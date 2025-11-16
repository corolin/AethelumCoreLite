"""
轴突工作器 (AxonWorker)

基于Python threading.Thread实现的工作器线程，负责传递神经信号。
"""

import threading
import time
import logging
import traceback
from typing import Callable, Dict, Optional, Any
from .message import NeuralImpulse
from .queue import SynapticQueue


class AxonWorker(threading.Thread):
    """
    轴突工作器 - 传递神经信号的纤维工作器

    继承自threading.Thread，持续消费队列中的神经脉冲并执行对应的Hook函数。
    包含强制性的SINK校验逻辑，确保流程安全。
    """

    # 强制性安全队列
    MANDATORY_QUEUES = {
        'Q_AUDIT_INPUT',     # 输入审查
        'Q_AUDIT_OUTPUT',    # 输出审查
        'Q_RESPONSE_SINK'    # 响应发送器（SINK校验）
    }

    def __init__(
        self,
        name: str,
        queue: SynapticQueue,
        hook_function: Optional[Callable[[NeuralImpulse, str], NeuralImpulse]] = None,
        router_instance: Optional[Any] = None,  # 回调到路由器
        error_handler: Optional[Callable[[Exception, NeuralImpulse], None]] = None,
        worker_id: Optional[int] = None
    ):
        """
        初始化轴突工作器

        Args:
            name: 工作器名称
            queue: 监听的突触队列
            hook_function: 处理神经脉冲的钩子函数
            router_instance: 路由器实例，用于路由消息
            error_handler: 错误处理函数
            worker_id: 工作器ID
        """
        super().__init__(name=f"AxonWorker-{name}", daemon=True)
        self.worker_name: str = name
        self.worker_id: int = worker_id or id(self)
        self.queue: SynapticQueue = queue
        self.hook_function: Optional[Callable] = hook_function
        self.router_instance = router_instance
        self.error_handler: Optional[Callable] = error_handler

        # 工作器状态
        self._running: bool = False
        self._stopped: threading.Event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 默认不暂停

        # 统计信息
        self._stats = {
            'created_at': time.time(),
            'started_at': None,
            'processed_messages': 0,
            'failed_messages': 0,
            'last_activity': None,
            'total_processing_time': 0.0
        }

        # 日志记录
        self.logger = logging.getLogger(f"worker.{name}")

    def run(self) -> None:
        """主工作循环"""
        self._running = True
        self._stats['started_at'] = time.time()
        self.logger.info(f"轴突工作器 {self.worker_name} 启动，监听队列: {self.queue.name}")

        try:
            while not self._stopped.is_set():
                # 检查是否暂停
                if not self._pause_event.is_set():
                    self._pause_event.wait()
                    continue

                # 获取神经脉冲（非阻塞）
                impulse = self.queue.get(block=False)
                if impulse is None:
                    time.sleep(0.01)  # 避免CPU空转
                    continue

                # 处理神经脉冲
                self._process_impulse(impulse)

        except Exception as e:
            self.logger.error(f"轴突工作器 {self.worker_name} 发生未捕获异常: {e}")
            self.logger.error(f"异常详情: {traceback.format_exc()}")
        finally:
            self._running = False
            self.logger.debug(f"轴突工作器 {self.worker_name} 停止")

    def _process_impulse(self, impulse: NeuralImpulse) -> None:
        """处理单个神经脉冲"""
        start_time = time.time()

        try:
            # SINK安全校验（如果当前队列是Q_RESPONSE_SINK）
            if self.queue.name == 'Q_RESPONSE_SINK':
                self._validate_sink_security(impulse)

            # 执行Hook函数
            if self.hook_function:
                processed_impulse = self.hook_function(impulse, self.queue.name)
                if processed_impulse is None:
                    # Hook返回None，丢弃消息
                    self.logger.warning(f"Hook函数返回None，丢弃消息: {impulse.session_id}")
                    self.queue.task_done()
                    return
            else:
                processed_impulse = impulse

            # 根据action_intent路由到下一个队列
            if self.router_instance and processed_impulse.action_intent:
                self._route_to_next_queue(processed_impulse)

            # 标记任务完成
            self.queue.task_done()

            # 更新统计信息
            processing_time = time.time() - start_time
            with threading.RLock():
                self._stats['processed_messages'] += 1
                self._stats['last_activity'] = time.time()
                self._stats['total_processing_time'] += processing_time

        except Exception as e:
            # 错误处理
            with threading.RLock():
                self._stats['failed_messages'] += 1
                self._stats['last_activity'] = time.time()

            self.logger.error(f"处理神经脉冲失败: {e}")
            self.logger.error(f"消息ID: {impulse.session_id}, 队列: {self.queue.name}")

            # 调用自定义错误处理器
            if self.error_handler:
                try:
                    self.error_handler(e, impulse)
                except Exception as handler_error:
                    self.logger.error(f"错误处理器也失败了: {handler_error}")

            # 仍然标记任务完成，避免阻塞队列
            self.queue.task_done()

    def _validate_sink_security(self, impulse: NeuralImpulse) -> None:
        """
        SINK安全校验逻辑 - 支持Q_AUDIT_INPUT和Q_AUDIT_OUTPUT双重来源

        验证消息是否源自Q_AUDIT_OUTPUT或Q_AUDIT_INPUT（输入审查失败的情况），确保安全性。
        """
        # 检查源Agent或路由历史，允许两种合法来源：
        # 1. Q_AUDIT_OUTPUT - 正常的输出审查流程
        # 2. Q_AUDIT_INPUT - 输入审查失败，直接跳转到回复流程
        valid_audit_sources = {'Q_AUDIT_INPUT', 'Q_AUDIT_OUTPUT'}

        # 检查源Agent是否为合法的审计来源
        source_agent_valid = False
        for valid_source in valid_audit_sources:
            if (impulse.source_agent == valid_source or
                impulse.source_agent.endswith(f"_{valid_source}")):
                source_agent_valid = True
                break

        # 检查路由历史是否包含合法的审计队列
        history_valid = False
        for valid_source in valid_audit_sources:
            if valid_source in impulse.routing_history:
                history_valid = True
                break

        if not (source_agent_valid or history_valid):
            error_msg = (f"流程违规：消息试图直接路由到Q_RESPONSE_SINK但未经过安全审查。"
                        f"Source: {impulse.source_agent}, History: {impulse.routing_history}")

            self.logger.error(error_msg)
            raise ValueError(error_msg)

        # 记录校验通过和来源
        if 'audit_failed_at_input' in impulse.metadata:
            self.logger.debug(f"SINK安全校验通过（输入审查失败）: {impulse.session_id}")
        elif 'audit_failed_at_output' in impulse.metadata:
            self.logger.debug(f"SINK安全校验通过（输出审查失败）: {impulse.session_id}")
        else:
            self.logger.debug(f"SINK安全校验通过（正常流程）: {impulse.session_id}")

    def _route_to_next_queue(self, impulse: NeuralImpulse) -> None:
        """将神经脉冲路由到下一个队列"""
        if not self.router_instance:
            self.logger.warning("无路由器实例，无法路由消息")
            return

        try:
            # 处理特殊的action_intent映射
            target_queue = impulse.action_intent

            # 如果当前已经在Q_DONE队列且目标是Done，则无需再次路由
            if (self.queue.name == 'Q_DONE' and target_queue == "Done"):
                return

            # 添加当前队列到路由历史，使用QUEUE:前缀区分队列名称和Agent名称
            impulse.add_to_history(f"QUEUE:{self.queue.name}")

            # Done action intent 映射到 Q_DONE 队列
            if target_queue == "Done":
                target_queue = "Q_DONE"

            # 调用路由器的发送方法
            self.router_instance._send_to_queue(target_queue, impulse)

        except Exception as e:
            self.logger.error(f"路由消息失败: {e}")
            raise

    def stop(self) -> None:
        """停止工作器"""
        self.logger.debug(f"停止轴突工作器 {self.worker_name}")
        self._stopped.set()

        # 如果工作器正在暂停状态，唤醒它以便退出
        self._pause_event.set()

    def pause(self) -> None:
        """暂停工作器"""
        self.logger.debug(f"暂停轴突工作器 {self.worker_name}")
        self._pause_event.clear()

    def resume(self) -> None:
        """恢复工作器"""
        self.logger.debug(f"恢复轴突工作器 {self.worker_name}")
        self._pause_event.set()

    def is_running(self) -> bool:
        """检查工作器是否运行中"""
        return self._running

    def is_paused(self) -> bool:
        """检查工作器是否暂停"""
        return not self._pause_event.is_set()

    def get_stats(self) -> Dict[str, Any]:
        """获取工作器统计信息"""
        with threading.RLock():
            uptime = time.time() - self._stats['created_at']
            runtime = time.time() - self._stats['started_at'] if self._stats['started_at'] else 0

            return {
                **self._stats,
                'worker_name': self.worker_name,
                'worker_id': self.worker_id,
                'queue_name': self.queue.name,
                'is_running': self._running,
                'is_paused': self.is_paused(),
                'uptime_seconds': uptime,
                'runtime_seconds': runtime,
                'avg_processing_time': (
                    self._stats['total_processing_time'] / max(1, self._stats['processed_messages'])
                ),
                'success_rate': (
                    (self._stats['processed_messages'] - self._stats['failed_messages']) /
                    max(1, self._stats['processed_messages'])
                ) if self._stats['processed_messages'] > 0 else 0.0
            }

    def __str__(self) -> str:
        """字符串表示"""
        status = "运行中" if self._running else "已停止"
        return f"AxonWorker(name='{self.worker_name}', queue='{self.queue.name}', status={status})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"AxonWorker(name='{self.worker_name}', worker_id={self.worker_id}, "
                f"queue='{self.queue.name}', running={self._running})")
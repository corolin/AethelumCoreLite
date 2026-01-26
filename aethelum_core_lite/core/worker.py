import threading
import time
import uuid
from typing import Dict, List, Optional, Callable, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from queue import Queue, Empty

from .message import NeuralImpulse
from .queue import SynapticQueue
# 使用类型注解字符串避免循环导入
# from .router import NeuralSomaRouter
from ..hooks.base_hook import BaseHook


class WorkerState(Enum):
    """工作器状态枚举"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    RECOVERING = "recovering"


class ErrorType(Enum):
    """错误类型枚举"""
    VALIDATION_ERROR = "validation_error"
    PROCESSING_ERROR = "processing_error"
    ROUTING_ERROR = "routing_error"
    QUEUE_ERROR = "queue_error"
    HOOK_ERROR = "hook_error"
    SYSTEM_ERROR = "system_error"
    TIMEOUT_ERROR = "timeout_error"


@dataclass
class WorkerStats:
    """工作器统计信息"""
    worker_id: str
    name: str
    state: WorkerState = WorkerState.INITIALIZING
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    processed_messages: int = 0
    failed_messages: int = 0
    total_processing_time: float = 0.0
    average_processing_time: float = 0.0
    success_rate: float = 0.0
    error_counts: Dict[str, int] = field(default_factory=dict)
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    recovery_attempts: int = 0
    consecutive_failures: int = 0
    health_score: float = 100.0
    uptime: float = 0.0


class AxonWorker(threading.Thread):
    """神经轴突工作器，负责处理神经脉冲消息
    
    工作器从输入队列获取神经脉冲，进行处理，然后路由到下一个队列。
    支持暂停、恢复和停止操作，以及错误处理和恢复机制。
    """
    
    def __init__(self,
                 name: str,
                 input_queue: SynapticQueue,
                 hooks: Optional[List[BaseHook]] = None,
                 router: Optional['NeuralSomaRouter'] = None,
                 error_handler: Optional[Callable[[Exception, NeuralImpulse], None]] = None,
                 worker_id: Optional[str] = None,
                 max_consecutive_failures: int = 5,
                 recovery_delay: float = 5.0,
                 health_check_interval: float = 30.0,
                 processing_timeout: float = 60.0):
        """初始化轴突工作器

        Args:
            name: 工作器名称
            input_queue: 输入队列
            hooks: 钩子函数列表
            router: 路由器实例
            error_handler: 错误处理函数
            worker_id: 工作器ID，如果不提供则自动生成
            max_consecutive_failures: 最大连续失败次数，超过后进入恢复模式
            recovery_delay: 恢复延迟时间（秒）
            health_check_interval: 健康检查间隔（秒）
            processing_timeout: 处理超时时间（秒）
        """
        super().__init__(daemon=True)
        self.name = name
        self.worker_id = worker_id or str(uuid.uuid4())
        self.input_queue = input_queue
        self.hooks = hooks or []
        self.router = router
        self.error_handler = error_handler

        # 工作器状态
        self._state = WorkerState.INITIALIZING
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始状态为运行

        # 错误处理配置
        self.max_consecutive_failures = max_consecutive_failures
        self.recovery_delay = recovery_delay
        self.health_check_interval = health_check_interval
        self.processing_timeout = processing_timeout

        # 统计信息
        self._stats = WorkerStats(
            worker_id=self.worker_id,
            name=self.name,
            state=self._state
        )

        # 统计信息锁（保护 _stats 的并发访问）
        self._stats_lock = threading.Lock()

        # 日志记录器
        import logging
        self.logger = logging.getLogger(f"AxonWorker.{name}")

        # 健康检查线程
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True
        )

        # 错误类型映射
        self._error_type_mapping = {
            ValueError: ErrorType.VALIDATION_ERROR,
            RuntimeError: ErrorType.PROCESSING_ERROR,
            KeyError: ErrorType.ROUTING_ERROR,
            Empty: ErrorType.QUEUE_ERROR,
            AttributeError: ErrorType.HOOK_ERROR,
            OSError: ErrorType.SYSTEM_ERROR,
            TimeoutError: ErrorType.TIMEOUT_ERROR
        }
    
    def run(self):
        """工作器主循环"""
        self._state = WorkerState.RUNNING
        self._stats.state = self._state
        self._stats.start_time = time.time()
        
        # 启动健康检查线程
        self._health_check_thread.start()
        
        try:
            while not self._stop_event.is_set():
                # 检查是否暂停
                if not self._pause_event.is_set():
                    time.sleep(0.1)
                    continue
                
                try:
                    # 非阻塞获取神经脉冲
                    impulse = self.input_queue.get(block=False)
                    if impulse is None:
                        time.sleep(0.1)
                        continue
                    
                    # 处理神经脉冲
                    self._process_impulse(impulse)
                    
                    # 重置连续失败计数
                    self._stats.consecutive_failures = 0
                    
                except Empty:
                    # 队列为空，短暂休眠
                    time.sleep(0.1)
                except Exception as e:
                    # 处理异常
                    self._handle_error(e, None)
                    
                    # 检查是否需要进入恢复模式
                    if self._stats.consecutive_failures >= self.max_consecutive_failures:
                        self._enter_recovery_mode()
        
        finally:
            self._state = WorkerState.STOPPED
            self._stats.state = self._state
    
    def _process_impulse(self, impulse: NeuralImpulse):
        """处理神经脉冲
        
        Args:
            impulse: 神经脉冲对象
        """
        start_time = time.time()
        self._stats.last_activity = start_time
        
        try:
            # 验证SINK安全
            self._validate_sink_security(impulse)
            
            # 执行前置钩子
            for hook in self.hooks:
                hook.before_process(impulse)
            
            # 路由到下一个队列
            self._route_to_next_queue(impulse)
            
            # 执行后置钩子
            for hook in self.hooks:
                hook.after_process(impulse)
            
            # 更新统计信息
            processing_time = time.time() - start_time
            self._update_stats(processing_time, success=True)
            
        except Exception as e:
            # 更新统计信息
            processing_time = time.time() - start_time
            self._update_stats(processing_time, success=False)
            
            # 处理错误
            self._handle_error(e, impulse)
            
            # 如果有错误处理器，调用它
            if self.error_handler:
                try:
                    self.error_handler(e, impulse)
                except Exception as handler_error:
                    self.logger.error(f"Error in error handler: {handler_error}")
    
    def _validate_sink_security(self, impulse: NeuralImpulse):
        """验证SINK安全

        根据设计文档 v0.1 要求，Q_RESPONSE_SINK 的 Worker 必须验证消息是否经过 Q_AUDIT_OUTPUT 审查。
        这是强制性安全检查，防止消息绕过输出审查直接进入响应队列。

        验证规则：
        1. 检查 routing_history 中是否包含 "Q_AUDIT_OUTPUT"（表示消息流经了该队列）
        2. source_agent 字段应该是处理 Q_AUDIT_OUTPUT 的 Agent 名称，不直接用于验证

        Args:
            impulse: 神经脉冲对象

        Raises:
            ValueError: 如果验证失败（消息未经过 Q_AUDIT_OUTPUT 审查）
        """
        # 只有 Q_RESPONSE_SINK 队列需要验证
        if impulse.action_intent == "Q_RESPONSE_SINK":
            # 检查消息是否经过 Q_AUDIT_OUTPUT 队列
            if "Q_AUDIT_OUTPUT" not in impulse.routing_history:
                raise ValueError(
                    f"【安全违规】消息直接路由到 Q_RESPONSE_SINK 但未经过 Q_AUDIT_OUTPUT 审查！\n"
                    f"消息来源: {impulse.source_agent}\n"
                    f"路由历史: {impulse.routing_history}\n"
                    f"会话ID: {impulse.session_id}\n"
                    f"根据设计文档 v0.1 第4.2节要求，所有进入 Q_RESPONSE_SINK 的消息必须经过 Q_AUDIT_OUTPUT 审查。"
                )
    
    def _route_to_next_queue(self, impulse: NeuralImpulse):
        """路由神经脉冲到下一个队列
        
        Args:
            impulse: 神经脉冲对象
            
        Raises:
            KeyError: 如果路由失败
        """
        if not self.router:
            raise KeyError("No router configured")
        
        # 根据action_intent路由到不同的队列
        action_intent = impulse.metadata.get("action_intent", "Q_AUDIT_OUTPUT")
        
        # 更新路由历史
        impulse.add_to_history(self.name)
        
        # 路由到下一个队列
        success = self.router._send_to_queue(action_intent, impulse)
        if not success:
            raise KeyError(f"Failed to route impulse with action_intent: {action_intent}")
    
    def _handle_error(self, error: Exception, impulse: Optional[NeuralImpulse] = None):
        """处理错误
        
        Args:
            error: 异常对象
            impulse: 相关的神经脉冲对象（可选）
        """
        # 确定错误类型
        error_type = self._determine_error_type(error)
        
        # 更新错误统计
        error_type_str = error_type.value
        self._stats.error_counts[error_type_str] = self._stats.error_counts.get(error_type_str, 0) + 1
        self._stats.last_error = str(error)
        self._stats.last_error_time = time.time()
        self._stats.consecutive_failures += 1
        
        # 记录错误
        self.logger.error(f"Error in worker {self.name}: {error}")
        if impulse:
            self.logger.error(f"Error processing impulse: {impulse.session_id}")
    
    def _determine_error_type(self, error: Exception) -> ErrorType:
        """确定错误类型
        
        Args:
            error: 异常对象
            
        Returns:
            ErrorType: 错误类型
        """
        for error_class, error_type in self._error_type_mapping.items():
            if isinstance(error, error_class):
                return error_type
        
        # 默认为系统错误
        return ErrorType.SYSTEM_ERROR
    
    def _enter_recovery_mode(self):
        """进入恢复模式"""
        self._state = WorkerState.RECOVERING
        self._stats.state = self._state
        self._stats.recovery_attempts += 1
        
        self.logger.warning(f"Worker {self.name} entering recovery mode after {self._stats.consecutive_failures} consecutive failures")
        
        # 等待恢复延迟
        time.sleep(self.recovery_delay)
        
        # 重置连续失败计数
        self._stats.consecutive_failures = 0
        
        # 恢复到运行状态
        self._state = WorkerState.RUNNING
        self._stats.state = self._state
        
        self.logger.info(f"Worker {self.name} recovered and resuming operation")
    
    def _health_check_loop(self):
        """健康检查循环"""
        while not self._stop_event.is_set():
            time.sleep(self.health_check_interval)
            
            # 计算健康分数
            self._calculate_health_score()
            
            # 检查是否需要干预
            if self._stats.health_score < 30.0:
                self.logger.warning(f"Worker {self.name} health score is low: {self._stats.health_score}")
    
    def _calculate_health_score(self):
        """计算健康分数"""
        # 基础分数
        score = 100.0
        
        # 根据成功率调整
        if self._stats.processed_messages > 0:
            success_rate = self._stats.success_rate
            score *= (success_rate / 100.0)
        
        # 根据连续失败次数调整
        if self._stats.consecutive_failures > 0:
            score -= (self._stats.consecutive_failures * 10)
        
        # 根据恢复尝试次数调整
        if self._stats.recovery_attempts > 0:
            score -= (self._stats.recovery_attempts * 5)
        
        # 确保分数在0-100之间
        self._stats.health_score = max(0.0, min(100.0, score))
    
    def _update_stats(self, processing_time: float, success: bool):
        """更新统计信息

        Args:
            processing_time: 处理时间
            success: 是否成功
        """
        with self._stats_lock:
            if success:
                self._stats.processed_messages += 1
            else:
                self._stats.failed_messages += 1

            self._stats.total_processing_time += processing_time
            total_messages = self._stats.processed_messages + self._stats.failed_messages

            if total_messages > 0:
                self._stats.average_processing_time = self._stats.total_processing_time / total_messages
                self._stats.success_rate = (self._stats.processed_messages / total_messages) * 100

            # 更新运行时间
            self._stats.uptime = time.time() - self._stats.start_time
    
    def pause(self):
        """暂停工作器"""
        self._pause_event.clear()
        self._state = WorkerState.PAUSED
        self._stats.state = self._state
        self.logger.info(f"Worker {self.name} paused")

    def resume(self):
        """恢复工作器"""
        self._pause_event.set()
        self._state = WorkerState.RUNNING
        self._stats.state = self._state
        self.logger.info(f"Worker {self.name} resumed")

    def stop(self):
        """停止工作器"""
        self._state = WorkerState.STOPPING
        self._stats.state = self._state
        self._stop_event.set()
        self.logger.info(f"Worker {self.name} stopping")
    
    def get_stats(self) -> WorkerStats:
        """获取工作器统计信息

        Returns:
            WorkerStats: 工作器统计信息
        """
        with self._stats_lock:
            # 更新运行时间
            self._stats.uptime = time.time() - self._stats.start_time

            # 更新状态
            self._stats.state = self._state

            # 返回副本而非引用，防止外部修改
            return WorkerStats(
                worker_id=self._stats.worker_id,
                name=self._stats.name,
                state=self._stats.state,
                start_time=self._stats.start_time,
                last_activity=self._stats.last_activity,
                processed_messages=self._stats.processed_messages,
                failed_messages=self._stats.failed_messages,
                total_processing_time=self._stats.total_processing_time,
                average_processing_time=self._stats.average_processing_time,
                success_rate=self._stats.success_rate,
                error_counts=dict(self._stats.error_counts),
                last_error=self._stats.last_error,
                last_error_time=self._stats.last_error_time,
                recovery_attempts=self._stats.recovery_attempts,
                consecutive_failures=self._stats.consecutive_failures,
                health_score=self._stats.health_score,
                uptime=self._stats.uptime
            )
    
    def get_state(self) -> WorkerState:
        """获取工作器状态
        
        Returns:
            WorkerState: 工作器状态
        """
        return self._state
    
    def is_healthy(self) -> bool:
        """检查工作器是否健康
        
        Returns:
            bool: 是否健康
        """
        return self._stats.health_score >= 50.0
    
    def __str__(self) -> str:
        """返回工作器的字符串表示
        
        Returns:
            str: 工作器字符串表示
        """
        return f"AxonWorker(name={self.name}, state={self._state.value}, processed={self._stats.processed_messages})"
    
    def __repr__(self) -> str:
        """返回工作器的详细字符串表示
        
        Returns:
            str: 工作器详细字符串表示
        """
        return (f"AxonWorker(id={self.worker_id}, name={self.name}, state={self._state.value}, "
                f"processed={self._stats.processed_messages}, failed={self._stats.failed_messages}, "
                f"success_rate={self._stats.success_rate:.2f}%, health_score={self._stats.health_score:.2f})")
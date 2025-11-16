"""
神经胞体路由器 (NeuralSomaRouter)

核心编排组件，负责整合和分发神经信号，管理队列和工作器的生命周期。
"""

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Set, Any
from .message import NeuralImpulse
from .queue import SynapticQueue
from .worker import AxonWorker
from .openai_client import OpenAIConfig
from .zhipu_client import ZhipuClientManager


class NeuralSomaRouter:
    """
    神经胞体路由器 - 整合和分发神经信号的核心组件

    基于设计文档的CoreLiteRouter实现：
    - 维护队列实例和钩子映射
    - 管理Worker线程的生命周期
    - 提供神经系统的启动/激活接口
    - 强制执行安全审计流程
    """

    # 强制性核心队列
    MANDATORY_QUEUES = {
        'Q_AUDIT_INPUT',     # 输入审查
        'Q_AUDITED_INPUT',   # 审计后输入
        'Q_AUDIT_OUTPUT',    # 输出审查
        'Q_RESPONSE_SINK',   # 响应发送器
        'Q_ERROR_HANDLER',    # 错误处理器
        'Q_DONE'             # 消息终止处理器
    }

    # 审计相关的队列（由路由器自动管理）
    AUDIT_QUEUES = {
        'Q_AUDIT_INPUT',
        'Q_AUDITED_INPUT',
        'Q_AUDIT_OUTPUT'
    }

    # 禁止注册钩子的队列（审计队列由路由器管理）
    FORBIDDEN_HOOK_QUEUES = {
        'Q_AUDIT_INPUT',
        'Q_AUDIT_OUTPUT'
    }

    def __init__(self, enable_logging: bool = True, openai_config: Optional[OpenAIConfig] = None):
        """
        初始化神经胞体路由器

        Args:
            enable_logging: 是否启用日志记录
            openai_config: OpenAI客户端配置（可选）
        """
        # 队列管理
        self._queues: Dict[str, SynapticQueue] = {}
        self._lock = threading.RLock()

        # Hook映射：队列名 -> Hook函数
        self._hooks: Dict[str, Callable] = {}

        # Worker管理
        self._workers: Dict[str, List[AxonWorker]] = {}
        self._router_active = False

        # 审计Agent管理（内部自动创建）
        self._audit_agent = None
        self._zhipu_client = None  # 延迟初始化，在logger创建后

        # 统计信息
        self._stats = {
            'created_at': time.time(),
            'activated_at': None,
            'total_impulses_processed': 0,
            'total_hooks_registered': 0,
            'total_queues_created': 0
        }

        # 日志设置
        if enable_logging:
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        self.logger = logging.getLogger("NeuralSomaRouter")

        # Zhipu客户端管理（移到logger创建后）
        if openai_config:
            try:
                zhipu_manager = ZhipuClientManager.create_from_openai_config(openai_config)
                self._zhipu_client = zhipu_manager.get_default_client()
                if self._zhipu_client:
                    self.logger.info(f"智谱AI客户端创建成功 - 模型: {openai_config.model}")
                else:
                    # 没有配置时直接抛出异常
                    error_msg = "智谱AI客户端创建失败：SDK未安装或配置错误。请安装 zai-sdk: pip install zai-sdk"
                    self.logger.error(error_msg)
                    raise RuntimeError(error_msg)
            except Exception as e:
                error_msg = f"智谱AI客户端初始化失败: {e}"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
        else:
            # 没有提供配置时也需要智谱AI客户端
            error_msg = "未提供OpenAI配置。审计功能需要智谱AI客户端支持。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def create_queue(
        self,
        name: str,
        max_size: Optional[int] = None,
        durable: bool = False,
        auto_delete: bool = False
    ) -> SynapticQueue:
        """
        创建突触队列

        Args:
            name: 队列名称
            max_size: 最大容量
            durable: 是否持久化
            auto_delete: 是否自动删除

        Returns:
            SynapticQueue: 创建的队列实例
        """
        with self._lock:
            if name in self._queues:
                self.logger.warning(f"队列 {name} 已存在，返回现有实例")
                return self._queues[name]

            queue = SynapticQueue(
                name=name,
                max_size=max_size,
                durable=durable,
                auto_delete=auto_delete
            )

            self._queues[name] = queue
            self._stats['total_queues_created'] += 1

            self.logger.debug(f"创建突触队列: {name}")
            return queue

    def get_queue(self, name: str) -> Optional[SynapticQueue]:
        """获取队列实例"""
        with self._lock:
            return self._queues.get(name)

    def register_hook(
        self,
        queue_name: str,
        hook_function: Callable[[NeuralImpulse, str], NeuralImpulse]
    ) -> None:
        """
        注册Hook函数到指定队列

        Args:
            queue_name: 队列名称
            hook_function: Hook函数

        Raises:
            ValueError: 如果尝试向禁止的队列注册Hook
        """
        # 强制检查：禁止向Q_AUDIT_INPUT和Q_AUDIT_OUTPUT注册Hook
        if queue_name in self.FORBIDDEN_HOOK_QUEUES:
            raise ValueError(
                f"禁止向安全队列 {queue_name} 注册Hook。安全队列必须由系统管理。"
            )

        with self._lock:
            if queue_name not in self._queues:
                raise ValueError(f"队列 {queue_name} 不存在，请先创建队列")

            self._hooks[queue_name] = hook_function
            self._stats['total_hooks_registered'] += 1

            self.logger.debug(f"注册Hook到队列: {queue_name}")

    def start_workers(
        self,
        queue_name: str,
        num_workers: int = 1,
        custom_hook: Optional[Callable] = None
    ) -> List[AxonWorker]:
        """
        为指定队列启动工作器

        Args:
            queue_name: 队列名称
            num_workers: 工作器数量
            custom_hook: 自定义Hook函数（覆盖已注册的Hook）

        Returns:
            List[AxonWorker]: 启动的工作器列表
        """
        with self._lock:
            if queue_name not in self._queues:
                raise ValueError(f"队列 {queue_name} 不存在")

            queue = self._queues[queue_name]
            hook_function = custom_hook or self._hooks.get(queue_name)

            # 创建工作器
            workers = []
            for i in range(num_workers):
                worker = AxonWorker(
                    name=f"{queue_name}-worker-{i}",
                    queue=queue,
                    hook_function=hook_function,
                    router_instance=self
                )
                workers.append(worker)

            # 记录工作器
            if queue_name not in self._workers:
                self._workers[queue_name] = []
            self._workers[queue_name].extend(workers)

            # 启动工作器
            for worker in workers:
                worker.start()

            self.logger.debug(f"为队列 {queue_name} 启动了 {num_workers} 个工作器")
            return workers

    def activate(self) -> None:
        """
        激活整个神经系统

        自动创建所有强制性队列，初始化审计组件，启动必要的工作器。
        """
        with self._lock:
            if self._router_active:
                self.logger.warning("神经系统已经激活")
                return

            # 自动创建所有强制性队列
            self._initialize_mandatory_queues()

            # 自动创建和设置审计组件
            self._setup_audit_hooks()

            # 确保所有强制性队列都存在
            missing_queues = self.MANDATORY_QUEUES - set(self._queues.keys())
            if missing_queues:
                raise ValueError(f"缺少强制性队列: {missing_queues}")

            self._router_active = True
            self._stats['activated_at'] = time.time()
            self.logger.info("神经系统已激活")

    def _initialize_mandatory_queues(self) -> None:
        """自动初始化所有强制性队列"""
        self.logger.info("初始化强制性队列...")

        for queue_name in self.MANDATORY_QUEUES:
            if queue_name not in self._queues:
                self.create_queue(queue_name)
                self.logger.debug(f"自动创建队列: {queue_name}")

        # 为 Q_DONE 队列设置内置的 Done handler
        self._setup_builtin_done_handler()

    def _setup_builtin_done_handler(self) -> None:
        """设置内置的 Done 消息处理器"""
        logger = logging.getLogger("Builtin.DoneHandler")

        def handle_done(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
            """内置 Done 消息处理器 - 消息的最终归宿"""
            # Done 队列是消息的最终归宿，只进行日志记录
            logger.debug(f"消息已终止: {impulse.session_id}")
            # 保持 action_intent = "Done" 防止进一步路由
            return impulse

        # 注册内置的 Done handler 并启动工作器
        self.register_hook("Q_DONE", handle_done)
        self.start_workers("Q_DONE", 1)  # 通常只需要一个工作器处理终止消息
        self.logger.debug("内置Done处理器已注册")

    def _create_audit_agent(self) -> Optional['AuditAgent']:
        """自动创建审计Agent"""
        if not self._zhipu_client:
            self.logger.warning("无法创建审计Agent：缺少智谱AI客户端")
            return None

        try:
            from ..agents.audit_agent import AuditAgent
            agent_name = "NeuralSomaAuditAgent"  # 固定名称，用户无需关心
            self._audit_agent = AuditAgent(agent_name, self._zhipu_client)
            self.logger.info(f"审计Agent创建成功: {agent_name}")
            return self._audit_agent
        except Exception as e:
            self.logger.error(f"创建审计Agent失败: {e}")
            return None

    def _setup_audit_hooks(self, audit_agent=None) -> None:
        """自动设置审计相关的钩子"""
        # 如果没有提供审计Agent，尝试自动创建
        if not audit_agent:
            audit_agent = self._create_audit_agent()

        # 审计Agent必须存在
        if not audit_agent:
            error_msg = "审计Agent创建失败。无法继续初始化系统。"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 设置审计钩子
        self.logger.info("设置审计钩子...")

        # 注册输入审计钩子
        self.start_workers("Q_AUDIT_INPUT", 1, audit_agent.process_input_audit)

        # 注册输出审计钩子
        self.start_workers("Q_AUDIT_OUTPUT", 1, audit_agent.process_output_audit)

        self.logger.info("审计钩子设置完成")

        # 创建默认错误处理器并注册钩子
        from .hooks import create_default_error_handler
        error_handler = create_default_error_handler()
        self.register_hook("Q_ERROR_HANDLER", error_handler)
        self.start_workers("Q_ERROR_HANDLER", 1)

    def setup_business_handlers(self, business_handler=None, response_handler=None) -> None:
        """
        设置业务处理器（用户自定义组件）

        Args:
            business_handler: 业务处理钩子函数
            response_handler: 响应处理钩子函数
        """
        if business_handler:
            self.register_hook("Q_AUDITED_INPUT", business_handler)
            self.start_workers("Q_AUDITED_INPUT", 1)
            self.logger.info("业务处理器已注册")

        if response_handler:
            self.register_hook("Q_RESPONSE_SINK", response_handler)
            self.start_workers("Q_RESPONSE_SINK", 1)
            self.logger.info("响应处理器已注册")

    def auto_setup(self, business_handler=None, response_handler=None) -> None:
        """
        一键自动设置整个神经系统

        Args:
            business_handler: 业务处理钩子函数（用户自定义）
            response_handler: 响应处理钩子函数（用户自定义）
        """
        self.logger.info("开始自动设置神经系统...")

        # 激活系统（自动创建审计Agent和所有组件，包括Done队列）
        self.activate()

        # 设置业务组件
        self.setup_business_handlers(business_handler, response_handler)

        self.logger.info("神经系统自动设置完成")

    
    def inject_input(self, impulse: NeuralImpulse) -> bool:
        """
        注入神经脉冲到系统

        这是用户输入的主要入口点。

        Args:
            impulse: 神经脉冲

        Returns:
            bool: 是否成功注入
        """
        if not self._router_active:
            self.logger.error("神经系统未激活，无法注入神经脉冲")
            return False

        # 必须有审计Agent，走审计流程
        if not self._audit_agent:
            self.logger.error("审计Agent未初始化，无法注入消息")
            return False

        impulse.action_intent = 'Q_AUDIT_INPUT'
        # 添加初始处理节点记录
        impulse.add_to_history("INPUT_GATEWAY")
        return self._send_to_queue('Q_AUDIT_INPUT', impulse)

    def _send_to_queue(self, queue_name: str, impulse: NeuralImpulse) -> bool:
        """
        内部方法：发送神经脉冲到指定队列

        Args:
            queue_name: 目标队列名称
            impulse: 神经脉冲

        Returns:
            bool: 是否成功发送
        """
        queue = self.get_queue(queue_name)
        if queue is None:  # 修复：使用 is None 而不是 not queue
            self.logger.error(f"目标队列不存在: {queue_name}")
            return False

        try:
            success = queue.put(impulse, block=True, timeout=5.0)
            if success:
                with self._lock:
                    self._stats['total_impulses_processed'] += 1
                self.logger.debug(f"神经脉冲已发送到队列 {queue_name}: {impulse.session_id[:8]}...")
            return success
        except Exception as e:
            self.logger.error(f"发送神经脉冲到队列 {queue_name} 失败: {e}")
            return False

    def stop(self) -> None:
        """停止整个神经系统"""
        self.logger.info("正在停止神经系统...")

        with self._lock:
            # 停止所有工作器
            for queue_name, workers in self._workers.items():
                self.logger.debug(f"停止队列 {queue_name} 的工作器...")
                for worker in workers:
                    worker.stop()
                    worker.join(timeout=5.0)

            self._router_active = False

        self.logger.info("🧠 神经系统已停止")

    def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息"""
        with self._lock:
            uptime = time.time() - self._stats['created_at']
            runtime = time.time() - self._stats['activated_at'] if self._stats['activated_at'] else 0

            # 统计所有队列的信息
            queue_stats = {}
            total_queue_size = 0
            for name, queue in self._queues.items():
                stats = queue.get_stats()
                queue_stats[name] = stats
                total_queue_size += stats['current_size']

            # 统计所有工作器的信息
            worker_stats = {}
            total_workers = 0
            for queue_name, workers in self._workers.items():
                worker_stats[queue_name] = [worker.get_stats() for worker in workers]
                total_workers += len(workers)

            return {
                **self._stats,
                'is_active': self._router_active,
                'uptime_seconds': uptime,
                'runtime_seconds': runtime,
                'queue_count': len(self._queues),
                'hook_count': len(self._hooks),
                'worker_count': total_workers,
                'total_queue_size': total_queue_size,
                'mandatory_queues_present': self.MANDATORY_QUEUES.issubset(set(self._queues.keys())),
                'queues': queue_stats,
                'workers': worker_stats
            }

    def list_queues(self) -> List[str]:
        """列出所有队列名称"""
        with self._lock:
            return list(self._queues.keys())

    def list_hooks(self) -> List[str]:
        """列出所有已注册Hook的队列名称"""
        with self._lock:
            return list(self._hooks.keys())

    def get_queue_sizes(self) -> Dict[str, int]:
        """获取所有队列的当前大小"""
        sizes = {}
        for name, queue in self._queues.items():
            sizes[name] = queue.size()
        return sizes

    def __str__(self) -> str:
        """字符串表示"""
        status = "已激活" if self._router_active else "未激活"
        return f"NeuralSomaRouter(queues={len(self._queues)}, hooks={len(self._hooks)}, status={status})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"NeuralSomaRouter(queues={list(self._queues.keys())}, "
                f"hooks={list(self._hooks.keys())}, active={self._router_active})")
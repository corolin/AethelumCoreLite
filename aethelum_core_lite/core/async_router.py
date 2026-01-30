"""
异步Router实现

异步神经路由器，负责消息路由和组件管理。
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
import time

from .async_worker import AsyncAxonWorker
from .async_queue import AsyncSynapticQueue, QueuePriority
from .async_hooks import AsyncHookType, AsyncBaseHook
from .message import NeuralImpulse

logger = logging.getLogger(__name__)


@dataclass
class RouterMetrics:
    """路由器指标（内存存储）"""
    router_id: str
    total_workers: int = 0
    total_queues: int = 0
    total_messages_routed: int = 0
    last_update: float = field(default_factory=time.time)
    labels: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


class AsyncNeuralSomaRouter:
    """异步神经路由器"""

    def __init__(self, router_id: str):
        self.router_id = router_id
        self._queues: Dict[str, AsyncSynapticQueue] = {}
        self._workers: Dict[str, AsyncAxonWorker] = {}
        self._routing_rules: Dict[str, str] = {}
        self._queue_priorities: Dict[str, QueuePriority] = {}

        # Hook系统
        self._hooks: Dict[str, Dict[AsyncHookType, List[Callable]]] = {}
        self._lock = asyncio.Lock()

        # 性能指标
        self._performance_metrics = {
            'queue_processing_times': {},  # 队列名 -> [处理时间列表]
            'hook_execution_times': {},    # 队列名 -> {hook_type -> [执行时间列表]}
            'worker_utilization': {},      # 队列名 -> [工作器利用率列表]
            'last_metrics_update': time.time(),
            'total_hooks_executed': 0,
            'total_hook_errors': 0
        }

        # 指标存储（内存）
        self._metrics = RouterMetrics(
            router_id=router_id,
            labels={"router_id": router_id}
        )

        # 系统状态
        self._router_active = False

        # 强制性核心队列（与同步版本保持一致）
        self.MANDATORY_QUEUES = {
            'Q_AUDIT_INPUT': {'priority': QueuePriority.HIGH, 'description': '输入审查队列'},
            'Q_AUDIT_OUTPUT': {'priority': QueuePriority.HIGH, 'description': '输出审查队列'},
            'Q_RESPONSE_SINK': {'priority': QueuePriority.CRITICAL, 'description': '响应汇聚队列'},
            'Q_DONE': {'priority': QueuePriority.NORMAL, 'description': '完成队列'},
            'Q_ERROR': {'priority': QueuePriority.CRITICAL, 'description': '错误处理队列'}
        }

    async def start(self):
        """启动路由器"""
        # 启动所有Worker
        tasks = [worker.start() for worker in self._workers.values()]
        if tasks:
            await asyncio.gather(*tasks)
        logger.info(f"[Router] {self.router_id} started with {len(self._workers)} workers")

    async def stop(self):
        """停止路由器"""
        # 停止所有Worker
        tasks = [worker.stop() for worker in self._workers.values()]
        if tasks:
            await asyncio.gather(*tasks)
        logger.info(f"[Router] {self.router_id} stopped")

    def register_queue(self, queue: AsyncSynapticQueue, priority: QueuePriority = QueuePriority.NORMAL):
        """注册队列

        Args:
            queue: 队列实例
            priority: 队列优先级（默认为NORMAL）
        """
        self._queues[queue.queue_id] = queue
        # 如果队列没有设置优先级，使用默认值
        if queue.queue_id not in self._queue_priorities:
            self._queue_priorities[queue.queue_id] = priority
        self._update_metrics_async()

    def register_worker(self, worker: AsyncAxonWorker):
        """注册Worker"""
        self._workers[worker.worker_id] = worker
        self._update_metrics_async()

    def add_routing_rule(self, pattern: str, queue_id: str):
        """添加路由规则"""
        self._routing_rules[pattern] = queue_id

    async def route_message(self, message: Any, pattern: str) -> bool:
        """异步路由消息"""
        queue_id = self._routing_rules.get(pattern)

        if not queue_id or queue_id not in self._queues:
            logger.warning(f"[Router] No queue found for pattern: {pattern}")
            return False

        # 如果message是NeuralImpulse，进行安全验证
        if hasattr(message, 'action_intent'):
            from .message import NeuralImpulse
            if isinstance(message, NeuralImpulse):
                if not await self._validate_sink_security(message):
                    logger.error(f"[Router] 安全验证失败，拒绝路由消息到 {message.action_intent}")
                    return False

        queue = self._queues[queue_id]
        result = await queue.async_put(message)

        # 异步更新指标
        if result:
            self._metrics.total_messages_routed += 1
            self._update_metrics_async()

        return result

    async def _validate_sink_security(self, impulse: Any) -> bool:
        """
        验证SINK队列的安全性

        防止消息路由到敏感SINK队列，只有授权的Agent可以路由。

        Args:
            impulse: 神经脉冲

        Returns:
            bool: True表示通过验证
        """
        if not hasattr(impulse, 'action_intent'):
            return True

        # 定义敏感SINK列表
        SENSITIVE_SINKS = [
            "Q_AUDIT_OUTPUT",
            "Q_SECURITY_LOG",
            "Q_COMPLIANCE_CHECK"
        ]

        action_intent = impulse.action_intent

        # 检查是否尝试路由到敏感SINK
        if action_intent in SENSITIVE_SINKS:
            # 验证来源权限
            source = getattr(impulse, 'source_agent', "")

            # 只有特定Agent可以路由到这些SINK
            allowed_sources = ["SecurityAuditor", "ComplianceManager", "Admin"]

            if source not in allowed_sources:
                logger.warning(
                    f"[Security] 拒绝非授权访问SINK: {action_intent}, "
                    f"来源: {source}"
                )
                return False

        return True

    async def route_from_audit_input(self, impulse: NeuralImpulse) -> bool:
        """
        从 Q_AUDIT_INPUT 路由消息

        这是审计队列的Worker应该调用的方法。
        根据审计结果，将消息路由到 Q_AUDIT_OUTPUT 或拒绝。

        Args:
            impulse: 神经脉冲

        Returns:
            bool: True表示成功路由
        """
        # 验证消息确实来自 Q_AUDIT_INPUT
        if "Q_AUDIT_INPUT" not in impulse.routing_history:
            logger.error(
                f"[Security] 消息未经过 Q_AUDIT_INPUT 审查，拒绝处理 "
                f"session_id={impulse.session_id}"
            )
            return False

        # 执行输入审计逻辑（这里可以添加自定义的审计规则）
        # 默认情况下，所有消息都通过审计
        audit_passed = await self._perform_input_audit(impulse)

        if audit_passed:
            # 审计通过，路由到 Q_AUDIT_OUTPUT
            impulse.action_intent = 'Q_AUDIT_OUTPUT'

            # 添加审计通过标记
            impulse.metadata['audit_input_passed'] = True
            impulse.metadata['audit_input_timestamp'] = time.time()

            success = await self.route_message(impulse, 'Q_AUDIT_OUTPUT')

            if success:
                logger.debug(
                    f"[Router] 消息通过输入审计，已路由到 Q_AUDIT_OUTPUT "
                    f"session_id={impulse.session_id}"
                )

            return success
        else:
            # 审计失败，路由到错误处理队列
            logger.warning(
                f"[Router] 消息未通过输入审计，session_id={impulse.session_id}"
            )

            impulse.action_intent = 'Q_ERROR'
            impulse.metadata['audit_failure_reason'] = 'Input audit failed'

            return await self.route_message(impulse, 'Q_ERROR')

    async def route_from_audit_output(self, impulse: NeuralImpulse) -> bool:
        """
        从 Q_AUDIT_OUTPUT 路由消息

        这是输出审计队列的Worker应该调用的方法。
        审计通过后，恢复原始目标并继续路由。

        Args:
            impulse: 神经脉冲

        Returns:
            bool: True表示成功路由
        """
        # 验证消息确实经过 Q_AUDIT_INPUT 和 Q_AUDIT_OUTPUT
        if "Q_AUDIT_INPUT" not in impulse.routing_history:
            logger.error(
                f"[Security] 消息未经过 Q_AUDIT_INPUT，拒绝处理 "
                f"session_id={impulse.session_id}"
            )
            return False

        if "Q_AUDIT_OUTPUT" not in impulse.routing_history:
            logger.error(
                f"[Security] 消息未经过 Q_AUDIT_OUTPUT 审查，拒绝处理 "
                f"session_id={impulse.session_id}"
            )
            return False

        # 执行输出审计逻辑
        audit_passed = await self._perform_output_audit(impulse)

        if audit_passed:
            # 审计通过，恢复原始目标队列
            original_intent = impulse.metadata.get('original_action_intent')

            if not original_intent:
                logger.error(
                    f"[Router] 无法找到原始目标队列 "
                    f"session_id={impulse.session_id}"
                )
                return False

            # 恢复原始目标
            impulse.action_intent = original_intent

            # 添加输出审计通过标记
            impulse.metadata['audit_output_passed'] = True
            impulse.metadata['audit_output_timestamp'] = time.time()

            # 路由到原始目标
            success = await self.route_message(impulse, original_intent)

            if success:
                logger.debug(
                    f"[Router] 消息通过输出审计，已路由到原始目标 {original_intent} "
                    f"session_id={impulse.session_id}"
                )
                self._metrics.total_messages_routed += 1

            return success
        else:
            # 审计失败，路由到错误处理队列
            logger.warning(
                f"[Router] 消息未通过输出审计，session_id={impulse.session_id}"
            )

            impulse.action_intent = 'Q_ERROR'
            impulse.metadata['audit_failure_reason'] = 'Output audit failed'

            return await self.route_message(impulse, 'Q_ERROR')

    async def _perform_input_audit(self, impulse: NeuralImpulse) -> bool:
        """
        执行输入审计逻辑

        可根据实际需求自定义审计规则（例如敏感词检测、格式验证等）。

        Args:
            impulse: 神经脉冲

        Returns:
            bool: True表示审计通过
        """
        # 默认实现：所有消息都通过审计
        # 实际使用时应该添加具体的审计逻辑
        return True

    async def _perform_output_audit(self, impulse: NeuralImpulse) -> bool:
        """
        执行输出审计逻辑

        可根据实际需求自定义审计规则（例如敏感信息过滤、内容审查等）。

        Args:
            impulse: 神经脉冲

        Returns:
            bool: True表示审计通过
        """
        # 默认实现：所有消息都通过审计
        # 实际使用时应该添加具体的审计逻辑
        return True

    def _update_metrics_async(self):
        """异步更新指标到内存"""
        self._metrics.total_workers = len(self._workers)
        self._metrics.total_queues = len(self._queues)
        self._metrics.last_update = time.time()

        # 更新metrics字典
        self._metrics.metrics = {
            "router_id": self.router_id,
            "total_workers": self._metrics.total_workers,
            "total_queues": self._metrics.total_queues,
            "total_messages_routed": self._metrics.total_messages_routed,
            "last_update": self._metrics.last_update
        }

    async def register_hook(
        self,
        queue_name: str,
        hook_function: Union[Callable, AsyncBaseHook],
        hook_type: AsyncHookType = AsyncHookType.PRE_PROCESS,
        replace: bool = False
    ) -> None:
        """
        注册Hook到指定队列

        Args:
            queue_name: 队列名称
            hook_function: Hook函数或AsyncBaseHook实例
            hook_type: Hook类型
            replace: 是否替换现有的Hooks（False表示追加）
        """
        async with self._lock:
            # 检查队列是否存在
            if queue_name not in self._queues:
                raise ValueError(f"队列 {queue_name} 不存在，请先创建队列")

            # 初始化队列的Hook字典
            if queue_name not in self._hooks:
                self._hooks[queue_name] = {}

            # 初始化Hook类型的列表
            if hook_type not in self._hooks[queue_name]:
                self._hooks[queue_name][hook_type] = []

            # 替换或添加Hook
            if replace:
                self._hooks[queue_name][hook_type] = [hook_function]
            else:
                self._hooks[queue_name][hook_type].append(hook_function)

            logger.info(
                f"[Router] Hook已注册: 队列={queue_name}, "
                f"类型={hook_type.value}, "
                f"当前数量={len(self._hooks[queue_name][hook_type])}"
            )

    async def unregister_hook(
        self,
        queue_name: str,
        hook_function: Optional[Callable] = None,
        hook_type: Optional[AsyncHookType] = None
    ) -> int:
        """
        从指定队列注销Hook函数

        Args:
            queue_name: 队列名称
            hook_function: 要注销的Hook函数（如果为None，则根据hook_type注销所有）
            hook_type: Hook类型（如果为None，则注销所有类型的Hook）

        Returns:
            int: 注销的Hook数量
        """
        async with self._lock:
            if queue_name not in self._hooks:
                return 0

            removed_count = 0

            # 如果指定了hook_type
            if hook_type is not None:
                if hook_type in self._hooks[queue_name]:
                    hooks = self._hooks[queue_name][hook_type]
                    if hook_function is None:
                        # 注销该类型的所有Hook
                        removed_count = len(hooks)
                        del self._hooks[queue_name][hook_type]
                    else:
                        # 注销指定的Hook函数
                        try:
                            hooks.remove(hook_function)
                            removed_count = 1
                            if not hooks:  # 如果列表为空，删除该类型
                                del self._hooks[queue_name][hook_type]
                        except ValueError:
                            pass  # Hook函数不存在
            else:
                # 注销所有类型的Hook
                if hook_function is None:
                    for hooks in self._hooks[queue_name].values():
                        removed_count += len(hooks)
                    del self._hooks[queue_name]
                else:
                    # 在所有类型中查找并注销指定的Hook函数
                    for hook_type_key, hooks in list(self._hooks[queue_name].items()):
                        try:
                            hooks.remove(hook_function)
                            removed_count += 1
                            if not hooks:  # 如果列表为空，删除该类型
                                del self._hooks[queue_name][hook_type_key]
                        except ValueError:
                            pass  # Hook函数不存在

            logger.debug(f"从队列 {queue_name} 注销了 {removed_count} 个Hook")
            return removed_count

    async def execute_hooks(
        self,
        impulse: Any,
        queue_name: str,
        hook_type: AsyncHookType = AsyncHookType.PRE_PROCESS
    ) -> Any:
        """
        执行指定队列和类型的所有Hooks

        Args:
            impulse: 神经脉冲或消息
            queue_name: 队列名称
            hook_type: Hook类型

        Returns:
            Any: 处理后的脉冲
        """
        hooks = self._hooks.get(queue_name, {}).get(hook_type, [])

        if not hooks:
            return impulse

        start_time = time.time()

        try:
            # 并行执行异步Hooks
            tasks = []
            for hook in hooks:
                if asyncio.iscoroutinefunction(hook):
                    # 异步Hook函数
                    tasks.append(hook(impulse, queue_name))
                elif isinstance(hook, AsyncBaseHook):
                    # AsyncBaseHook实例
                    tasks.append(hook.execute_async(impulse, queue_name))
                else:
                    # 同步Hook函数，在线程池中执行
                    tasks.append(asyncio.to_thread(hook, impulse, queue_name))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 处理结果
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"[Router] Hook执行失败: {result}, "
                            f"Hook={hooks[i]}, Queue={queue_name}"
                        )
                        self._performance_metrics['total_hook_errors'] += 1
                    elif result is not None:
                        # 使用最后一个非None结果
                        impulse = result

                self._performance_metrics['total_hooks_executed'] += len(tasks)

            # 记录执行时间
            execution_time = time.time() - start_time

            # 更新性能指标（只保留最近100次）
            if queue_name not in self._performance_metrics['hook_execution_times']:
                self._performance_metrics['hook_execution_times'][queue_name] = {}

            hook_times = self._performance_metrics['hook_execution_times'][queue_name]
            if hook_type.value not in hook_times:
                hook_times[hook_type.value] = []

            hook_times[hook_type.value].append(execution_time)
            if len(hook_times[hook_type.value]) > 100:
                hook_times[hook_type.value].pop(0)

        except Exception as e:
            logger.error(
                f"[Router] 执行{hook_type.value} Hook时出错: {e}",
                exc_info=True
            )
            self._performance_metrics['total_hook_errors'] += 1

        return impulse

    def get_queue_priority(self, queue_name: str) -> Optional[QueuePriority]:
        """获取队列优先级

        Args:
            queue_name: 队列名称

        Returns:
            QueuePriority: 队列优先级，如果队列不存在则返回None
        """
        return self._queue_priorities.get(queue_name)

    def set_queue_priority(self, queue_name: str, priority: QueuePriority) -> bool:
        """设置队列优先级

        Args:
            queue_name: 队列名称
            priority: 新的优先级

        Returns:
            bool: 是否设置成功
        """
        if queue_name not in self._queues:
            logger.error(f"队列 {queue_name} 不存在")
            return False

        old_priority = self._queue_priorities.get(queue_name)
        self._queue_priorities[queue_name] = priority
        logger.debug(f"队列 {queue_name} 优先级从 {old_priority.name if old_priority else 'None'} 更改为 {priority.name}")
        return True

    def get_queue_sizes(self) -> Dict[str, int]:
        """获取所有队列的当前大小

        Returns:
            Dict[str, int]: 队列名称到大小的映射
        """
        sizes = {}
        for name, queue in self._queues.items():
            sizes[name] = queue.size()
        return sizes

    def get_hooks(
        self,
        queue_name: str,
        hook_type: Optional[AsyncHookType] = None
    ) -> List[Callable]:
        """
        获取指定队列的Hooks

        Args:
            queue_name: 队列名称
            hook_type: Hook类型（如果为None，返回所有类型的Hooks）

        Returns:
            List[Callable]: Hook列表
        """
        if queue_name not in self._hooks:
            return []

        if hook_type is None:
            # 返回所有类型的Hooks
            all_hooks = []
            for hooks in self._hooks[queue_name].values():
                all_hooks.extend(hooks)
            return all_hooks
        else:
            return self._hooks[queue_name].get(hook_type, [])

    async def get_metrics(self) -> Dict[str, Any]:
        """获取所有组件指标（从内存）"""
        # 获取所有队列的指标（异步）
        queue_metrics = {}
        for queue_id, queue in self._queues.items():
            metrics = await queue.get_metrics()
            queue_metrics[queue_id] = metrics.metrics

        # 获取所有工作器的统计（异步）
        worker_metrics = {}
        for worker_id, worker in self._workers.items():
            stats = await worker.get_stats()
            worker_metrics[worker_id] = stats.metrics

        return {
            "router": self._metrics.metrics,
            "queues": queue_metrics,
            "workers": worker_metrics,
            "performance": self._performance_metrics
        }

    async def update_worker_utilization(self, queue_name: str, utilization: float):
        """更新Worker利用率数据

        Args:
            queue_name: 队列名称
            utilization: 利用率（0.0-1.0）
        """
        async with self._lock:
            if queue_name not in self._performance_metrics['worker_utilization']:
                self._performance_metrics['worker_utilization'][queue_name] = []

            # 限制列表大小，避免无限增长
            self._performance_metrics['worker_utilization'][queue_name].append(utilization)
            if len(self._performance_metrics['worker_utilization'][queue_name]) > 1000:
                self._performance_metrics['worker_utilization'][queue_name].pop(0)

    def get_queue(self, queue_id: str) -> Optional[AsyncSynapticQueue]:
        """获取队列"""
        return self._queues.get(queue_id)

    def get_worker(self, worker_id: str) -> Optional[AsyncAxonWorker]:
        """获取Worker"""
        return self._workers.get(worker_id)

    @property
    def metrics(self) -> RouterMetrics:
        """获取路由器指标"""
        return self._metrics

    async def activate(self):
        """
        激活神经系统，创建所有强制性队列
        """
        async with self._lock:
            if self._router_active:
                logger.warning("神经系统已经激活")
                return

            # 创建所有强制性队列
            for queue_name, queue_config in self.MANDATORY_QUEUES.items():
                if queue_name not in self._queues:
                    priority = queue_config['priority']
                    await self.create_queue_async(
                        queue_name,
                        priority=priority,
                        enable_wal=False  # 默认不启用WAL
                    )
                    logger.debug(f"创建强制性队列: {queue_name}")

            self._router_active = True
            logger.info(f"[Router] {self.router_id} 神经系统已激活")

            # 启动利用率收集任务
            await self.start_utilization_collector(interval=30.0)

    async def start_utilization_collector(self, interval: float = 30.0):
        """启动Worker利用率收集任务（异步版本）

        Args:
            interval: 收集间隔（秒）
        """
        import asyncio

        async def collect_loop():
            while self._router_active:
                try:
                    # 遍历所有Worker
                    for worker_id, worker in list(self._workers.items()):
                        util = worker.get_utilization()
                        queue_name = worker.input_queue.queue_id
                        await self.update_worker_utilization(queue_name, util)

                    await asyncio.sleep(interval)
                except Exception as e:
                    logger.error(f"收集利用率时出错: {e}")
                    await asyncio.sleep(interval)

        # 创建后台任务
        asyncio.create_task(collect_loop())
        logger.info(f"Worker利用率收集任务已启动，间隔{interval}秒")

    async def create_queue_async(
        self,
        queue_name: str,
        priority: QueuePriority = QueuePriority.NORMAL,
        max_size: int = 0,
        enable_wal: bool = False
    ) -> AsyncSynapticQueue:
        """
        异步创建队列

        Args:
            queue_name: 队列名称
            priority: 队列优先级
            max_size: 最大大小
            enable_wal: 是否启用WAL

        Returns:
            AsyncSynapticQueue: 创建的队列
        """
        queue = AsyncSynapticQueue(
            queue_id=queue_name,
            max_size=max_size,
            enable_wal=enable_wal
        )
        await queue.start()
        self.register_queue(queue)
        return queue

    async def _setup_builtin_handlers(self):
        """设置内置处理器"""
        # Done处理器
        async def handle_done(impulse, source_queue):
            logger.debug(f"消息已终止: {impulse.session_id}")
            return impulse

        await self.register_hook("Q_DONE", handle_done, AsyncHookType.PRE_PROCESS)
        await self.start_workers_async("Q_DONE", 1)

        # 错误处理器
        async def handle_error(impulse, source_queue):
            error_message = impulse.metadata.get('error_message', 'Unknown error')
            error_source = impulse.metadata.get('original_source', 'Unknown')
            logger.error(
                f"错误处理器接收到的错误 - 来源: {error_source}, "
                f"消息: {error_message}"
            )
            impulse.action_intent = "Done"
            return impulse

        await self.register_hook(
            "Q_ERROR_HANDLER",
            handle_error,
            AsyncHookType.PRE_PROCESS
        )
        await self.start_workers_async("Q_ERROR_HANDLER", 1)

    async def setup_business_handlers(
        self,
        business_handler=None,
        response_handler=None
    ):
        """
        设置业务处理器

        Args:
            business_handler: 业务逻辑处理函数
            response_handler: 响应处理函数
        """
        if business_handler:
            await self.create_queue_async(
                "Q_PROCESS_INPUT",
                QueuePriority.HIGH,
                enable_wal=False
            )
            await self.register_hook(
                "Q_PROCESS_INPUT",
                business_handler,
                AsyncHookType.PRE_PROCESS
            )
            await self.start_workers_async("Q_PROCESS_INPUT", 1)

        if response_handler:
            await self.create_queue_async(
                "Q_RESPONSE_SINK",
                QueuePriority.NORMAL,
                enable_wal=False
            )
            await self.register_hook(
                "Q_RESPONSE_SINK",
                response_handler,
                AsyncHookType.POST_PROCESS
            )
            await self.start_workers_async("Q_RESPONSE_SINK", 1)

    async def auto_setup(
        self,
        business_handler=None,
        response_handler=None
    ):
        """
        一键自动设置整个神经系统

        Args:
            business_handler: 业务逻辑处理函数
            response_handler: 响应处理函数
        """
        logger.info(f"[Router] {self.router_id} 开始自动设置异步神经系统...")

        # 激活系统
        await self.activate()

        # 设置内置处理器
        await self._setup_builtin_handlers()

        # 设置业务处理器
        await self.setup_business_handlers(business_handler, response_handler)

        logger.info(f"[Router] {self.router_id} 异步神经系统自动设置完成")

    async def inject_input(self, impulse: NeuralImpulse, enable_audit: bool = True) -> bool:
        """
        注入神经脉冲到系统（主要入口点）

        根据设计文档 v0.1 要求，所有外部输入的消息必须经过 Q_AUDIT_INPUT 审查。

        Args:
            impulse: 神经脉冲
            enable_audit: 是否启用输入审计（默认True，符合安全设计）

        Returns:
            bool: True表示成功
        """
        if not self._router_active:
            logger.error("神经系统未激活，无法注入神经脉冲")
            return False

        if not hasattr(impulse, 'action_intent') or not impulse.action_intent:
            logger.warning("消息缺少action_intent，无法路由")
            return False

        # 添加初始处理节点记录
        impulse.add_to_history("INPUT_GATEWAY")
        impulse.metadata['queue_timestamp'] = time.time()

        # 强制性审计流程：所有消息必须先经过 Q_AUDIT_INPUT
        if enable_audit and 'Q_AUDIT_INPUT' in self._queues:
            # 保存原始目标队列
            original_intent = impulse.action_intent
            impulse.metadata['original_action_intent'] = original_intent

            # 强制路由到审计队列
            impulse.action_intent = 'Q_AUDIT_INPUT'
            success = await self.route_message(impulse, 'Q_AUDIT_INPUT')

            if success:
                logger.debug(
                    f"[Router] 消息已发送到 Q_AUDIT_INPUT 审查, "
                    f"session_id={impulse.session_id}"
                )

            return success
        else:
            # 如果未启用审计或审计队列不存在，直接路由
            if not enable_audit:
                logger.warning(
                    f"[Router] 输入审计未启用，消息绕过 Q_AUDIT_INPUT "
                    f"(不推荐，违反安全设计) session_id={impulse.session_id}"
                )
            else:
                logger.warning(
                    f"[Router] Q_AUDIT_INPUT 队列不存在，无法执行输入审计 "
                    f"session_id={impulse.session_id}"
                )

            # 安全验证
            if not await self._validate_sink_security(impulse):
                logger.error("安全验证失败")
                return False

            # 路由消息
            success = await self.route_message(impulse, impulse.action_intent)

            if success:
                self._metrics.total_messages_routed += 1

            return success

    async def batch_route(
        self,
        messages: List[Tuple[Any, str]],
        timeout: Optional[float] = None
    ) -> int:
        """
        批量路由消息

        Args:
            messages: [(message, pattern), ...] 列表
            timeout: 总超时时间

        Returns:
            int: 成功路由的数量
        """
        success_count = 0
        start_time = time.time()

        for message, pattern in messages:
            # 检查总超时
            if timeout and (time.time() - start_time) > timeout:
                break

            result = await self.route_message(message, pattern)
            if result:
                success_count += 1

        return success_count

    async def start_workers_async(
        self,
        queue_name: str,
        num_workers: int = 1
    ) -> List['AsyncAxonWorker']:
        """
        为指定队列启动工作器

        Args:
            queue_name: 队列名称
            num_workers: 工作器数量

        Returns:
            List[AsyncAxonWorker]: 启动的工作器列表
        """
        if queue_name not in self._queues:
            raise ValueError(f"队列 {queue_name} 不存在")

        queue = self._queues[queue_name]
        workers = []

        for i in range(num_workers):
            worker = AsyncAxonWorker(
                name=f"{queue_name}_worker_{i}",
                input_queue=queue,
                router=self  # 传入router引用
            )
            await worker.start()
            self.register_worker(worker)
            workers.append(worker)

        logger.info(f"[Router] 为队列 {queue_name} 启动了 {num_workers} 个工作器")
        return workers

    async def stop_all_workers(self):
        """停止所有工作器"""
        tasks = [worker.stop() for worker in self._workers.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"[Router] 停止了 {len(self._workers)} 个工作器")

    async def adjust_workers(
        self,
        queue_id: str,
        target_count: int
    ) -> Dict[str, int]:
        """
        动态调整指定队列的Worker数量

        Args:
            queue_id: 队列ID
            target_count: 目标Worker数量

        Returns:
            Dict[str, int]: 调整结果 {"before": X, "after": Y, "added": Z, "removed": W}

        Raises:
            ValueError: 队列不存在
        """
        async with self._lock:
            if queue_id not in self._queues:
                raise ValueError(f"队列 {queue_id} 不存在")

            # 获取当前队列的所有Worker
            current_workers = [
                worker for worker in self._workers.values()
                if worker.input_queue.queue_id == queue_id
            ]
            current_count = len(current_workers)

            adjustment = target_count - current_count

            if adjustment == 0:
                return {
                    "before": current_count,
                    "after": current_count,
                    "added": 0,
                    "removed": 0
                }

            if adjustment > 0:
                # 扩容：增加Worker
                new_workers = await self.start_workers_async(queue_id, adjustment)
                logger.debug(f"[Router] 为队列 {queue_id} 增加了 {adjustment} 个工作器")
            else:
                # 缩容：减少Worker
                workers_to_stop = abs(adjustment)
                workers_to_remove = current_workers[:workers_to_stop]

                for worker in workers_to_remove:
                    await worker.stop()
                    # 从workers字典中移除
                    self._workers.pop(worker.worker_id, None)

                logger.debug(f"[Router] 为队列 {queue_id} 减少了 {workers_to_stop} 个工作器")

            return {
                "before": current_count,
                "after": target_count,
                "added": max(0, adjustment),
                "removed": max(0, -adjustment)
            }

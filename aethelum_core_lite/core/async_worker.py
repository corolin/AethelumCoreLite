"""
异步Worker实现

专为AI Agent I/O密集型场景设计的异步工作器。
"""

import asyncio
import logging
import time
import uuid
from typing import Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field, replace
from enum import Enum
import copy

from ..hooks.base_hook import BaseHook

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .async_queue import AsyncSynapticQueue
    from .async_router import AsyncNeuralSomaRouter
    from .message import NeuralImpulse


class AsyncWorkerState(Enum):
    """异步工作器状态"""
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
class AsyncWorkerStats:
    """异步工作器统计信息"""
    worker_id: str
    name: str
    state: AsyncWorkerState = AsyncWorkerState.INITIALIZING
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    processed_messages: int = 0
    failed_messages: int = 0
    total_processing_time: float = 0.0
    average_processing_time: float = 0.0
    success_rate: float = 0.0
    error_counts: dict = field(default_factory=dict)
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    recovery_attempts: int = 0
    consecutive_failures: int = 0
    health_score: float = 100.0
    uptime: float = 0.0
    utilization: float = 0.0  # 当前利用率（0.0-1.0）
    # 指标存储（供API查询）
    labels: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


class AsyncAxonWorker:
    """异步轴突工作器 - 专为AI Agent I/O场景设计"""

    def __init__(self,
                 name: str,
                 input_queue: 'AsyncSynapticQueue',
                 hooks: Optional[List[BaseHook]] = None,
                 worker_id: Optional[str] = None,
                 router: Optional['AsyncNeuralSomaRouter'] = None,
                 max_consecutive_failures: int = 5,
                 recovery_delay: float = 5.0,
                 health_check_interval: float = 30.0,
                 processing_timeout: float = 60.0):
        self.name = name
        self.worker_id = worker_id or str(uuid.uuid4())
        self.input_queue = input_queue
        self.hooks = hooks or []
        self.router = router  # Router引用，用于获取Hooks
        self.max_consecutive_failures = max_consecutive_failures
        self.recovery_delay = recovery_delay
        self.health_check_interval = health_check_interval
        self.processing_timeout = processing_timeout

        # 状态管理
        self._state = AsyncWorkerState.INITIALIZING
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 默认可运行
        self._task: Optional[asyncio.Task] = None

        # 保护状态的并发访问
        self._state_lock = asyncio.Lock()

        # 统计信息（内存存储）
        self._stats = AsyncWorkerStats(
            worker_id=self.worker_id,
            name=name,
            state=self._state,
            labels={
                "worker_id": self.worker_id,
                "worker_name": self.name,
                "queue_id": input_queue.queue_id
            }
        )
        self._consecutive_failures = 0

        # 保护统计信息的并发访问
        self._stats_lock = asyncio.Lock()

        # 错误类型映射
        self._error_type_mapping = {
            ValueError: ErrorType.VALIDATION_ERROR,
            RuntimeError: ErrorType.PROCESSING_ERROR,
            KeyError: ErrorType.ROUTING_ERROR,
            asyncio.QueueEmpty: ErrorType.QUEUE_ERROR,
            AttributeError: ErrorType.HOOK_ERROR,
            OSError: ErrorType.SYSTEM_ERROR,
            asyncio.TimeoutError: ErrorType.TIMEOUT_ERROR
        }

    async def start(self):
        """启动工作器（带并发保护）"""
        async with self._state_lock:
            if self._state in (AsyncWorkerState.RUNNING, AsyncWorkerState.STOPPING):
                logger.warning(f"[Worker] {self.name} already starting or running")
                return

            self._state = AsyncWorkerState.RUNNING
            self._task = asyncio.create_task(self._run_loop())
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info(f"[Worker] {self.name} started")

    async def stop(self):
        """停止工作器（带并发保护）"""
        async with self._state_lock:
            if self._state == AsyncWorkerState.STOPPED:
                logger.warning(f"[Worker] {self.name} already stopped")
                return

            self._state = AsyncWorkerState.STOPPING

        # 在锁外执行停止操作（避免死锁）
        self._stop_event.set()

        # 停止健康检查任务
        if hasattr(self, '_health_check_task') and self._health_check_task:
            try:
                await asyncio.wait_for(self._health_check_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"[Worker] {self.name} stop timeout, cancelling task")
                self._task.cancel()

        # 重新获取锁来更新状态
        async with self._state_lock:
            self._state = AsyncWorkerState.STOPPED
        logger.info(f"[Worker] {self.name} stopped")

    async def pause(self):
        """暂停工作器（带并发保护）"""
        async with self._state_lock:
            self._pause_event.clear()
            self._state = AsyncWorkerState.PAUSED

    async def resume(self):
        """恢复工作器（带并发保护）"""
        async with self._state_lock:
            self._pause_event.set()
            self._state = AsyncWorkerState.RUNNING

    async def _run_loop(self):
        """主处理循环"""
        while not self._stop_event.is_set():
            try:
                # 等待暂停事件
                await self._pause_event.wait()

                # 从队列获取消息（带超时）
                impulse = await asyncio.wait_for(
                    self.input_queue.async_get(),
                    timeout=1.0
                )

                # 处理消息
                await self._process_impulse(impulse)

            except asyncio.TimeoutError:
                continue  # 超时继续
            except Exception as e:
                logger.error(f"[Worker] {self.name} error in _run_loop: {e}")
                async with self._stats_lock:
                    self._consecutive_failures += 1

                    if self._consecutive_failures >= self.max_consecutive_failures:
                        async with self._state_lock:
                            self._state = AsyncWorkerState.ERROR
                        break

    async def _process_impulse(self, impulse: 'NeuralImpulse'):
        """处理神经脉冲（核心I/O密集型逻辑）"""
        start_time = time.time()

        try:
            # Q_AUDIT 安全验证
            self._validate_sink_security(impulse)

            # 执行Pre-Hooks（优先使用Router的Hooks）
            await self._execute_hooks_async(impulse, "pre")

            # 核心处理逻辑（I/O密集型）
            await self._process_core_logic(impulse)

            # 执行Post-Hooks（优先使用Router的Hooks）
            await self._execute_hooks_async(impulse, "post")

            # 异步更新指标到内存
            processing_time = time.time() - start_time
            await self._update_metrics_async(success=True, duration=processing_time)

        except Exception as e:
            # 映射错误类型
            error_type = self._map_exception_to_error_type(e)

            logger.error(f"[Worker] {self.name} failed to process impulse: {e}")

            # 更新错误统计
            async with self._stats_lock:
                error_type_str = error_type.value if error_type else "unknown"
                self._stats.error_counts[error_type_str] = self._stats.error_counts.get(error_type_str, 0) + 1
                self._stats.last_error = str(e)
                self._stats.last_error_time = time.time()

            # 检查是否需要进入恢复模式
            if self._consecutive_failures >= self.max_consecutive_failures:
                await self._enter_recovery_mode()

            await self._update_metrics_async(success=False, duration=0.0)

            # 执行Error-Hooks（优先使用Router的Hooks）
            await self._execute_hooks_async(impulse, "error", exception=e)

    async def _update_metrics_async(self, success: bool, duration: float):
        """异步更新指标到内存（带并发保护）"""
        async with self._stats_lock:
            if success:
                self._stats.processed_messages += 1
                self._stats.total_processing_time += duration
                if self._stats.processed_messages > 0:
                    self._stats.average_processing_time = (
                        self._stats.total_processing_time / self._stats.processed_messages
                    )
                self._consecutive_failures = 0
            else:
                self._stats.failed_messages += 1
                self._consecutive_failures += 1

            # 计算健康分数
            total = self._stats.processed_messages + self._stats.failed_messages
            if total > 0:
                self._stats.success_rate = (self._stats.processed_messages / total) * 100
                self._stats.health_score = max(0, 100 - self._consecutive_failures * 10)

            # 更新metrics字典（供API查询）
            self._stats.metrics = {
                "worker_id": self.worker_id,
                "worker_name": self.name,
                "queue_id": self._stats.labels.get("queue_id", ""),
                "processed_messages": self._stats.processed_messages,
                "failed_messages": self._stats.failed_messages,
                "average_processing_time": self._stats.average_processing_time,
                "health_score": self._stats.health_score,
                "success_rate": self._stats.success_rate
            }

    async def _process_core_logic(self, impulse: 'NeuralImpulse'):
        """
        核心处理逻辑 - I/O密集型操作

        典型场景：
        1. 调用AI API（OpenAI、Claude等）
        2. 向量数据库检索（RAG）
        3. 文件读写
        4. 数据库操作
        """
        # 示例：模拟AI API调用
        # response = await openai_client.acomplete(...)
        # result = await vector_store.query(...)

        await asyncio.sleep(0.1)  # 模拟I/O等待

    async def _execute_hooks_async(self,
                                   impulse: 'NeuralImpulse',
                                   hook_stage: str,
                                   exception: Optional[Exception] = None):
        """
        异步执行Hooks

        优先使用Router的Hooks，如果没有Router则使用自身的Hooks。

        Args:
            impulse: 神经脉冲
            hook_stage: Hook阶段（"pre", "post", "error"）
            exception: 异常对象（仅error阶段使用）
        """
        # 如果有Router，优先从Router获取Hooks
        if self.router:
            from .async_hooks import AsyncHookType

            # 映射hook_stage到AsyncHookType
            hook_type_map = {
                "pre": AsyncHookType.PRE_PROCESS,
                "post": AsyncHookType.POST_PROCESS,
                "error": AsyncHookType.ERROR_HANDLER
            }

            hook_type = hook_type_map.get(hook_stage)
            if hook_type:
                impulse = await self.router.execute_hooks(
                    impulse,
                    self.input_queue.queue_id,
                    hook_type
                )

        # 执行Worker自身的Hooks（兼容旧代码）
        hooks = [h for h in self.hooks if getattr(h, f"is_{hook_stage}_hook", False)]

        if not hooks:
            return

        # 并行执行Hooks（如果Hook支持异步）
        tasks = []
        for hook in hooks:
            if hasattr(hook, 'execute_async'):
                task = hook.execute_async(impulse, self.input_queue.queue_id)
                tasks.append(task)
            elif asyncio.iscoroutinefunction(hook):
                task = hook(impulse, self.input_queue.queue_id)
                tasks.append(task)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"[Worker] {self.name} hook execution failed: {result}")

    def _validate_sink_security(self, impulse):
        """验证SINK安全

        根据设计文档 v0.1 要求，Q_RESPONSE_SINK 的 Worker 必须验证消息是否经过 Q_AUDIT_OUTPUT 审查。
        这是强制性安全检查，防止消息绕过输出审查直接进入响应队列。

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
                    f"[Security Violation] Message routed to Q_RESPONSE_SINK without Q_AUDIT_OUTPUT audit!\n"
                    f"Message Source: {impulse.source_agent}\n"
                    f"Routing History: {impulse.routing_history}\n"
                    f"Session ID: {impulse.session_id}\n"
                    f"According to design doc v0.1 section 4.2, all messages entering Q_RESPONSE_SINK must pass through Q_AUDIT_OUTPUT audit."
                )

    def _map_exception_to_error_type(self, exception: Exception) -> Optional[ErrorType]:
        """将异常映射到错误类型"""
        exception_type = type(exception)
        return self._error_type_mapping.get(exception_type, ErrorType.SYSTEM_ERROR)

    async def _enter_recovery_mode(self):
        """进入恢复模式（带并发保护）

        状态管理：
        - _state: 内部控制状态
        - _stats.state: 外部报告状态
        两者保持一致，确保恢复期间状态正确
        """
        async with self._state_lock:
            self._state = AsyncWorkerState.RECOVERING
            self._stats.state = self._state
            self._stats.recovery_attempts += 1
            consecutive_failures = self._stats.consecutive_failures

        logger.warning(f"Worker {self.name} entering recovery mode after {consecutive_failures} consecutive failures")

        # 等待恢复延迟
        await asyncio.sleep(self.recovery_delay)

        # 重置连续失败计数和恢复状态（使用锁保护）
        async with self._state_lock:
            self._stats.consecutive_failures = 0
            self._state = AsyncWorkerState.RUNNING
            self._stats.state = self._state

        logger.info(f"Worker {self.name} recovered and resuming operation")

    async def _health_check_loop(self):
        """健康检查循环（带并发保护）"""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.health_check_interval)

                # 计算健康分数
                await self._calculate_health_score()

                # 检查是否需要干预（使用锁保护）
                async with self._stats_lock:
                    health_score = self._stats.health_score

                if health_score < 30.0:
                    logger.warning(f"[Worker] {self.name} health score is low: {health_score}")

            except asyncio.CancelledError:
                # 任务被取消，退出循环
                break
            except Exception as e:
                logger.error(f"[Worker] {self.name} error in health check loop: {e}")

    async def _calculate_health_score(self):
        """计算健康分数（带并发保护）"""
        async with self._stats_lock:
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

    async def get_stats(self) -> AsyncWorkerStats:
        """获取统计信息（从内存，返回副本防止外部修改）"""
        async with self._stats_lock:
            # 使用 replace 创建副本，避免外部修改内部状态
            return replace(
                self._stats,
                labels=copy.deepcopy(self._stats.labels),
                metrics=copy.deepcopy(self._stats.metrics)
            )

    def get_utilization(self) -> float:
        """获取当前Worker利用率

        利用率 = 处理时间 / 总运行时间

        Returns:
            float: 利用率（0.0-1.0）
        """
        # 获取 _stats_lock 的方式需要适配
        if hasattr(self, '_stats_lock'):
            # 使用同步方式获取锁（如果可用）
            import threading
            if isinstance(self._stats_lock, threading.Lock):
                with self._stats_lock:
                    total_time = time.time() - self._stats.start_time
                    if total_time == 0:
                        return 0.0
                    utilization = self._stats.total_processing_time / total_time
                    self._stats.utilization = utilization
                    return utilization

        # 异步版本：直接访问（假设调用方已经持有锁或状态是线程安全的）
        total_time = time.time() - self._stats.start_time
        if total_time == 0:
            return 0.0
        utilization = self._stats.total_processing_time / total_time
        self._stats.utilization = utilization
        return utilization

    @property
    def state(self) -> AsyncWorkerState:
        """获取当前状态"""
        return self._state

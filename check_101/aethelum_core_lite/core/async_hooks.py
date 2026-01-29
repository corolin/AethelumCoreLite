"""
异步Hook系统

提供异步Hook函数的基础抽象类和工具函数。
与同步版本的Hooks模块对应，但使用AsyncIO实现。
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable, List, Union
from enum import Enum
from .message import NeuralImpulse


class AsyncHookType(Enum):
    """异步Hook类型枚举"""
    PRE_PROCESS = "pre_process"      # 预处理Hook
    POST_PROCESS = "post_process"     # 后处理Hook
    ERROR_HANDLER = "error_handler"   # 错误处理Hook
    TRANSFORM = "transform"          # 转换Hook


class AsyncBaseHook(ABC):
    """
    异步基础钩子抽象类

    定义了所有异步Hook函数必须实现的接口，提供通用的Hook功能。
    与同步版本BaseHook对应，但使用AsyncIO实现。
    """

    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        """
        初始化异步基础钩子

        Args:
            hook_name: Hook名称
            enable_logging: 是否启用日志记录
            priority: Hook优先级（0-100，数值越小优先级越高）
        """
        self.hook_name = hook_name
        self.enabled = True
        self.priority = priority
        self.logger = logging.getLogger(f"async_hook.{hook_name}")
        self.hook_type = "async_base"

        # 异步锁，用于统计信息的线程安全更新
        self._lock = asyncio.Lock()

        # 统计信息
        self._stats = {
            'total_processed': 0,
            'total_errors': 0,
            'total_skipped': 0,
            'avg_processing_time': 0.0,
            'last_processed_at': None,
            'execution_count': 0,
            'total_execution_time': 0.0
        }

    @abstractmethod
    async def process_async(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        异步处理神经脉冲的抽象方法

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现process_async方法")

    async def __call__(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        使Hook函数可调用

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        return await self.execute_async(impulse, source_queue)

    async def execute_async(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        异步执行Hook函数，包含错误处理和统计

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        if not self.enabled:
            self.logger.debug(f"Hook {self.hook_name} 已禁用，跳过处理")
            async with self._lock:
                self._stats['total_skipped'] += 1
            return impulse

        start_time = time.time()

        try:
            # 调用子类实现的异步处理方法
            result = await self.process_async(impulse, source_queue)

            # 更新统计信息
            processing_time = time.time() - start_time
            async with self._lock:
                self._stats['total_processed'] += 1
                self._stats['execution_count'] += 1
                self._stats['total_execution_time'] += processing_time
                self._stats['avg_processing_time'] = (
                    self._stats['total_execution_time'] / self._stats['execution_count']
                )
                self._stats['last_processed_at'] = start_time

            if self.enable_logging:
                self.logger.debug(
                    f"Hook {self.hook_name} 处理完成，耗时: {processing_time:.4f}s"
                )

            return result

        except Exception as e:
            # 错误处理
            self.logger.error(
                f"Hook {self.hook_name} 执行失败: {e}",
                exc_info=True
            )

            async with self._lock:
                self._stats['total_errors'] += 1

            # 将错误信息添加到脉冲元数据
            impulse.metadata[f'hook_error_{self.hook_name}'] = {
                'error': str(e),
                'hook_name': self.hook_name,
                'source_queue': source_queue,
                'timestamp': time.time()
            }

            return impulse

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取Hook统计信息（线程安全）

        Returns:
            Dict[str, Any]: 统计信息副本
        """
        async with self._lock:
            return self._stats.copy()

    def enable(self):
        """启用Hook"""
        self.enabled = True
        self.logger.info(f"Hook {self.hook_name} 已启用")

    def disable(self):
        """禁用Hook"""
        self.enabled = False
        self.logger.info(f"Hook {self.hook_name} 已禁用")


class AsyncPreHook(AsyncBaseHook):
    """
    异步前置Hook

    在主处理逻辑之前执行的Hook。
    """

    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "pre_process"


class AsyncPostHook(AsyncBaseHook):
    """
    异步后置Hook

    在主处理逻辑之后执行的Hook。
    """

    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "post_process"


class AsyncErrorHook(AsyncBaseHook):
    """
    异步错误Hook

    发生错误时执行的Hook。
    """

    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "error_handler"


class AsyncTransformHook(AsyncBaseHook):
    """
    异步转换Hook

    用于转换或修改消息内容的Hook。
    """

    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "transform"


class AsyncFilterHook(AsyncBaseHook):
    """
    异步过滤Hook

    根据条件决定是否处理消息的Hook。
    如果消息被过滤，则返回None。
    """

    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "filter"

    @abstractmethod
    async def should_process(self, impulse: NeuralImpulse, source_queue: str) -> bool:
        """
        判断是否应该处理该消息

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            bool: True表示处理，False表示跳过
        """
        raise NotImplementedError("子类必须实现should_process方法")

    async def process_async(self, impulse: NeuralImpulse, source_queue: str) -> Optional[NeuralImpulse]:
        """
        异步处理神经脉冲

        如果should_process返回False，则返回None表示过滤掉该消息。
        """
        if await self.should_process(impulse, source_queue):
            return impulse
        else:
            self.logger.debug(f"Hook {self.hook_name} 过滤了消息 {impulse.session_id}")
            return None


# 便捷创建函数

def create_async_pre_hook(hook_func: Callable) -> AsyncPreHook:
    """
    从异步函数创建PreHook

    Args:
        hook_func: 异步函数，签名为 async def func(impulse, source_queue) -> impulse

    Returns:
        AsyncPreHook: PreHook实例
    """
    class _PreHookImpl(AsyncPreHook):
        async def process_async(self, impulse, source_queue):
            return await hook_func(impulse, source_queue)

    hook_name = getattr(hook_func, '__name__', 'anonymous_pre_hook')
    return _PreHookImpl(hook_name=hook_name)


def create_async_post_hook(hook_func: Callable) -> AsyncPostHook:
    """
    从异步函数创建PostHook

    Args:
        hook_func: 异步函数，签名为 async def func(impulse, source_queue) -> impulse

    Returns:
        AsyncPostHook: PostHook实例
    """
    class _PostHookImpl(AsyncPostHook):
        async def process_async(self, impulse, source_queue):
            return await hook_func(impulse, source_queue)

    hook_name = getattr(hook_func, '__name__', 'anonymous_post_hook')
    return _PostHookImpl(hook_name=hook_name)


def create_async_error_hook(hook_func: Callable) -> AsyncErrorHook:
    """
    从异步函数创建ErrorHook

    Args:
        hook_func: 异步函数，签名为 async def func(impulse, source_queue) -> impulse

    Returns:
        AsyncErrorHook: ErrorHook实例
    """
    class _ErrorHookImpl(AsyncErrorHook):
        async def process_async(self, impulse, source_queue):
            return await hook_func(impulse, source_queue)

    hook_name = getattr(hook_func, '__name__', 'anonymous_error_hook')
    return _ErrorHookImpl(hook_name=hook_name)


def create_async_filter_hook(
    should_process_func: Callable
) -> AsyncFilterHook:
    """
    从异步函数创建FilterHook

    Args:
        should_process_func: 异步函数，签名为 async def func(impulse, source_queue) -> bool

    Returns:
        AsyncFilterHook: FilterHook实例
    """
    class _FilterHookImpl(AsyncFilterHook):
        async def should_process(self, impulse, source_queue):
            return await should_process_func(impulse, source_queue)

    hook_name = getattr(should_process_func, '__name__', 'anonymous_filter_hook')
    return _FilterHookImpl(hook_name=hook_name)


# 兼容性工具：将同步Hook包装为异步Hook

class SyncToAsyncHookWrapper(AsyncBaseHook):
    """
    将同步Hook包装为异步Hook的包装器

    允许在异步系统中使用现有的同步Hook函数。
    """

    def __init__(self, sync_hook_func: Callable, hook_name: str, hook_type: str = "pre_process"):
        """
        初始化包装器

        Args:
            sync_hook_func: 同步Hook函数
            hook_name: Hook名称
            hook_type: Hook类型
        """
        super().__init__(hook_name=hook_name)
        self.sync_hook_func = sync_hook_func
        self.hook_type = hook_type

    async def process_async(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        在线程池中执行同步Hook函数
        """
        # 在单独的线程中执行同步函数，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.sync_hook_func,
            impulse,
            source_queue
        )


def wrap_sync_hook_as_async(
    sync_hook_func: Callable,
    hook_name: Optional[str] = None,
    hook_type: str = "pre_process"
) -> AsyncBaseHook:
    """
    将同步Hook函数包装为异步Hook

    Args:
        sync_hook_func: 同步Hook函数
        hook_name: Hook名称（如果为None，使用函数名）
        hook_type: Hook类型

    Returns:
        AsyncBaseHook: 异步Hook实例

    Example:
        >>> # 同步Hook函数
        >>> def my_sync_hook(impulse, source_queue):
        ...     impulse.content = "processed"
        ...     return impulse
        >>>
        >>> # 包装为异步Hook
        >>> async_hook = wrap_sync_hook_as_async(my_sync_hook)
        >>> await async_hook.execute_async(impulse, "queue_name")
    """
    if hook_name is None:
        hook_name = getattr(sync_hook_func, '__name__', 'wrapped_sync_hook')

    return SyncToAsyncHookWrapper(sync_hook_func, hook_name, hook_type)

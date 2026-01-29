"""
异步队列实现

使用asyncio.Queue实现异步突触队列，支持优先级和WAL持久化。
"""

import asyncio
import logging
from typing import Optional, Any, List, Tuple, Dict
from dataclasses import dataclass, field, replace
from enum import Enum
import time
import uuid
import copy

from .message import MessagePriority
from ..utils.wal_writer import AsyncWALWriter

logger = logging.getLogger(__name__)


class QueuePriority(Enum):
    """队列优先级枚举"""
    CRITICAL = 1  # 关键队列，如错误处理
    HIGH = 2      # 高优先级队列
    NORMAL = 3    # 普通优先级队列
    LOW = 4       # 低优先级队列


@dataclass(order=True)
class PriorityItem:
    """优先级队列项"""
    priority: int
    item: Any = field(compare=False)


@dataclass
class QueueMetrics:
    """队列指标（内存存储）"""
    queue_id: str
    size: int = 0
    capacity: int = 0
    total_messages: int = 0
    total_dropped: int = 0
    labels: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


class AsyncSynapticQueue:
    """异步突触队列 - 使用asyncio.Queue"""

    def __init__(self,
                 queue_id: str,
                 max_size: int = 0,
                 enable_wal: bool = True,
                 wal_dir: str = "wal_data",
                 message_ttl: Optional[float] = None):
        """
        初始化异步队列

        Args:
            queue_id: 队列ID
            max_size: 最大大小（0表示无限制）
            enable_wal: 是否启用WAL持久化
            wal_dir: WAL目录
            message_ttl: 消息TTL（秒），None表示不过期
        """
        self.queue_id = queue_id
        self.max_size = max_size
        self.enable_wal = enable_wal
        self.message_ttl = message_ttl

        # asyncio.Queue（线程安全）
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)

        # 指标存储（内存）
        self._metrics = QueueMetrics(
            queue_id=queue_id,
            capacity=max_size,
            labels={
                "queue_id": queue_id
            }
        )

        # 保护metrics的并发访问
        self._metrics_lock = asyncio.Lock()

        # WAL写入器
        self._wal_writer: Optional[AsyncWALWriter] = None
        if self.enable_wal:
            self._wal_writer = AsyncWALWriter(
                queue_id=queue_id,
                wal_dir=wal_dir,
                enable_wal=enable_wal
            )

        # 消息ID映射
        self._message_map: Dict[str, Any] = {}
        self._message_lock = asyncio.Lock()

        # 后台清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 300.0  # 默认5分钟清理一次
        self._stop_event = asyncio.Event()

    async def start(self):
        """启动队列（启动WAL写入器和清理任务）"""
        if self._wal_writer:
            await self._wal_writer.start()

        # 启动后台清理任务（如果启用了TTL）
        if self.message_ttl is not None:
            self._stop_event.clear()
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info(
                f"[Queue] {self.queue_id} 清理任务已启动 "
                f"(TTL={self.message_ttl}s)"
            )

        logger.info(f"[Queue] {self.queue_id} started")

    async def clear(self):
        """清空队列中的所有消息

        移除队列中当前所有的消息。注意：这不会删除已经持久化到WAL的消息。
        """
        # 获取并丢弃所有消息
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # 更新指标
        async with self._metrics_lock:
            self._metrics.size = 0

        logger.info(f"[Queue] {self.queue_id} cleared")

    async def stop(self):
        """停止队列（停止WAL写入器和清理任务）"""
        # 取消清理任务
        if self._cleanup_task and not self._cleanup_task.done():
            self._stop_event.set()
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info(f"[Queue] {self.queue_id} 清理任务已停止")

        if self._wal_writer:
            await self._wal_writer.stop()
        logger.info(f"[Queue] {self.queue_id} stopped")

    # close() 是 stop() 的别名，用于API一致性
    close = stop

    async def async_put(self,
                       item: Any,
                       priority: MessagePriority = MessagePriority.NORMAL,
                       block: bool = True,
                       timeout: Optional[float] = None) -> bool:
        """异步放入消息（支持优先级）"""
        priority_item = PriorityItem(priority.value, item)

        # 获取消息的 message_id
        message_id = item.message_id if hasattr(item, 'message_id') else str(uuid.uuid4())

        try:
            if timeout:
                await asyncio.wait_for(
                    self._queue.put(priority_item),
                    timeout=timeout
                )
            else:
                await self._queue.put(priority_item)

            # 异步更新指标到内存
            await self._update_metrics_async(dropped=False)

            # WAL持久化 - 使用 impulse.message_id
            if self._wal_writer:
                await self._wal_writer.write_log1(message_id, priority.value, item)

            return True

        except (asyncio.TimeoutError, asyncio.QueueFull):
            await self._update_metrics_async(dropped=True)
            return False

    async def async_get(self,
                       block: bool = True,
                       timeout: Optional[float] = None) -> Any:
        """
        异步获取消息

        如果启用了TTL，会自动跳过过期消息。
        """
        try:
            while True:
                if timeout:
                    priority_item = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=timeout
                    )
                else:
                    priority_item = await self._queue.get()

                item = priority_item.item

                # 检查是否过期
                if self._is_expired(item):
                    logger.debug(
                        f"[Queue] {self.queue_id} 跳过过期消息: "
                        f"{getattr(item, 'session_id', 'unknown')}"
                    )
                    # 继续获取下一条消息
                    continue

                return item

        except asyncio.TimeoutError:
            raise

    async def _update_metrics_async(self, dropped: bool):
        """异步更新指标到内存（带并发保护）"""
        async with self._metrics_lock:
            self._metrics.size = self._queue.qsize()

            if dropped:
                self._metrics.total_dropped += 1
            else:
                self._metrics.total_messages += 1

            # 更新metrics字典
            self._metrics.metrics = {
                "size": self._metrics.size,
                "capacity": self._metrics.capacity,
                "usage_percent": (self._metrics.size / self._metrics.capacity * 100) if self._metrics.capacity > 0 else 0,
                "total_messages": self._metrics.total_messages,
                "total_dropped": self._metrics.total_dropped
            }

    async def mark_message_processed(self, message_id: str):
        """标记消息处理完成（写log2）"""
        if self._wal_writer:
            await self._wal_writer.write_log2(message_id)

    async def task_done(self):
        """标记任务完成（包装 asyncio.Queue.task_done）

        用于配合 join() 方法，表示队列中的一个任务已完成。
        """
        self._queue.task_done()

    async def join(self):
        """阻塞直到队列中所有任务都被处理（包装 asyncio.Queue.join）

        等待队列中的所有消息都被处理（即调用了相应次数的 task_done()）。
        """
        await self._queue.join()

    def size(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """判断队列是否为空"""
        return self._queue.empty()

    def full(self) -> bool:
        """判断队列是否已满"""
        return self._queue.full()

    async def get_metrics(self) -> QueueMetrics:
        """获取指标（从内存，返回副本防止外部修改）"""
        async with self._metrics_lock:
            # 使用 replace 创建副本，避免外部修改内部状态
            return replace(
                self._metrics,
                labels=copy.deepcopy(self._metrics.labels),
                metrics=copy.deepcopy(self._metrics.metrics)
            )

    async def batch_put(
        self,
        items: List[Tuple[Any, MessagePriority]],
        timeout: Optional[float] = None
    ) -> int:
        """
        批量放入消息

        Args:
            items: [(item, priority), ...] 列表
            timeout: 总超时时间

        Returns:
            int: 成功放入的数量
        """
        success_count = 0
        start_time = time.time()

        for item, priority in items:
            # 检查总超时
            if timeout and (time.time() - start_time) > timeout:
                logger.warning(
                    f"[Queue] {self.queue_id} 批量放入超时，"
                    f"已放入 {success_count}/{len(items)}"
                )
                break

            # 单个放入（不阻塞，快速失败）
            result = await self.async_put(item, priority, block=False)
            if result:
                success_count += 1
            else:
                # 队列已满，停止继续尝试
                logger.warning(
                    f"[Queue] {self.queue_id} 队列已满，"
                    f"批量放入中止于 {success_count}/{len(items)}"
                )
                break

        logger.info(
            f"[Queue] {self.queue_id} 批量放入完成: "
            f"{success_count}/{len(items)} 成功"
        )
        return success_count

    async def batch_get(
        self,
        count: int,
        timeout: Optional[float] = None
    ) -> List[Any]:
        """
        批量获取消息

        Args:
            count: 获取数量
            timeout: 总超时时间

        Returns:
            List[Any]: 消息列表
        """
        messages = []
        start_time = time.time()

        for _ in range(count):
            # 检查总超时
            if timeout and (time.time() - start_time) > timeout:
                logger.debug(
                    f"[Queue] {self.queue_id} 批量获取超时，"
                    f"已获取 {len(messages)}/{count}"
                )
                break

            # 计算单个操作的超时时间
            remaining_timeout = None
            if timeout:
                remaining_timeout = timeout - (time.time() - start_time)
                if remaining_timeout <= 0:
                    break

            try:
                # 尝试获取消息
                message = await self.async_get(
                    block=True,
                    timeout=remaining_timeout
                )
                messages.append(message)
            except asyncio.TimeoutError:
                # 超时，停止继续获取
                break

        logger.debug(
            f"[Queue] {self.queue_id} 批量获取完成: "
            f"{len(messages)}/{count}"
        )
        return messages

    def _is_expired(self, item: Any) -> bool:
        """
        检查消息是否过期

        Args:
            item: 消息对象

        Returns:
            bool: True表示已过期
        """
        if self.message_ttl is None:
            return False

        # 从item中提取时间戳
        if hasattr(item, 'metadata'):
            queue_timestamp = item.metadata.get("queue_timestamp", time.time())
            return (time.time() - queue_timestamp) > self.message_ttl

        return False

    async def get_expired_messages(self) -> List[Any]:
        """获取所有过期消息（不删除）

        Returns:
            List[Any]: 过期消息列表
        """
        expired = []

        # 遍历消息映射检查过期
        async with self._message_lock:
            for message_id, item in self._message_map.items():
                if self._is_expired(item):
                    expired.append(item)

        return expired

    async def remove_expired_messages(self) -> int:
        """
        移除所有过期消息

        Returns:
            int: 移除的消息数量
        """
        if self.message_ttl is None:
            return 0

        expired_count = 0
        current_time = time.time()

        # 创建新队列（需要遍历，因为asyncio.Queue不支持直接遍历）
        temp_queue = asyncio.Queue(maxsize=self.max_size)

        # 将未过期的消息移到临时队列
        while not self._queue.empty():
            try:
                priority_item = self._queue.get_nowait()
                impulse = priority_item.item

                # 检查是否过期
                if not self._is_expired(impulse):
                    await temp_queue.put(priority_item)
                else:
                    # 过期，移除
                    if hasattr(impulse, 'metadata') and 'message_id' in impulse.metadata:
                        message_id = impulse.metadata['message_id']
                        async with self._message_lock:
                            if message_id in self._message_map:
                                del self._message_map[message_id]
                    expired_count += 1

                    # 标记为已处理（写log2）
                    if hasattr(impulse, 'metadata') and 'message_id' in impulse.metadata:
                        await self.mark_message_processed(impulse.metadata['message_id'])
            except asyncio.QueueEmpty:
                break

        # 替换队列
        self._queue = temp_queue

        if expired_count > 0:
            logger.info(
                f"[Queue] {self.queue_id} 清理了 {expired_count} 条过期消息"
            )

        return expired_count

    async def _cleanup_loop(self):
        """后台清理循环"""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._cleanup_interval)

                # 检查是否需要停止
                if self._stop_event.is_set():
                    break

                # 执行清理
                expired_count = await self.remove_expired_messages()

                if expired_count > 0:
                    logger.info(
                        f"[Queue] {self.queue_id} 定期清理: "
                        f"移除 {expired_count} 条过期消息"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Queue] {self.queue_id} 清理任务出错: {e}")

    async def get_message_by_id(self, message_id: str) -> Optional[Any]:
        """
        根据消息ID获取消息

        Args:
            message_id: 消息ID

        Returns:
            Optional[Any]: 消息对象，如果不存在返回None
        """
        async with self._message_lock:
            return self._message_map.get(message_id)

    async def update_message_priority(
        self,
        message_id: str,
        new_priority: MessagePriority
    ) -> bool:
        """
        更新消息优先级（需要重建队列）

        Args:
            message_id: 消息ID
            new_priority: 新的优先级

        Returns:
            bool: True表示更新成功
        """
        async with self._message_lock:
            if message_id not in self._message_map:
                return False

            impulse = self._message_map[message_id]

            # 创建新队列
            temp_queue = asyncio.Queue(maxsize=self.max_size)

            # 将消息移到新队列，更新目标消息的优先级
            found = False
            while not self._queue.empty():
                try:
                    priority_item = self._queue.get_nowait()
                    item = priority_item.item

                    # 检查是否是目标消息
                    if hasattr(item, 'metadata') and item.metadata.get('message_id') == message_id:
                        # 更新优先级
                        new_priority_item = PriorityItem(new_priority.value, item)
                        await temp_queue.put(new_priority_item)
                        found = True
                    else:
                        await temp_queue.put(priority_item)

                except asyncio.QueueEmpty:
                    break

            if found:
                # 替换队列
                self._queue = temp_queue
                logger.debug(
                    f"[Queue] {self.queue_id} 更新消息 {message_id} "
                    f"优先级为 {new_priority.value}"
                )
                return True
            else:
                return False


__all__ = [
    "QueuePriority",
    "AsyncSynapticQueue",
    "PriorityItem",
    "QueueMetrics",
]

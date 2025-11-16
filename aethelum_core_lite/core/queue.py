"""
突触队列 (SynapticQueue)

基于Python queue.Queue实现的线程安全内存队列，模拟神经元间的突触连接。
"""

import threading
import time
import uuid
from typing import Any, Dict, Optional
from queue import Queue, Empty, Full
from .message import NeuralImpulse


class SynapticQueue:
    """
    突触队列 - 神经元间的连接点，缓冲神经信号

    基于Python queue.Queue实现，提供线程安全的FIFO队列，
    用于在Agent之间传递NeuralImpulse（神经脉冲）。
    """

    def __init__(
        self,
        name: str,
        max_size: Optional[int] = None,
        durable: bool = False,
        auto_delete: bool = False,
        max_retries: int = 3,
        retry_delay: float = 5.0
    ):
        """
        初始化突触队列

        Args:
            name: 队列名称
            max_size: 队列最大容量，None表示无限制
            durable: 是否持久化（内存模式下无效，仅为兼容性）
            auto_delete: 是否自动删除（内存模式下无效，仅为兼容性）
            max_retries: 最大重试次数
            retry_delay: 重试延迟时间（秒）
        """
        self.name: str = name
        self.max_size: Optional[int] = max_size
        self.durable: bool = durable
        self.auto_delete: bool = auto_delete
        self.max_retries: int = max_retries
        self.retry_delay: float = retry_delay

        # 内部队列
        self._queue: Queue = Queue(maxsize=max_size or 0)

        # 统计信息
        self._stats = {
            'created_at': time.time(),
            'total_messages': 0,
            'failed_messages': 0,
            'last_activity': None
        }

        # 线程锁
        self._lock = threading.RLock()

        # 队列状态
        self._active = True

    def put(self, impulse: NeuralImpulse, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        向队列放入神经脉冲

        Args:
            impulse: 神经脉冲消息
            block: 是否阻塞等待
            timeout: 超时时间（秒）

        Returns:
            bool: 是否成功放入
        """
        try:
            # 添加队列元数据
            impulse.metadata['_queue_enqueued'] = self.name
            impulse.metadata['_queue_timestamp'] = time.time()
            impulse.metadata['_queue_id'] = str(uuid.uuid4())

            self._queue.put(impulse, block=block, timeout=timeout)

            with self._lock:
                self._stats['total_messages'] += 1
                self._stats['last_activity'] = time.time()

            return True
        except Full:
            return False
        except Exception as e:
            with self._lock:
                self._stats['failed_messages'] += 1
            raise e

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[NeuralImpulse]:
        """
        从队列获取神经脉冲

        Args:
            block: 是否阻塞等待
            timeout: 超时时间（秒）

        Returns:
            NeuralImpulse: 神经脉冲，如果队列为空且不阻塞则返回None
        """
        try:
            impulse = self._queue.get(block=block, timeout=timeout)

            with self._lock:
                self._stats['last_activity'] = time.time()

            return impulse
        except Empty:
            return None
        except Exception as e:
            with self._lock:
                self._stats['failed_messages'] += 1
            raise e

    def task_done(self) -> None:
        """标记任务完成，调用queue.task_done()"""
        try:
            self._queue.task_done()
        except ValueError:
            # 如果没有正在处理的任务，忽略错误
            pass

    def join(self) -> None:
        """阻塞直到队列中所有任务都被处理"""
        self._queue.join()

    def size(self) -> int:
        """获取当前队列大小"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """检查队列是否为空"""
        return self._queue.empty()

    def full(self) -> bool:
        """检查队列是否已满"""
        return self._queue.full()

    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        with self._lock:
            return {
                **self._stats,
                'name': self.name,
                'current_size': self.size(),
                'max_size': self.max_size,
                'is_empty': self.empty(),
                'is_full': self.full(),
                'is_active': self._active,
                'uptime_seconds': time.time() - self._stats['created_at']
            }

    def clear(self) -> int:
        """
        清空队列

        Returns:
            int: 清除的消息数量
        """
        count = 0
        while not self.empty():
            try:
                self._queue.get_nowait()
                self.task_done()
                count += 1
            except Empty:
                break

        with self._lock:
            self._stats['last_activity'] = time.time()

        return count

    def close(self) -> None:
        """关闭队列"""
        with self._lock:
            self._active = False

        # 清空队列
        self.clear()

    def __str__(self) -> str:
        """字符串表示"""
        return f"SynapticQueue(name='{self.name}', size={self.size()}/{self.max_size or '∞'})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"SynapticQueue(name='{self.name}', max_size={self.max_size}, "
                f"durable={self.durable}, auto_delete={self.auto_delete})")

    def __len__(self) -> int:
        """返回队列大小"""
        return self.size()
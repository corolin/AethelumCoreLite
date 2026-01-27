"""
WAL持久化辅助类

为AsyncIO组件提供WAL（Write-Ahead Log）持久化功能。
"""

import asyncio
import json
import time
import uuid
import os
from typing import Any, Optional
from pathlib import Path
from collections import deque
import logging

logger = logging.getLogger(__name__)

# 检查msgpack可用性
try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False
    logger.warning("msgpack not available, falling back to JSON for WAL")


class AsyncWALWriter:
    """异步WAL写入器 - 支持批量写入和异步操作"""

    def __init__(self,
                 queue_id: str,
                 wal_dir: str = "wal_data",
                 batch_size: int = 100,
                 flush_interval: float = 1.0,
                 enable_wal: bool = True):
        """
        初始化WAL写入器

        Args:
            queue_id: 队列ID
            wal_dir: WAL日志目录
            batch_size: 批量写入大小
            flush_interval: 刷新间隔（秒）
            enable_wal: 是否启用WAL
        """
        # 安全验证：防止路径遍历攻击
        if not queue_id:
            raise ValueError("queue_id不能为空")

        # 只允许字母、数字、下划线、连字符
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', queue_id):
            raise ValueError(
                f"queue_id包含非法字符: {queue_id}. "
                "只允许字母、数字、下划线、连字符"
            )

        # 限制长度
        if len(queue_id) > 100:
            raise ValueError(f"queue_id过长（最大100字符）: {len(queue_id)}")

        self.queue_id = queue_id
        self.wal_dir = wal_dir
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.enable_wal = enable_wal

        # WAL文件路径（已验证queue_id安全）
        Path(wal_dir).mkdir(parents=True, exist_ok=True)
        self.log1_path = os.path.join(wal_dir, f"{queue_id}_log1.wal")
        self.log2_path = os.path.join(wal_dir, f"{queue_id}_log2.wal")

        # 缓冲区
        self._log1_buffer: deque = deque()
        self._log2_buffer: deque = deque()

        # 文件句柄
        self._log1_file: Optional[Any] = None
        self._log2_file: Optional[Any] = None

        # 控制标志
        self._stop_event = asyncio.Event()
        self._writer_task: Optional[asyncio.Task] = None

    async def start(self):
        """启动WAL写入器"""
        if not self.enable_wal:
            logger.info(f"[WAL] Disabled for queue {self.queue_id}")
            return

        await self._init_wal_logs()
        self._writer_task = asyncio.create_task(self._write_loop())
        logger.info(f"[WAL] Writer started for queue {self.queue_id}")

    async def stop(self):
        """停止WAL写入器"""
        if not self.enable_wal:
            return

        self._stop_event.set()

        if self._writer_task:
            try:
                await asyncio.wait_for(self._writer_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"[WAL] Writer stop timeout for queue {self.queue_id}")

        await self._close_wal_logs()
        logger.info(f"[WAL] Writer stopped for queue {self.queue_id}")

    async def write_log1(self, message_id: str, priority: int, impulse: Any):
        """写入log1（输入日志）"""
        if not self.enable_wal:
            return

        self._log1_buffer.append((message_id, priority, impulse))

    async def write_log2(self, message_id: str):
        """写入log2（处理完成日志）"""
        if not self.enable_wal:
            return

        self._log2_buffer.append(message_id)

    async def _write_loop(self):
        """后台写入循环"""
        logger.info(f"[WAL] Write loop started for queue {self.queue_id}")

        while not self._stop_event.is_set():
            try:
                # 等待刷新间隔或停止信号
                await asyncio.sleep(self.flush_interval)

                if self._stop_event.is_set():
                    # 退出前刷新
                    await self._flush_log1_buffer()
                    await self._flush_log2_buffer()
                    break

                # 定期刷新缓冲区
                if len(self._log1_buffer) > self.batch_size:
                    await self._flush_log1_buffer()
                if len(self._log2_buffer) > self.batch_size:
                    await self._flush_log2_buffer()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[WAL] Error in write loop for queue {self.queue_id}: {e}")

        logger.info(f"[WAL] Write loop exited for queue {self.queue_id}")

    async def _flush_log1_buffer(self):
        """批量刷新log1缓冲区"""
        if not self._log1_buffer:
            return

        # 批量取出所有待写入的数据
        batch = []
        while self._log1_buffer:
            batch.append(self._log1_buffer.popleft())

        if not batch:
            return

        try:
            # 在线程池中执行同步写入
            await asyncio.to_thread(self._sync_write_log1, batch)
            logger.debug(f"[WAL] Flushed {len(batch)} entries to log1 for queue {self.queue_id}")
        except Exception as e:
            logger.error(f"[WAL] Failed to flush log1 buffer for queue {self.queue_id}: {e}")

    async def _flush_log2_buffer(self):
        """批量刷新log2缓冲区"""
        if not self._log2_buffer:
            return

        # 批量取出所有待写入的数据
        batch = []
        while self._log2_buffer:
            batch.append(self._log2_buffer.popleft())

        if not batch:
            return

        try:
            # 在线程池中执行同步写入
            await asyncio.to_thread(self._sync_write_log2, batch)
            logger.debug(f"[WAL] Flushed {len(batch)} entries to log2 for queue {self.queue_id}")
        except Exception as e:
            logger.error(f"[WAL] Failed to flush log2 buffer for queue {self.queue_id}: {e}")

    def _sync_write_log1(self, batch: list):
        """同步写入log1"""
        if not self._log1_file:
            return

        try:
            if MSGPACK_AVAILABLE:
                # msgpack 批量写入
                for message_id, priority, impulse in batch:
                    log_entry = {
                        "id": message_id,
                        "priority": priority,
                        "impulse": impulse.to_dict() if hasattr(impulse, 'to_dict') else impulse,
                        "timestamp": time.time()
                    }
                    packed = msgpack.packb(log_entry, use_bin_type=True)
                    self._log1_file.write(len(packed).to_bytes(4, 'big'))
                    self._log1_file.write(packed)
            else:
                # JSON 批量写入
                for message_id, priority, impulse in batch:
                    log_entry = {
                        "id": message_id,
                        "priority": priority,
                        "impulse": impulse.to_dict() if hasattr(impulse, 'to_dict') else impulse,
                        "timestamp": time.time()
                    }
                    self._log1_file.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

            self._log1_file.flush()
        except Exception as e:
            logger.error(f"[WAL] Failed to write log1: {e}")

    def _sync_write_log2(self, batch: list):
        """同步写入log2"""
        if not self._log2_file:
            return

        try:
            for message_id in batch:
                self._log2_file.write(message_id + '\n')
            self._log2_file.flush()
        except Exception as e:
            logger.error(f"[WAL] Failed to write log2: {e}")

    async def _init_wal_logs(self):
        """初始化WAL日志文件"""
        try:
            if MSGPACK_AVAILABLE:
                # msgpack 使用二进制模式
                self._log1_file = open(self.log1_path, 'ab')
                self._log2_file = open(self.log2_path, 'ab')
                logger.info(f"[WAL] Logs initialized with msgpack for queue {self.queue_id}")
            else:
                # JSON 使用文本模式
                self._log1_file = open(self.log1_path, 'a', encoding='utf-8')
                self._log2_file = open(self.log2_path, 'a', encoding='utf-8')
                logger.info(f"[WAL] Logs initialized with JSON for queue {self.queue_id}")
        except Exception as e:
            logger.error(f"[WAL] Failed to initialize logs for queue {self.queue_id}: {e}")
            raise

    async def _close_wal_logs(self):
        """关闭WAL日志文件"""
        try:
            if self._log1_file:
                self._log1_file.flush()
                self._log1_file.close()
                self._log1_file = None
            if self._log2_file:
                self._log2_file.flush()
                self._log2_file.close()
                self._log2_file = None
            logger.info(f"[WAL] Logs closed for queue {self.queue_id}")
        except Exception as e:
            logger.error(f"[WAL] Error closing logs for queue {self.queue_id}: {e}")

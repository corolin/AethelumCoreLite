"""
改进的 WAL 持久化实现 v2

架构改进：
1. Log1（数据）: Msgpack + Header [LSN(8B)][DataSize(4B)][Checksum(4B)]
2. Log2（状态）: mmap 位点文件，仅 8 字节记录 Last_Committed_LSN
3. 清理机制：滚动删除已处理的旧 Log1（100MB 触发）

性能优势：
- Log2 从频繁写入变为单次 mmap 更新，减少 I/O
- Checksum 确保数据完整性
- LSN 支持崩溃恢复和精确清理
"""

import asyncio
import struct
import mmap
import os
import time
import hashlib
from pathlib import Path
from typing import Optional, Any, List, Tuple
from collections import deque
import logging

logger = logging.getLogger(__name__)

# 检查 msgpack 可用性
try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False
    logger.warning("msgpack not available, falling back to JSON")

# Header 格式: LSN(8B) + DataSize(4B) + Checksum(4B)
HEADER_FORMAT = ">QII"  # big-endian: unsigned long long + unsigned int + unsigned int
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 16 字节


class LSNAllocator:
    """LSN (Log Sequence Number) 分配器"""

    def __init__(self, start_lsn: int = 1):
        self._current_lsn = start_lsn
        self._lock = asyncio.Lock()

    async def next_lsn(self) -> int:
        """获取下一个 LSN"""
        async with self._lock:
            lsn = self._current_lsn
            self._current_lsn += 1
            return lsn

    @property
    def current_lsn(self) -> int:
        """当前 LSN"""
        return self._current_lsn


class MmapLSNTracker:
    """
    mmap 位点文件追踪器

    文件格式：8 字节存储 Last_Committed_LSN
    """

    def __init__(self, ptr_path: str):
        self.ptr_path = ptr_path
        self.ptr_file: Optional[Any] = None
        self.ptr_map: Optional[Any] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """初始化 mmap 文件"""
        Path(self.ptr_path).parent.mkdir(parents=True, exist_ok=True)

        # 如果文件不存在，创建并初始化为 0
        if not os.path.exists(self.ptr_path):
            with open(self.ptr_path, "wb") as f:
                f.write(struct.pack(">Q", 0))  # 初始 LSN = 0

        # 打开并 mmap 文件
        self.ptr_file = open(self.ptr_path, "r+b")
        self.ptr_map = mmap.mmap(self.ptr_file.fileno(), 8)

        logger.debug(f"[LSN Tracker] Initialized: {self.ptr_path}")

    async def stop(self):
        """关闭 mmap"""
        async with self._lock:
            try:
                if self.ptr_map:
                    self.ptr_map.close()
                    self.ptr_map = None
            except:
                pass
            try:
                if self.ptr_file:
                    self.ptr_file.close()
                    self.ptr_file = None
            except:
                pass

    async def get_committed_lsn(self) -> int:
        """获取已提交的 LSN"""
        async with self._lock:
            if not self.ptr_map:
                return 0
            self.ptr_map.seek(0)
            data = self.ptr_map.read(8)
            return struct.unpack(">Q", data)[0]

    async def commit_lsn(self, lsn: int):
        """更新已提交的 LSN（mmap 写入，自动持久化）"""
        async with self._lock:
            if not self.ptr_map:
                logger.warning("[LSN Tracker] Not initialized")
                return
            self.ptr_map.seek(0)
            self.ptr_map.write(struct.pack(">Q", lsn))
            self.ptr_map.flush()  # mmap flush，确保持久化


class RollingLog1Manager:
    """
    Log1 滚动管理器

    规则：
    - 单文件最大 100MB
    - 当 Last_Committed_LSN 确认该段已处理时，删除旧文件
    """

    def __init__(self, queue_id: str, wal_dir: str, max_segment_size: int = 100 * 1024 * 1024):
        self.queue_id = queue_id
        self.wal_dir = wal_dir
        self.max_segment_size = max_segment_size
        self.current_segment_path = ""
        self.current_segment_size = 0
        self.current_file: Optional[Any] = None
        self.segment_base_lsn = 1  # 当前段的起始 LSN

        Path(wal_dir).mkdir(parents=True, exist_ok=True)

    def _get_segment_path(self, segment_num: int) -> str:
        """获取段文件路径"""
        return os.path.join(self.wal_dir, f"{self.queue_id}_log1_{segment_num}.wal")

    def _list_segments(self) -> List[Tuple[int, str]]:
        """列出所有段文件，按段号排序"""
        segments = []
        if not os.path.exists(self.wal_dir):
            return segments

        for filename in os.listdir(self.wal_dir):
            if filename.startswith(f"{self.queue_id}_log1_") and filename.endswith(".wal"):
                # 提取段号
                try:
                    segment_num = int(filename[len(f"{self.queue_id}_log1_"):-4])
                    full_path = os.path.join(self.wal_dir, filename)
                    segments.append((segment_num, full_path))
                except ValueError:
                    continue

        return sorted(segments, key=lambda x: x[0])

    async def start(self):
        """启动管理器，加载或创建当前段"""
        segments = self._list_segments()

        if segments:
            # 使用最后一个段
            last_segment_num, last_path = segments[-1]
            file_size = os.path.getsize(last_path)

            if file_size < self.max_segment_size:
                # 继续使用最后一个段
                self.current_segment_path = last_path
                self.current_segment_size = file_size
                self.current_file = open(last_path, "ab")
                self.segment_base_lsn = last_segment_num * 1000000 + 1  # 估计值
                logger.info(f"[Log1] Resuming segment {last_segment_num}: {last_path}")
            else:
                # 最后一段已满，创建新段
                await self._rotate_segment(last_segment_num + 1)
        else:
            # 创建第一个段
            await self._rotate_segment(0)

    async def _rotate_segment(self, new_segment_num: int):
        """滚动到新段"""
        # 关闭旧文件
        if self.current_file:
            self.current_file.close()

        # 创建新段
        new_path = self._get_segment_path(new_segment_num)
        self.current_segment_path = new_path
        self.current_file = open(new_path, "ab")
        self.current_segment_size = 0
        self.segment_base_lsn = new_segment_num * 1000000 + 1

        logger.info(f"[Log1] Created new segment {new_segment_num}: {new_path}")

    async def write_record(self, lsn: int, data: bytes) -> bool:
        """写入一条记录（包含 Header）"""
        if not self.current_file:
            logger.error("[Log1] File not initialized")
            return False

        record_size = HEADER_SIZE + len(data)

        # 检查是否需要滚动
        if self.current_segment_size + record_size > self.max_segment_size:
            # 提取当前段号
            current_segment_num = self._extract_segment_num(self.current_segment_path)
            await self._rotate_segment(current_segment_num + 1)

        # 写入 Header + Data
        try:
            # 计算 checksum (CRC32)
            checksum = hashlib.md5(data).digest()[:4]
            checksum_int = struct.unpack(">I", checksum)[0]

            # 组装 Header: LSN + DataSize + Checksum
            header = struct.pack(HEADER_FORMAT, lsn, len(data), checksum_int)

            # 写入文件
            self.current_file.write(header + data)
            self.current_file.flush()
            os.fsync(self.current_file.fileno())

            self.current_segment_size += record_size
            return True
        except Exception as e:
            logger.error(f"[Log1] Failed to write record: {e}")
            return False

    def _extract_segment_num(self, path: str) -> int:
        """从路径提取段号"""
        filename = os.path.basename(path)
        # filename format: {queue_id}_log1_{segment_num}.wal
        prefix = f"{self.queue_id}_log1_"
        suffix = ".wal"
        return int(filename[len(prefix):-len(suffix)])

    async def cleanup_old_segments(self, committed_lsn: int):
        """清理已处理的旧段"""
        segments = self._list_segments()

        # 找出可以删除的段
        # 规则：如果段中的所有 LSN 都 < committed_lsn，则可以删除
        segments_to_delete = []

        for segment_num, path in segments:
            # 估计该段的 LSN 范围
            segment_start_lsn = segment_num * 1000000 + 1
            segment_end_lsn = (segment_num + 1) * 1000000

            # 如果该段的所有 LSN 都已提交，则删除
            if segment_end_lsn < committed_lsn:
                # 但不能删除当前段
                if path != self.current_segment_path:
                    segments_to_delete.append(path)

        # 删除旧段
        for path in segments_to_delete:
            try:
                os.remove(path)
                logger.info(f"[Log1] Deleted old segment: {path}")
            except Exception as e:
                logger.error(f"[Log1] Failed to delete segment {path}: {e}")

    async def stop(self):
        """关闭文件"""
        if self.current_file:
            self.current_file.close()
            self.current_file = None


class ImprovedWALWriter:
    """
    改进的 WAL 写入器 v2

    架构：
    - Log1: 滚动文件，每条记录包含 [LSN + DataSize + Checksum + Data]
    - Log2: mmap 位点文件，8 字节记录 Last_Committed_LSN
    - 清理：自动删除已处理的旧 Log1 段
    """

    def __init__(self,
                 queue_id: str,
                 wal_dir: str = "wal_data_v2",
                 batch_size: int = 100,
                 flush_interval: float = 1.0,
                 enable_wal: bool = True,
                 max_segment_size: int = 100 * 1024 * 1024):
        """
        初始化改进的 WAL 写入器

        Args:
            queue_id: 队列ID
            wal_dir: WAL 目录
            batch_size: 批量写入大小
            flush_interval: 刷新间隔（秒）
            enable_wal: 是否启用 WAL
            max_segment_size: 单个 Log1 段的最大大小（默认 100MB）
        """
        # 安全验证：防止路径遍历攻击
        if not queue_id:
            raise ValueError("queue_id不能为空")

        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', queue_id):
            raise ValueError(
                f"queue_id包含非法字符: {queue_id}. "
                "只允许字母、数字、下划线、连字符"
            )

        if len(queue_id) > 100:
            raise ValueError(f"queue_id过长（最大100字符）: {len(queue_id)}")

        self.queue_id = queue_id
        self.wal_dir = wal_dir
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.enable_wal = enable_wal

        # LSN 分配器
        self._lsn_allocator = LSNAllocator(start_lsn=1)

        # Log1 管理器
        self._log1_manager = RollingLog1Manager(
            queue_id=queue_id,
            wal_dir=wal_dir,
            max_segment_size=max_segment_size
        )

        # Log2 mmap 追踪器
        ptr_path = os.path.join(wal_dir, f"{queue_id}_log2.ptr")
        self._lsn_tracker = MmapLSNTracker(ptr_path)

        # 缓冲区：存储 (message_id, lsn, priority, data)
        self._log1_buffer: deque = deque()

        # message_id -> LSN 映射（用于 WAL log2 查找）
        self._message_id_to_lsn: Dict[str, int] = {}

        # 控制
        self._stop_event = asyncio.Event()
        self._writer_task: Optional[asyncio.Task] = None

    async def start(self):
        """启动 WAL 写入器"""
        if not self.enable_wal:
            logger.info(f"[WAL v2] Disabled for queue {self.queue_id}")
            return

        await self._log1_manager.start()
        await self._lsn_tracker.start()

        self._writer_task = asyncio.create_task(self._write_loop())
        logger.info(f"[WAL v2] Started for queue {self.queue_id}")

    async def stop(self):
        """停止 WAL 写入器"""
        if not self.enable_wal:
            return

        self._stop_event.set()

        if self._writer_task:
            try:
                await asyncio.wait_for(self._writer_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"[WAL v2] Stop timeout for queue {self.queue_id}")

        await self._log1_manager.stop()
        await self._lsn_tracker.stop()
        logger.info(f"[WAL v2] Stopped for queue {self.queue_id}")

    async def write_log1(self, message_id: str, priority: int, data: dict):
        """写入 log1（输入日志）"""
        if not self.enable_wal:
            return

        # 分配 LSN
        lsn = await self._lsn_allocator.next_lsn()

        # 存储 message_id -> LSN 映射
        self._message_id_to_lsn[message_id] = lsn

        # 加入缓冲区
        self._log1_buffer.append((message_id, lsn, priority, data))

        logger.debug(f"[WAL v2] Assigned LSN {lsn} to message_id {message_id}")

    async def write_log2(self, message_id: str, lsn: Optional[int] = None):
        """写入 log2（处理完成）- 更新 mmap 位点"""
        if not self.enable_wal:
            return

        # 如果没有提供 LSN，从映射中查找
        if lsn is None:
            lsn = self._message_id_to_lsn.get(message_id)
            if lsn is None:
                logger.warning(f"[WAL v2] message_id {message_id} not found in LSN mapping")
                return

        # 更新已提交 LSN（mmap 写入）
        await self._lsn_tracker.commit_lsn(lsn)

        logger.debug(f"[WAL v2] Committed LSN {lsn} for message_id {message_id}")

        # 触发清理检查
        committed_lsn = await self._lsn_tracker.get_committed_lsn()
        await self._log1_manager.cleanup_old_segments(committed_lsn)

    async def _write_loop(self):
        """后台写入循环"""
        logger.info(f"[WAL v2] Write loop started for queue {self.queue_id}")

        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.flush_interval)

                if self._stop_event.is_set():
                    await self._flush_buffer()
                    break

                # 批量刷新
                if len(self._log1_buffer) > self.batch_size:
                    await self._flush_buffer()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WAL v2] Error in write loop: {e}")

        logger.info(f"[WAL v2] Write loop exited for queue {self.queue_id}")

    async def _flush_buffer(self):
        """批量刷新缓冲区到 Log1"""
        if not self._log1_buffer:
            return

        # 取出所有待写入数据
        batch = []
        while self._log1_buffer:
            batch.append(self._log1_buffer.popleft())

        if not batch:
            return

        try:
            # 在线程池中执行同步写入
            await asyncio.to_thread(self._sync_write_batch, batch)
            logger.debug(f"[WAL v2] Flushed {len(batch)} entries to Log1")
        except Exception as e:
            logger.error(f"[WAL v2] Failed to flush buffer: {e}")

    def _sync_write_batch(self, batch: List[Tuple]):
        """同步写入批量数据"""
        import json

        for message_id, lsn, priority, data in batch:
            # 序列化数据
            if MSGPACK_AVAILABLE:
                payload = msgpack.packb({
                    "id": message_id,
                    "priority": priority,
                    "data": data,
                    "timestamp": time.time()
                }, use_bin_type=True)
            else:
                payload = json.dumps({
                    "id": message_id,
                    "priority": priority,
                    "data": data,
                    "timestamp": time.time()
                }).encode('utf-8')

            # 写入 Log1（带 Header）- 同步写入
            data_size = len(payload)
            record_size = HEADER_SIZE + data_size

            # 检查是否需要滚动
            if self._log1_manager.current_segment_size + record_size > self._log1_manager.max_segment_size:
                # 切换到新段
                current_segment_num = self._log1_manager._extract_segment_num(
                    self._log1_manager.current_segment_path
                )
                # 在线程中不能使用 await，所以直接同步处理
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._log1_manager._rotate_segment(current_segment_num + 1))

            # 计算 checksum
            checksum = hashlib.md5(payload).digest()[:4]
            checksum_int = struct.unpack(">I", checksum)[0]

            # 组装 Header
            header = struct.pack(HEADER_FORMAT, lsn, data_size, checksum_int)

            # 写入文件
            self._log1_manager.current_file.write(header + payload)
            self._log1_manager.current_file.flush()
            os.fsync(self._log1_manager.current_file.fileno())

            self._log1_manager.current_segment_size += record_size

    async def recover(self) -> List[Tuple[int, Any]]:
        """
        崩溃恢复：读取未提交的记录

        Returns:
            List of (lsn, data) for uncommitted records
        """
        if not self.enable_wal:
            return []

        # 获取已提交的 LSN
        committed_lsn = await self._lsn_tracker.get_committed_lsn()

        # 扫描所有 Log1 段，找出 LSN > committed_lsn 的记录
        uncommitted_records = []

        segments = self._log1_manager._list_segments()
        for segment_num, path in segments:
            try:
                records = await self._read_segment(path, committed_lsn)
                uncommitted_records.extend(records)
            except Exception as e:
                logger.error(f"[WAL v2] Failed to read segment {path}: {e}")

        # 按 LSN 排序
        uncommitted_records.sort(key=lambda x: x[0])

        logger.info(f"[WAL v2] Recovered {len(uncommitted_records)} uncommitted records")
        return uncommitted_records

    async def _read_segment(self, path: str, committed_lsn: int) -> List[Tuple[int, Any]]:
        """读取段文件，返回未提交的记录"""
        uncommitted = []

        try:
            with open(path, "rb") as f:
                while True:
                    # 读取 Header
                    header_data = f.read(HEADER_SIZE)
                    if len(header_data) < HEADER_SIZE:
                        break  # 文件结束

                    lsn, data_size, checksum = struct.unpack(HEADER_FORMAT, header_data)

                    # 读取 Data
                    data = f.read(data_size)
                    if len(data) < data_size:
                        logger.warning(f"[WAL v2] Incomplete record at LSN {lsn}")
                        break

                    # 验证 checksum
                    computed_checksum = hashlib.md5(data).digest()[:4]
                    computed_checksum_int = struct.unpack(">I", computed_checksum)[0]

                    if computed_checksum_int != checksum:
                        logger.error(f"[WAL v2] Checksum mismatch at LSN {lsn}")
                        continue

                    # 如果 LSN > committed_lsn，则为未提交记录
                    if lsn > committed_lsn:
                        # 反序列化
                        if MSGPACK_AVAILABLE:
                            record = msgpack.unpackb(data, raw=False)
                        else:
                            import json
                            record = json.loads(data.decode('utf-8'))

                        uncommitted.append((lsn, record))

        except Exception as e:
            logger.error(f"[WAL v2] Error reading segment {path}: {e}")

        return uncommitted

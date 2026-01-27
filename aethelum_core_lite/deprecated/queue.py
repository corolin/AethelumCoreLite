import queue
import threading
import time
import uuid
import json
import os
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from collections import deque
from .message import NeuralImpulse

# msgpack 是可选依赖，优先使用 msgpack，否则回退到 json
try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False
    msgpack = None

@dataclass
class QueueStats:
    """队列统计数据"""
    total_messages: int = 0
    failed_messages: int = 0
    processed_messages: int = 0
    active_time: float = 0.0
    last_activity: float = 0.0
    average_processing_time: float = 0.0
    queue_size: int = 0
    priority_distribution: Dict[str, int] = None
    
    def __post_init__(self):
        if self.priority_distribution is None:
            self.priority_distribution = {}

class SynapticQueue:
    """突触队列，用于在神经元之间传递神经脉冲
    
    增强功能:
    - 消息优先级支持
    - 持久化存储
    - 批量操作
    - 详细统计信息
    - 消息过期处理
    """
    
    def __init__(self, queue_id: str, max_size: int = 0,
                 enable_persistence: bool = False,
                 persistence_path: Optional[str] = None,
                 message_ttl: Optional[float] = None,
                 persistence_interval: float = 30.0,
                 cleanup_interval: float = 300.0):
        """初始化突触队列

        Args:
            queue_id: 队列唯一标识符
            max_size: 队列最大大小，0表示无限制
            enable_persistence: 是否启用持久化
            persistence_path: 持久化文件路径（不含扩展名）
            message_ttl: 消息生存时间(秒)，None表示不过期
            persistence_interval: 后台持久化间隔(秒)，默认30秒（已废弃，保留兼容性）
            cleanup_interval: 后台清理间隔(秒)，默认300秒(5分钟)
        """
        self.queue_id = queue_id
        self.max_size = max_size
        self.enable_persistence = enable_persistence
        base_path = persistence_path or f"queue_{queue_id}"
        # WAL日志文件路径（根据可用性选择格式）
        ext = "msgpack" if MSGPACK_AVAILABLE else "jsonl"
        self._log1_path = f"{base_path}_log1.{ext}"  # 消息日志（append-only）
        self._log2_path = f"{base_path}_log2.{ext}"  # 消费日志（append-only）
        self.message_ttl = message_ttl
        self.persistence_interval = persistence_interval
        self.cleanup_interval = cleanup_interval

        # 使用优先级队列
        self._queue = queue.PriorityQueue(maxsize=max_size)
        self._lock = threading.RLock()
        self._closed = False

        # 统计信息
        self._stats = QueueStats()
        self._start_time = time.time()
        self._processing_times = []

        # 消息ID映射，用于快速查找和更新
        self._message_map = {}

        # 日志记录器
        self.logger = logging.getLogger(f"aethelum.queue.{queue_id}")

        # WAL日志文件句柄（append-only模式）
        self._log1_file = None
        self._log2_file = None

        # WAL异步写入缓冲区
        self._log1_buffer = deque(maxlen=10000)  # 内存缓冲队列
        self._log2_buffer = deque(maxlen=10000)
        self._write_lock = threading.Lock()  # 写入锁

        # 后台写入线程
        self._write_stop_event = threading.Event()
        self._write_thread = None

        # 后台清理线程
        self._cleanup_stop_event = threading.Event()
        self._cleanup_thread = None

        # 如果启用持久化，初始化WAL日志
        if self.enable_persistence:
            self._init_wal_logs()
            # 从log1恢复未处理的消息
            self._load_from_log1()
            # 启动后台写入线程
            self._write_thread = threading.Thread(
                target=self._write_loop,
                daemon=True,
                name=f"QueueWriter-{queue_id}"
            )
            self._write_thread.start()
            # 启动后台清理线程
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                daemon=True,
                name=f"QueueCleanup-{queue_id}"
            )
            self._cleanup_thread.start()
    
    def put(self, impulse: NeuralImpulse, priority: int = 5, block: bool = True, timeout: Optional[float] = None) -> bool:
        """将神经脉冲放入队列

        Args:
            impulse: 神经脉冲对象
            priority: 优先级，数字越小优先级越高
            block: 是否阻塞等待队列有空间
            timeout: 阻塞超时时间

        Returns:
            bool: 是否成功放入队列
        """
        if self._closed:
            return False

        # 检查消息是否过期
        if self._is_expired(impulse):
            return False

        # 为消息添加唯一ID和时间戳
        #
        # 消息唯一性保证：
        # ===================
        # 当前实现：uuid.uuid4()
        # - 122位随机数
        # - 冲突概率：~1/2^122
        # - 相当于：每秒生成10亿个UUID，连续运行85年才会有50%概率发生冲突
        # - 实际应用中冲突概率可忽略不计
        #
        # 如果您的应用场景需要更高的确定性，可考虑：
        # 1. 数据库唯一约束（防止重复）
        # 2. 布隆过滤器（快速检测重复）
        # 3. 雪花算法（分布式系统）
        # 4. 组合键：timestamp + hostname + sequence
        message_id = str(uuid.uuid4())
        impulse.metadata["message_id"] = message_id
        impulse.metadata["queue_timestamp"] = time.time()
        impulse.metadata["priority"] = priority

        try:
            with self._lock:
                # 使用优先级队列，(priority, timestamp, message_id, impulse)
                item = (priority, time.time(), message_id, impulse)
                self._queue.put(item, block=block, timeout=timeout)

                # 更新消息映射
                self._message_map[message_id] = impulse
                self._stats.total_messages += 1
                self._stats.last_activity = time.time()
                self._stats.queue_size = self._queue.qsize()

                # 更新优先级分布
                priority_key = f"priority_{priority}"
                self._stats.priority_distribution[priority_key] = \
                    self._stats.priority_distribution.get(priority_key, 0) + 1

                # WAL: 追加消息到内存缓冲（O(1)操作，非阻塞）
                if self.enable_persistence:
                    self._log1_buffer.append((message_id, priority, impulse))

            return True
        except queue.Full:
            return False
    
    def get(self, block: bool = True, timeout: Optional[float] = None,
            max_retries: int = 100) -> Optional[NeuralImpulse]:
        """从队列获取神经脉冲

        Args:
            block: 是否阻塞等待队列有消息
            timeout: 阻塞超时时间
            max_retries: 最大重试次数（防止连续过期消息导致无限循环）

        Returns:
            NeuralImpulse: 神经脉冲对象，队列为空时返回None
        """
        if self._closed:
            return None

        # 使用循环代替递归，限制最大重试次数
        retry_count = 0

        while retry_count < max_retries:
            # 先从队列获取消息（可能阻塞，不在锁内）
            try:
                priority, timestamp, message_id, impulse = self._queue.get(
                    block=block,
                    timeout=timeout
                )
            except queue.Empty:
                return None

            # 检查消息是否过期
            if not self._is_expired(impulse):
                # 消息未过期，正常返回
                break

            # 消息已过期，跳过并继续
            self._queue.task_done()
            retry_count += 1

            # 如果重试次数过多，记录警告
            if retry_count >= max_retries:
                self.logger.warning(
                    f"Queue {self.queue_id}: Reached max retries ({max_retries}) "
                    f"while skipping expired messages"
                )
                return None

        processing_start = time.time()

        # 在锁内完成所有剩余操作（原子性）
        with self._lock:
            # 从映射中移除
            if message_id in self._message_map:
                del self._message_map[message_id]

            self._stats.queue_size = self._queue.qsize()
            self._stats.last_activity = time.time()

            # WAL: 追加消息ID到内存缓冲（O(1)操作，非阻塞）
            if self.enable_persistence:
                self._log2_buffer.append(message_id)

        return impulse
    
    def task_done(self, processing_time: Optional[float] = None):
        """标记任务完成并更新统计信息
        
        Args:
            processing_time: 处理时间(秒)，如果不提供则使用默认计算
        """
        self._queue.task_done()
        
        with self._lock:
            self._stats.processed_messages += 1
            
            # 记录处理时间
            if processing_time is not None:
                self._processing_times.append(processing_time)
            
            # 保持最近1000次处理时间记录
            if len(self._processing_times) > 1000:
                self._processing_times = self._processing_times[-1000:]
            
            # 计算平均处理时间
            if self._processing_times:
                self._stats.average_processing_time = sum(self._processing_times) / len(self._processing_times)
    
    def join(self):
        """阻塞直到队列中所有任务都被处理"""
        self._queue.join()
    
    def clear(self):
        """清空队列"""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break

            self._message_map.clear()
            self._stats.queue_size = 0

            if self.enable_persistence:
                # 清空WAL日志文件
                self._cleanup_logs()
    
    def close(self):
        """关闭队列"""
        # 停止后台写入线程
        if self._write_thread is not None:
            self._write_stop_event.set()
            # 等待写入线程结束（最多等待5秒）
            self._write_thread.join(timeout=5.0)
            self.logger.info(f"Queue {self.queue_id}: Background write thread stopped")

        # 停止后台清理线程
        if self._cleanup_thread is not None:
            self._cleanup_stop_event.set()
            # 等待线程结束（最多等待5秒）
            self._cleanup_thread.join(timeout=5.0)
            self.logger.info(f"Queue {self.queue_id}: Background cleanup thread stopped")

        with self._lock:
            self._closed = True
            self._stats.active_time = time.time() - self._start_time

        # 关闭WAL日志文件（不执行清理，保留给下次启动）
        if self.enable_persistence:
            self._close_wal_logs()
            self.logger.info(f"Queue {self.queue_id}: WAL logs closed")
    
    def size(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()
    
    def empty(self) -> bool:
        """检查队列是否为空"""
        return self._queue.empty()
    
    def full(self) -> bool:
        """检查队列是否已满"""
        return self._queue.full()
    
    def get_stats(self) -> QueueStats:
        """获取队列统计信息"""
        with self._lock:
            # 更新活动时间
            self._stats.active_time = time.time() - self._start_time
            self._stats.queue_size = self._queue.qsize()
            # 返回副本而非引用，防止外部代码修改内部状态（线程安全）
            return QueueStats(
                total_messages=self._stats.total_messages,
                failed_messages=self._stats.failed_messages,
                processed_messages=self._stats.processed_messages,
                active_time=self._stats.active_time,
                last_activity=self._stats.last_activity,
                average_processing_time=self._stats.average_processing_time,
                queue_size=self._stats.queue_size,
                priority_distribution=dict(self._stats.priority_distribution)
            )
    
    def get_message_by_id(self, message_id: str) -> Optional[NeuralImpulse]:
        """根据消息ID获取消息
        
        Args:
            message_id: 消息ID
            
        Returns:
            NeuralImpulse: 神经脉冲对象，不存在时返回None
        """
        with self._lock:
            return self._message_map.get(message_id)
    
    def update_message_priority(self, message_id: str, new_priority: int) -> bool:
        """更新消息优先级
        
        Args:
            message_id: 消息ID
            new_priority: 新优先级
            
        Returns:
            bool: 是否成功更新
        """
        with self._lock:
            if message_id not in self._message_map:
                return False
                
            impulse = self._message_map[message_id]
            old_priority = impulse.metadata.get("priority", 5)
            
            # 更新优先级
            impulse.metadata["priority"] = new_priority
            
            # 更新优先级分布
            old_key = f"priority_{old_priority}"
            new_key = f"priority_{new_priority}"

            self._stats.priority_distribution[old_key] = \
                max(0, self._stats.priority_distribution.get(old_key, 0) - 1)
            self._stats.priority_distribution[new_key] = \
                self._stats.priority_distribution.get(new_key, 0) + 1

            # 持久化由后台线程定期处理，不再立即持久化
            return True
    
    def get_expired_messages(self) -> List[NeuralImpulse]:
        """获取所有过期消息
        
        Returns:
            List[NeuralImpulse]: 过期消息列表
        """
        if self.message_ttl is None:
            return []
            
        expired_messages = []
        current_time = time.time()
        
        with self._lock:
            for message_id, impulse in self._message_map.items():
                queue_timestamp = impulse.metadata.get("queue_timestamp", current_time)
                if current_time - queue_timestamp > self.message_ttl:
                    expired_messages.append(impulse)
        
        return expired_messages
    
    def remove_expired_messages(self) -> int:
        """移除所有过期消息
        
        Returns:
            int: 移除的消息数量
        """
        if self.message_ttl is None:
            return 0
            
        expired_count = 0
        current_time = time.time()
        
        # 创建新队列，只包含未过期的消息
        new_queue = queue.PriorityQueue(maxsize=self.max_size)
        
        with self._lock:
            while not self._queue.empty():
                try:
                    priority, timestamp, message_id, impulse = self._queue.get_nowait()
                    queue_timestamp = impulse.metadata.get("queue_timestamp", current_time)
                    
                    if current_time - queue_timestamp <= self.message_ttl:
                        # 消息未过期，放入新队列
                        new_queue.put((priority, timestamp, message_id, impulse))
                    else:
                        # 消息过期，从映射中移除
                        if message_id in self._message_map:
                            del self._message_map[message_id]
                        expired_count += 1
                        self._stats.failed_messages += 1
                except queue.Empty:
                    break
            
            # 替换队列
            self._queue = new_queue
            self._stats.queue_size = self._queue.qsize()

            # 持久化由后台线程定期处理，不再立即持久化

        return expired_count
    
    def batch_put(self, impulses: List[Tuple[NeuralImpulse, int]], 
                  block: bool = True, timeout: Optional[float] = None) -> int:
        """批量放入消息
        
        Args:
            impulses: (神经脉冲, 优先级)元组列表
            block: 是否阻塞等待队列有空间
            timeout: 阻塞超时时间
            
        Returns:
            int: 成功放入的消息数量
        """
        success_count = 0
        
        for impulse, priority in impulses:
            if self.put(impulse, priority, block, timeout):
                success_count += 1
            else:
                break  # 如果放入失败，停止尝试
        
        return success_count
    
    def batch_get(self, max_count: int, block: bool = True, 
                  timeout: Optional[float] = None) -> List[NeuralImpulse]:
        """批量获取消息
        
        Args:
            max_count: 最大获取数量
            block: 是否阻塞等待队列有消息
            timeout: 阻塞超时时间
            
        Returns:
            List[NeuralImpulse]: 神经脉冲列表
        """
        impulses = []
        
        for _ in range(max_count):
            impulse = self.get(block, timeout)
            if impulse is None:
                break
            impulses.append(impulse)
        
        return impulses
    
    def _is_expired(self, impulse: NeuralImpulse) -> bool:
        """检查消息是否过期
        
        Args:
            impulse: 神经脉冲对象
            
        Returns:
            bool: 是否过期
        """
        if self.message_ttl is None:
            return False
            
        queue_timestamp = impulse.metadata.get("queue_timestamp", time.time())
        return time.time() - queue_timestamp > self.message_ttl

    def _write_loop(self):
        """后台写入循环，批量将内存缓冲写入文件"""
        self.logger.info(
            f"Queue {self.queue_id}: Background write thread started"
        )

        while not self._write_stop_event.is_set():
            try:
                # 每秒批量写入一次
                self._write_stop_event.wait(1.0)

                if self._write_stop_event.is_set():
                    # 退出前刷新所有缓冲数据
                    self._flush_log1_buffer()
                    self._flush_log2_buffer()
                    break

                # 定期刷新缓冲
                if len(self._log1_buffer) > 100:
                    self._flush_log1_buffer()
                if len(self._log2_buffer) > 100:
                    self._flush_log2_buffer()

            except Exception as e:
                self.logger.error(f"Queue {self.queue_id}: Error in write loop: {e}")

        self.logger.info(f"Queue {self.queue_id}: Background write loop exited")

    def _flush_log1_buffer(self):
        """批量刷新log1缓冲区到文件"""
        if not self._log1_buffer:
            return

        with self._write_lock:
            # 批量取出所有待写入的数据
            batch = []
            while self._log1_buffer:
                batch.append(self._log1_buffer.popleft())

            if not batch:
                return

            try:
                if MSGPACK_AVAILABLE:
                    # msgpack 批量写入
                    for message_id, priority, impulse in batch:
                        log_entry = {
                            "id": message_id,
                            "priority": priority,
                            "impulse": impulse.to_dict(),
                            "timestamp": time.time()
                        }
                        packed = msgpack.packb(log_entry, use_bin_type=True)
                        # 写入长度前缀（4字节）+ 数据
                        self._log1_file.write(len(packed).to_bytes(4, 'big'))
                        self._log1_file.write(packed)
                else:
                    # JSON 批量写入
                    for message_id, priority, impulse in batch:
                        log_entry = {
                            "id": message_id,
                            "priority": priority,
                            "impulse": impulse.to_dict(),
                            "timestamp": time.time()
                        }
                        self._log1_file.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

                # 批量flush
                self._log1_file.flush()

            except Exception as e:
                self.logger.error(f"Queue {self.queue_id}: Failed to flush log1 buffer: {e}")

    def _flush_log2_buffer(self):
        """批量刷新log2缓冲区到文件"""
        if not self._log2_buffer:
            return

        with self._write_lock:
            # 批量取出所有待写入的数据
            batch = []
            while self._log2_buffer:
                batch.append(self._log2_buffer.popleft())

            if not batch:
                return

            try:
                if MSGPACK_AVAILABLE:
                    # msgpack 批量写入
                    for message_id in batch:
                        packed = msgpack.packb(message_id, use_bin_type=True)
                        self._log2_file.write(packed)
                else:
                    # JSON 批量写入
                    for message_id in batch:
                        self._log2_file.write(message_id + '\n')

                # 批量flush
                self._log2_file.flush()

            except Exception as e:
                self.logger.error(f"Queue {self.queue_id}: Failed to flush log2 buffer: {e}")

    def _init_wal_logs(self):
        """初始化WAL日志文件（append-only模式）"""
        try:
            if MSGPACK_AVAILABLE:
                # msgpack 使用二进制模式
                self._log1_file = open(self._log1_path, 'ab')
                self._log2_file = open(self._log2_path, 'ab')
                self.logger.info(
                    f"Queue {self.queue_id}: WAL logs initialized with msgpack, "
                    f"log1={self._log1_path}, log2={self._log2_path}"
                )
            else:
                # JSON 使用文本模式
                self._log1_file = open(self._log1_path, 'a', encoding='utf-8')
                self._log2_file = open(self._log2_path, 'a', encoding='utf-8')
                self.logger.info(
                    f"Queue {self.queue_id}: WAL logs initialized with JSON, "
                    f"log1={self._log1_path}, log2={self._log2_path}"
                )
        except Exception as e:
            self.logger.error(f"Queue {self.queue_id}: Failed to initialize WAL logs: {e}")
            raise

    def _close_wal_logs(self):
        """关闭WAL日志文件

        安全改进：
        - 分别处理每个文件的 flush 和 close，避免一个文件失败影响另一个
        - 确保 close() 一定被调用，防止文件句柄泄漏
        """
        for attr_name, log_name in [('_log1_file', 'log1'), ('_log2_file', 'log2')]:
            log_file = getattr(self, attr_name)
            if log_file:
                try:
                    log_file.flush()
                except Exception as e:
                    self.logger.warning(f"Queue {self.queue_id}: Failed to flush {log_name}: {e}")
                try:
                    log_file.close()
                except Exception as e:
                    self.logger.error(f"Queue {self.queue_id}: Failed to close {log_name}: {e}")
                finally:
                    setattr(self, attr_name, None)

    def _cleanup_loop(self):
        """后台清理循环，定期清理已处理消息"""
        self.logger.info(
            f"Queue {self.queue_id}: Background cleanup thread started, "
            f"interval={self.cleanup_interval}s"
        )

        while not self._cleanup_stop_event.is_set():
            try:
                # 等待指定的间隔时间，或直到收到停止信号
                self._cleanup_stop_event.wait(self.cleanup_interval)

                # 如果收到停止信号，执行最后一次清理后退出
                if self._cleanup_stop_event.is_set():
                    self._cleanup_logs()
                    break

                # 执行清理
                self.logger.debug(f"Queue {self.queue_id}: Starting log cleanup")
                self._cleanup_logs()
                self.logger.debug(f"Queue {self.queue_id}: Log cleanup completed")

            except Exception as e:
                self.logger.error(f"Queue {self.queue_id}: Error in cleanup loop: {e}")

        self.logger.info(f"Queue {self.queue_id}: Background cleanup loop exited")

    def _cleanup_logs(self):
        """清理已处理消息：读取log2，从log1中删除已处理的消息

        安全改进：
        1. 使用原子操作（临时文件 + fsync）
        2. 添加备份机制防止数据丢失
        3. 失败时自动恢复
        """
        if not os.path.exists(self._log2_path):
            return

        temp_log1_path = None
        original_log1_backup = None

        try:
            # 读取log2中所有已处理的消息ID
            processed_ids = set()
            with open(self._log2_path, 'rb' if MSGPACK_AVAILABLE else 'r', encoding=None if MSGPACK_AVAILABLE else 'utf-8') as f:
                if MSGPACK_AVAILABLE:
                    # msgpack 解包所有消息ID
                    unpacker = msgpack.Unpacker(f, raw=False)
                    for msg_id in unpacker:
                        if isinstance(msg_id, str):
                            processed_ids.add(msg_id)
                else:
                    # JSON 模式
                    for line in f:
                        line = line.strip()
                        if line:
                            processed_ids.add(line)

            if not processed_ids:
                return

            self.logger.info(
                f"Queue {self.queue_id}: Cleaning up {len(processed_ids)} processed messages"
            )

            # 读取log1，过滤出未处理的消息
            if not os.path.exists(self._log1_path):
                # log1不存在，直接清空log2
                open(self._log2_path, 'w' if not MSGPACK_AVAILABLE else 'wb').close()
                return

            # 创建临时文件在同一文件系统（确保原子替换）
            import tempfile
            temp_fd, temp_log1_path = tempfile.mkstemp(
                dir=os.path.dirname(self._log1_path),
                prefix=os.path.basename(self._log1_path) + '.tmp'
            )
            os.close(temp_fd)

            kept_count = 0

            with open(self._log1_path, 'rb' if MSGPACK_AVAILABLE else 'r', encoding=None if MSGPACK_AVAILABLE else 'utf-8') as f_in, \
                 open(temp_log1_path, 'wb' if MSGPACK_AVAILABLE else 'w', encoding=None if MSGPACK_AVAILABLE else 'utf-8') as f_out:

                if MSGPACK_AVAILABLE:
                    # msgpack 模式：读取长度前缀 + 数据
                    while True:
                        # 读取长度前缀（4字节）
                        length_bytes = f_in.read(4)
                        if not length_bytes or len(length_bytes) < 4:
                            break
                        length = int.from_bytes(length_bytes, 'big')

                        # 读取数据
                        data = f_in.read(length)
                        if not data or len(data) < length:
                            break

                        # 反序列化
                        try:
                            log_entry = msgpack.unpackb(data, raw=False)
                            message_id = log_entry.get(b'id') if isinstance(log_entry.get('id'), bytes) else log_entry.get('id')
                            if message_id not in processed_ids:
                                # 保留未处理的消息
                                f_out.write(length_bytes)
                                f_out.write(data)
                                kept_count += 1
                        except Exception:
                            continue
                else:
                    # JSON 模式
                    for line in f_in:
                        if not line.strip():
                            continue
                        try:
                            log_entry = json.loads(line)
                            message_id = log_entry.get('id')
                            if message_id not in processed_ids:
                                # 保留未处理的消息
                                f_out.write(line)
                                kept_count += 1
                        except json.JSONDecodeError:
                            continue

            # 关键：确保数据落盘
            f_out.flush()
            os.fsync(f_out.fileno())

            # 备份原始文件（以防万一）
            original_log1_backup = self._log1_path + '.backup'
            if os.path.exists(self._log1_path):
                import shutil
                shutil.copy2(self._log1_path, original_log1_backup)

            # 原子替换 log1 文件
            os.replace(temp_log1_path, self._log1_path)
            # 设置文件权限为仅所有者可读写（防止其他用户读取敏感数据）
            os.chmod(self._log1_path, 0o600)

            # 清空 log2 文件
            with open(self._log2_path, 'w' if not MSGPACK_AVAILABLE else 'wb') as f:
                if MSGPACK_AVAILABLE:
                    f.flush()
                    os.fsync(f.fileno())

            # 删除备份（成功后）
            if original_log1_backup and os.path.exists(original_log1_backup):
                os.remove(original_log1_backup)

            self.logger.info(
                f"Queue {self.queue_id}: Cleanup completed, "
                f"kept {kept_count} unprocessed messages, removed {len(processed_ids)} processed"
            )

        except Exception as e:
            self.logger.error(f"Queue {self.queue_id}: Error during log cleanup: {e}", exc_info=True)

            # 清理临时文件
            if temp_log1_path and os.path.exists(temp_log1_path):
                try:
                    os.remove(temp_log1_path)
                except Exception:
                    pass

            # 如果有备份，恢复原始文件
            if original_log1_backup and os.path.exists(original_log1_backup):
                try:
                    if os.path.exists(self._log1_path):
                        os.remove(self._log1_path)
                    os.replace(original_log1_backup, self._log1_path)
                    # 设置文件权限为仅所有者可读写
                    os.chmod(self._log1_path, 0o600)
                    self.logger.info(f"Queue {self.queue_id}: Restored log1 from backup after cleanup failure")
                except Exception as restore_error:
                    self.logger.error(
                        f"Queue {self.queue_id}: Failed to restore log1 backup: {restore_error}"
                    )

    def _load_from_log1(self):
        """从log1恢复未处理的消息到队列"""
        if not os.path.exists(self._log1_path):
            self.logger.info(f"Queue {self.queue_id}: No existing log1 found, starting fresh")
            return

        try:
            # 先执行一次清理（移除上次运行已处理的消息）
            if os.path.exists(self._log2_path):
                self.logger.info(f"Queue {self.queue_id}: Cleaning up previous run's processed messages")
                self._cleanup_logs()

            loaded_count = 0
            current_time = time.time()

            with open(self._log1_path, 'rb' if MSGPACK_AVAILABLE else 'r', encoding=None if MSGPACK_AVAILABLE else 'utf-8') as f:
                if MSGPACK_AVAILABLE:
                    # msgpack 模式：读取长度前缀 + 数据
                    while True:
                        # 读取长度前缀（4字节）
                        length_bytes = f.read(4)
                        if not length_bytes or len(length_bytes) < 4:
                            break
                        length = int.from_bytes(length_bytes, 'big')

                        # 读取数据
                        data = f.read(length)
                        if not data or len(data) < length:
                            break

                        # 反序列化
                        try:
                            log_entry = msgpack.unpackb(data, raw=False)
                            self._process_log_entry(log_entry, current_time)
                            loaded_count += 1
                        except Exception as e:
                            self.logger.warning(f"Queue {self.queue_id}: Failed to load msgpack entry: {e}")
                            continue
                else:
                    # JSON 模式
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            log_entry = json.loads(line)
                            self._process_log_entry(log_entry, current_time)
                            loaded_count += 1
                        except (json.JSONDecodeError, Exception) as e:
                            self.logger.warning(f"Queue {self.queue_id}: Failed to load JSON entry: {e}")
                            continue

            # 更新队列大小
            self._stats.queue_size = self._queue.qsize()

            self.logger.info(
                f"Queue {self.queue_id}: Loaded {loaded_count} messages from log1, "
                f"current queue size: {self._stats.queue_size}"
            )

        except Exception as e:
            self.logger.error(f"Queue {self.queue_id}: Error loading from log1: {e}")
            # 如果加载失败，清空队列以避免不一致状态
            self.clear()

    def _process_log_entry(self, log_entry: Dict[str, Any], current_time: float):
        """处理单个日志条目并加载到队列"""
        try:
            message_id = log_entry.get('id')
            priority = log_entry.get('priority', 5)
            timestamp = log_entry.get('timestamp', current_time)
            impulse_dict = log_entry.get('impulse', {})

            # 从字典重建神经脉冲
            impulse = NeuralImpulse.from_dict(impulse_dict)

            # 确保元数据中有必要的信息
            impulse.metadata["message_id"] = message_id
            impulse.metadata["queue_timestamp"] = timestamp
            impulse.metadata["priority"] = priority

            # 检查消息是否过期
            if self._is_expired(impulse):
                return

            # 放入队列
            item = (priority, timestamp, message_id, impulse)
            self._queue.put(item, block=False)

            # 更新消息映射和统计
            self._message_map[message_id] = impulse
            self._stats.total_messages += 1

            # 更新优先级分布
            priority_key = f"priority_{priority}"
            self._stats.priority_distribution[priority_key] = \
                self._stats.priority_distribution.get(priority_key, 0) + 1
        except Exception as e:
            self.logger.warning(f"Queue {self.queue_id}: Failed to process log entry: {e}")


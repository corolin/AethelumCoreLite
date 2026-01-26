import queue
import threading
import time
import uuid
import json
import os
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from .message import NeuralImpulse

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
                 persistence_interval: float = 30.0):
        """初始化突触队列

        Args:
            queue_id: 队列唯一标识符
            max_size: 队列最大大小，0表示无限制
            enable_persistence: 是否启用持久化
            persistence_path: 持久化文件路径
            message_ttl: 消息生存时间(秒)，None表示不过期
            persistence_interval: 后台持久化间隔(秒)，默认30秒
        """
        self.queue_id = queue_id
        self.max_size = max_size
        self.enable_persistence = enable_persistence
        self.persistence_path = persistence_path or f"queue_{queue_id}.json"
        self.message_ttl = message_ttl
        self.persistence_interval = persistence_interval

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

        # 后台持久化线程
        self._persistence_stop_event = threading.Event()
        self._persistence_thread = None

        # 如果启用持久化，尝试加载已有数据
        if self.enable_persistence:
            self._load_from_disk()
            # 启动后台持久化线程
            self._persistence_thread = threading.Thread(
                target=self._persistence_loop,
                daemon=True,
                name=f"QueuePersistence-{queue_id}"
            )
            self._persistence_thread.start()
    
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
        message_id = str(uuid.uuid4())
        impulse.metadata["message_id"] = message_id
        impulse.metadata["queue_timestamp"] = time.time()
        impulse.metadata["priority"] = priority
        
        try:
            # 使用优先级队列，(priority, timestamp, message_id, impulse)
            item = (priority, time.time(), message_id, impulse)
            self._queue.put(item, block=block, timeout=timeout)
            
            with self._lock:
                self._message_map[message_id] = impulse
                self._stats.total_messages += 1
                self._stats.last_activity = time.time()
                self._stats.queue_size = self._queue.qsize()

                # 更新优先级分布
                priority_key = f"priority_{priority}"
                self._stats.priority_distribution[priority_key] = \
                    self._stats.priority_distribution.get(priority_key, 0) + 1

            # 持久化由后台线程定期处理，不再立即持久化
            return True
        except queue.Full:
            return False
    
    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[NeuralImpulse]:
        """从队列获取神经脉冲
        
        Args:
            block: 是否阻塞等待队列有消息
            timeout: 阻塞超时时间
            
        Returns:
            NeuralImpulse: 神经脉冲对象，队列为空时返回None
        """
        if self._closed:
            return None
            
        try:
            priority, timestamp, message_id, impulse = self._queue.get(block=block, timeout=timeout)
            
            # 检查消息是否过期
            if self._is_expired(impulse):
                self._queue.task_done()
                return self.get(block, timeout)  # 递归获取下一个消息
            
            processing_start = time.time()
            
            with self._lock:
                # 从映射中移除
                if message_id in self._message_map:
                    del self._message_map[message_id]
                
                self._stats.queue_size = self._queue.qsize()
                self._stats.last_activity = time.time()
            
            return impulse
        except queue.Empty:
            return None
    
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
                self._save_to_disk()
    
    def close(self):
        """关闭队列"""
        # 停止后台持久化线程
        if self._persistence_thread is not None:
            self._persistence_stop_event.set()
            # 等待线程结束（最多等待5秒）
            self._persistence_thread.join(timeout=5.0)
            self.logger.info(f"Queue {self.queue_id}: Background persistence thread stopped")

        with self._lock:
            self._closed = True
            self._stats.active_time = time.time() - self._start_time

            if self.enable_persistence:
                self._save_to_disk()
                self.logger.info(f"Queue {self.queue_id}: Final state persisted to disk")
    
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
            return self._stats
    
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

    def _persistence_loop(self):
        """后台持久化循环，定期保存队列状态到磁盘"""
        self.logger.info(
            f"Queue {self.queue_id}: Background persistence thread started, "
            f"interval={self.persistence_interval}s"
        )

        while not self._persistence_stop_event.is_set():
            try:
                # 等待指定的间隔时间，或直到收到停止信号
                self._persistence_stop_event.wait(self.persistence_interval)

                # 如果收到停止信号，退出循环
                if self._persistence_stop_event.is_set():
                    break

                # 执行持久化
                self.logger.debug(f"Queue {self.queue_id}: Starting periodic persistence")
                self._save_to_disk()
                self.logger.debug(f"Queue {self.queue_id}: Periodic persistence completed")

            except Exception as e:
                self.logger.error(f"Queue {self.queue_id}: Error in persistence loop: {e}")

        self.logger.info(f"Queue {self.queue_id}: Background persistence loop exited")

    def _save_to_disk(self):
        """将队列状态保存到磁盘"""
        if not self.enable_persistence:
            return
            
        try:
            # 准备要保存的数据
            data = {
                "queue_id": self.queue_id,
                "max_size": self.max_size,
                "message_ttl": self.message_ttl,
                "stats": asdict(self._stats),
                "messages": []
            }
            
            # 保存消息
            with self._lock:
                # 创建临时队列来遍历而不影响原队列
                temp_items = []
                while not self._queue.empty():
                    try:
                        item = self._queue.get_nowait()
                        temp_items.append(item)
                        
                        priority, timestamp, message_id, impulse = item
                        # 将神经脉冲转换为可序列化的字典
                        impulse_dict = impulse.to_dict()
                        data["messages"].append({
                            "priority": priority,
                            "timestamp": timestamp,
                            "message_id": message_id,
                            "impulse": impulse_dict
                        })
                    except queue.Empty:
                        break
                
                # 将消息放回队列
                for item in temp_items:
                    self._queue.put(item)
            
            # 写入文件
            with open(self.persistence_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # 记录错误但不中断程序
            self.logger.error(f"Error saving queue to disk: {e}")
    
    def _load_from_disk(self):
        """从磁盘加载队列状态"""
        if not self.enable_persistence or not os.path.exists(self.persistence_path):
            return
            
        try:
            with open(self.persistence_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 加载统计信息
            if "stats" in data:
                stats_dict = data["stats"]
                self._stats = QueueStats(
                    total_messages=stats_dict.get("total_messages", 0),
                    failed_messages=stats_dict.get("failed_messages", 0),
                    processed_messages=stats_dict.get("processed_messages", 0),
                    active_time=stats_dict.get("active_time", 0.0),
                    last_activity=stats_dict.get("last_activity", 0.0),
                    average_processing_time=stats_dict.get("average_processing_time", 0.0),
                    queue_size=0,  # 将在加载消息后更新
                    priority_distribution=stats_dict.get("priority_distribution", {})
                )
            
            # 加载消息
            if "messages" in data:
                for msg_data in data["messages"]:
                    priority = msg_data.get("priority", 5)
                    timestamp = msg_data.get("timestamp", time.time())
                    message_id = msg_data.get("message_id", str(uuid.uuid4()))
                    impulse_dict = msg_data.get("impulse", {})
                    
                    # 从字典重建神经脉冲
                    impulse = NeuralImpulse.from_dict(impulse_dict)
                    
                    # 确保元数据中有必要的信息
                    impulse.metadata["message_id"] = message_id
                    impulse.metadata["queue_timestamp"] = timestamp
                    impulse.metadata["priority"] = priority
                    
                    # 放入队列
                    item = (priority, timestamp, message_id, impulse)
                    self._queue.put(item, block=False)
                    
                    # 更新消息映射
                    self._message_map[message_id] = impulse
                
                # 更新队列大小
                self._stats.queue_size = self._queue.qsize()
        except Exception as e:
            # 记录错误但不中断程序
            self.logger.error(f"Error loading queue from disk: {e}")
            # 如果加载失败，清空队列以避免不一致状态
            self.clear()
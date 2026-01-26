import threading
import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid

from .worker import AxonWorker, WorkerState, WorkerStats
from .queue import SynapticQueue
from .router import NeuralSomaRouter
from .hooks import BaseHook


class ManagerState(Enum):
    """管理器状态枚举"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WorkerConfig:
    """工作器配置"""
    name: str
    input_queue: SynapticQueue
    hooks: Optional[List[BaseHook]] = None
    router: Optional[NeuralSomaRouter] = None
    error_handler: Optional[Callable[[Exception, Any], None]] = None
    worker_id: Optional[str] = None
    max_consecutive_failures: int = 5
    recovery_delay: float = 5.0
    health_check_interval: float = 30.0
    processing_timeout: float = 60.0
    auto_restart: bool = True
    priority: int = 0  # 优先级，数值越高优先级越高


@dataclass
class ManagerStats:
    """管理器统计信息"""
    manager_id: str
    name: str
    state: ManagerState = ManagerState.INITIALIZING
    start_time: float = field(default_factory=time.time)
    total_workers: int = 0
    running_workers: int = 0
    paused_workers: int = 0
    stopped_workers: int = 0
    error_workers: int = 0
    recovering_workers: int = 0
    total_processed_messages: int = 0
    total_failed_messages: int = 0
    average_success_rate: float = 0.0
    average_health_score: float = 0.0
    uptime: float = 0.0
    last_health_check: float = field(default_factory=time.time)
    auto_restarts: int = 0


class WorkerManager:
    """工作器管理器，负责管理多个AxonWorker实例
    
    提供工作器的创建、启动、停止、监控和自动恢复功能。
    支持工作器的优先级管理和负载均衡。
    """
    
    def __init__(self,
                 name: str,
                 manager_id: Optional[str] = None,
                 health_check_interval: float = 60.0,
                 auto_recovery: bool = True,
                 max_recovery_attempts: int = 3):
        """初始化工作器管理器

        Args:
            name: 管理器名称
            manager_id: 管理器ID，如果不提供则自动生成
            health_check_interval: 健康检查间隔（秒）
            auto_recovery: 是否启用自动恢复
            max_recovery_attempts: 最大恢复尝试次数
        """
        self.name = name
        self.manager_id = manager_id or str(uuid.uuid4())
        self.health_check_interval = health_check_interval
        self.auto_recovery = auto_recovery
        self.max_recovery_attempts = max_recovery_attempts

        # 日志记录器
        import logging
        self.logger = logging.getLogger(f"WorkerManager.{name}")

        # 管理器状态
        self._state = ManagerState.INITIALIZING
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始状态为运行

        # 工作器管理
        self._workers: Dict[str, AxonWorker] = {}
        self._worker_configs: Dict[str, WorkerConfig] = {}
        self._worker_recovery_attempts: Dict[str, int] = {}

        # 统计信息
        self._stats = ManagerStats(
            manager_id=self.manager_id,
            name=self.name,
            state=self._state
        )

        # 健康检查线程
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True
        )

        # 工作器事件回调
        self._worker_event_callbacks: List[Callable[[str, WorkerState, WorkerState], None]] = []
    
    def add_worker(self, config: WorkerConfig) -> str:
        """添加工作器
        
        Args:
            config: 工作器配置
            
        Returns:
            str: 工作器ID
        """
        # 生成工作器ID
        worker_id = config.worker_id or str(uuid.uuid4())
        
        # 创建工作器
        worker = AxonWorker(
            name=config.name,
            input_queue=config.input_queue,
            hooks=config.hooks,
            router=config.router,
            error_handler=config.error_handler,
            worker_id=worker_id,
            max_consecutive_failures=config.max_consecutive_failures,
            recovery_delay=config.recovery_delay,
            health_check_interval=config.health_check_interval,
            processing_timeout=config.processing_timeout
        )
        
        # 存储工作器和配置
        self._workers[worker_id] = worker
        self._worker_configs[worker_id] = config
        self._worker_recovery_attempts[worker_id] = 0
        
        # 更新统计信息
        self._update_stats()
        
        return worker_id
    
    def remove_worker(self, worker_id: str) -> bool:
        """移除工作器
        
        Args:
            worker_id: 工作器ID
            
        Returns:
            bool: 是否成功移除
        """
        if worker_id not in self._workers:
            return False
        
        # 停止工作器
        worker = self._workers[worker_id]
        if worker.is_alive():
            worker.stop()
            worker.join(timeout=5.0)
        
        # 移除工作器
        del self._workers[worker_id]
        del self._worker_configs[worker_id]
        del self._worker_recovery_attempts[worker_id]
        
        # 更新统计信息
        self._update_stats()
        
        return True
    
    def start_worker(self, worker_id: str) -> bool:
        """启动工作器
        
        Args:
            worker_id: 工作器ID
            
        Returns:
            bool: 是否成功启动
        """
        if worker_id not in self._workers:
            return False
        
        worker = self._workers[worker_id]
        if not worker.is_alive():
            worker.start()
            
            # 更新统计信息
            self._update_stats()
            
            return True
        
        return False
    
    def stop_worker(self, worker_id: str) -> bool:
        """停止工作器
        
        Args:
            worker_id: 工作器ID
            
        Returns:
            bool: 是否成功停止
        """
        if worker_id not in self._workers:
            return False
        
        worker = self._workers[worker_id]
        if worker.is_alive():
            worker.stop()
            worker.join(timeout=5.0)
            
            # 更新统计信息
            self._update_stats()
            
            return True
        
        return False
    
    def pause_worker(self, worker_id: str) -> bool:
        """暂停工作器
        
        Args:
            worker_id: 工作器ID
            
        Returns:
            bool: 是否成功暂停
        """
        if worker_id not in self._workers:
            return False
        
        worker = self._workers[worker_id]
        worker.pause()
        
        # 更新统计信息
        self._update_stats()
        
        return True
    
    def resume_worker(self, worker_id: str) -> bool:
        """恢复工作器
        
        Args:
            worker_id: 工作器ID
            
        Returns:
            bool: 是否成功恢复
        """
        if worker_id not in self._workers:
            return False
        
        worker = self._workers[worker_id]
        worker.resume()
        
        # 更新统计信息
        self._update_stats()
        
        return True
    
    def start_all_workers(self) -> int:
        """启动所有工作器
        
        Returns:
            int: 成功启动的工作器数量
        """
        started_count = 0
        
        for worker_id in self._workers:
            if self.start_worker(worker_id):
                started_count += 1
        
        return started_count
    
    def stop_all_workers(self) -> int:
        """停止所有工作器
        
        Returns:
            int: 成功停止的工作器数量
        """
        stopped_count = 0
        
        for worker_id in self._workers:
            if self.stop_worker(worker_id):
                stopped_count += 1
        
        return stopped_count
    
    def pause_all_workers(self) -> int:
        """暂停所有工作器
        
        Returns:
            int: 成功暂停的工作器数量
        """
        paused_count = 0
        
        for worker_id in self._workers:
            if self.pause_worker(worker_id):
                paused_count += 1
        
        return paused_count
    
    def resume_all_workers(self) -> int:
        """恢复所有工作器
        
        Returns:
            int: 成功恢复的工作器数量
        """
        resumed_count = 0
        
        for worker_id in self._workers:
            if self.resume_worker(worker_id):
                resumed_count += 1
        
        return resumed_count
    
    def get_worker(self, worker_id: str) -> Optional[AxonWorker]:
        """获取工作器
        
        Args:
            worker_id: 工作器ID
            
        Returns:
            Optional[AxonWorker]: 工作器实例，如果不存在则返回None
        """
        return self._workers.get(worker_id)
    
    def get_all_workers(self) -> Dict[str, AxonWorker]:
        """获取所有工作器
        
        Returns:
            Dict[str, AxonWorker]: 工作器字典
        """
        return self._workers.copy()
    
    def get_worker_stats(self, worker_id: str) -> Optional[WorkerStats]:
        """获取工作器统计信息
        
        Args:
            worker_id: 工作器ID
            
        Returns:
            Optional[WorkerStats]: 工作器统计信息，如果工作器不存在则返回None
        """
        if worker_id not in self._workers:
            return None
        
        return self._workers[worker_id].get_stats()
    
    def get_all_worker_stats(self) -> Dict[str, WorkerStats]:
        """获取所有工作器统计信息
        
        Returns:
            Dict[str, WorkerStats]: 工作器统计信息字典
        """
        stats = {}
        
        for worker_id, worker in self._workers.items():
            stats[worker_id] = worker.get_stats()
        
        return stats
    
    def get_stats(self) -> ManagerStats:
        """获取管理器统计信息
        
        Returns:
            ManagerStats: 管理器统计信息
        """
        # 更新统计信息
        self._update_stats()
        
        return self._stats
    
    def get_state(self) -> ManagerState:
        """获取管理器状态
        
        Returns:
            ManagerState: 管理器状态
        """
        return self._state
    
    def start(self):
        """启动管理器"""
        self._state = ManagerState.RUNNING
        self._stats.state = self._state
        self._stats.start_time = time.time()
        
        # 启动健康检查线程
        self._health_check_thread.start()
        
        # 启动所有工作器
        self.start_all_workers()
    
    def stop(self):
        """停止管理器"""
        self._state = ManagerState.STOPPING
        self._stats.state = self._state
        
        # 停止所有工作器
        self.stop_all_workers()
        
        # 停止健康检查线程
        self._stop_event.set()
        
        self._state = ManagerState.STOPPED
        self._stats.state = self._state
    
    def pause(self):
        """暂停管理器"""
        self._state = ManagerState.PAUSED
        self._stats.state = self._state
        
        # 暂停所有工作器
        self.pause_all_workers()
    
    def resume(self):
        """恢复管理器"""
        self._state = ManagerState.RUNNING
        self._stats.state = self._state
        
        # 恢复所有工作器
        self.resume_all_workers()
    
    def add_worker_event_callback(self, callback: Callable[[str, WorkerState, WorkerState], None]):
        """添加工作器事件回调
        
        Args:
            callback: 回调函数，参数为(worker_id, old_state, new_state)
        """
        self._worker_event_callbacks.append(callback)
    
    def remove_worker_event_callback(self, callback: Callable[[str, WorkerState, WorkerState], None]):
        """移除工作器事件回调
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._worker_event_callbacks:
            self._worker_event_callbacks.remove(callback)
    
    def _health_check_loop(self):
        """健康检查循环"""
        while not self._stop_event.is_set():
            time.sleep(self.health_check_interval)
            
            # 检查所有工作器的健康状态
            self._check_workers_health()
            
            # 更新统计信息
            self._update_stats()
            
            # 更新最后健康检查时间
            self._stats.last_health_check = time.time()
    
    def _check_workers_health(self):
        """检查所有工作器的健康状态"""
        # 使用快照遍历，避免在遍历过程中修改字典导致的并发安全问题
        workers_snapshot = list(self._workers.items())

        for worker_id, worker in workers_snapshot:
            old_state = worker.get_state()

            # 检查工作器是否健康
            if not worker.is_healthy():
                self.logger.warning(f"Worker {worker.name} is unhealthy: {worker.get_stats().health_score}")

                # 如果启用自动恢复且工作器已停止，尝试重启
                if (self.auto_recovery and
                    not worker.is_alive() and
                    self._worker_configs[worker_id].auto_restart and
                    self._worker_recovery_attempts[worker_id] < self.max_recovery_attempts):

                    self.logger.info(f"Attempting to restart worker {worker.name} (attempt {self._worker_recovery_attempts[worker_id] + 1})")

                    # 增加重启尝试次数
                    self._worker_recovery_attempts[worker_id] += 1

                    # 重启工作器
                    if self.start_worker(worker_id):
                        self._stats.auto_restarts += 1
                        self.logger.info(f"Successfully restarted worker {worker.name}")
                    else:
                        self.logger.error(f"Failed to restart worker {worker.name}")
            else:
                # 重置恢复尝试次数
                self._worker_recovery_attempts[worker_id] = 0

            # 检查状态变化
            new_state = worker.get_state()
            if old_state != new_state:
                # 通知回调
                for callback in self._worker_event_callbacks:
                    try:
                        callback(worker_id, old_state, new_state)
                    except Exception as e:
                        self.logger.error(f"Error in worker event callback: {e}")
    
    def _update_stats(self):
        """更新统计信息"""
        # 重置计数
        self._stats.total_workers = len(self._workers)
        self._stats.running_workers = 0
        self._stats.paused_workers = 0
        self._stats.stopped_workers = 0
        self._stats.error_workers = 0
        self._stats.recovering_workers = 0
        self._stats.total_processed_messages = 0
        self._stats.total_failed_messages = 0
        self._stats.average_success_rate = 0.0
        self._stats.average_health_score = 0.0
        
        # 统计各状态工作器数量
        for worker in self._workers.values():
            stats = worker.get_stats()
            
            if stats.state == WorkerState.RUNNING:
                self._stats.running_workers += 1
            elif stats.state == WorkerState.PAUSED:
                self._stats.paused_workers += 1
            elif stats.state == WorkerState.STOPPED:
                self._stats.stopped_workers += 1
            elif stats.state == WorkerState.ERROR:
                self._stats.error_workers += 1
            elif stats.state == WorkerState.RECOVERING:
                self._stats.recovering_workers += 1
            
            self._stats.total_processed_messages += stats.processed_messages
            self._stats.total_failed_messages += stats.failed_messages
        
        # 计算平均成功率和健康分数
        if self._stats.total_workers > 0:
            total_success_rate = 0.0
            total_health_score = 0.0
            
            for worker in self._workers.values():
                stats = worker.get_stats()
                total_success_rate += stats.success_rate
                total_health_score += stats.health_score
            
            self._stats.average_success_rate = total_success_rate / self._stats.total_workers
            self._stats.average_health_score = total_health_score / self._stats.total_workers
        
        # 更新运行时间
        self._stats.uptime = time.time() - self._stats.start_time
        
        # 更新状态
        self._stats.state = self._state
    
    def __str__(self) -> str:
        """返回管理器的字符串表示
        
        Returns:
            str: 管理器字符串表示
        """
        return f"WorkerManager(name={self.name}, state={self._state.value}, workers={self._stats.total_workers})"
    
    def __repr__(self) -> str:
        """返回管理器的详细字符串表示
        
        Returns:
            str: 管理器详细字符串表示
        """
        return (f"WorkerManager(id={self.manager_id}, name={self.name}, state={self._state.value}, "
                f"total_workers={self._stats.total_workers}, running_workers={self._stats.running_workers}, "
                f"average_success_rate={self._stats.average_success_rate:.2f}%, "
                f"average_health_score={self._stats.average_health_score:.2f})")

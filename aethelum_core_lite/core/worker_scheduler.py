import threading
import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid
import heapq

from .worker import AxonWorker, WorkerState, WorkerStats
from .queue import SynapticQueue
from .message import NeuralImpulse
from .worker_manager import WorkerManager, WorkerConfig


class SchedulingStrategy(Enum):
    """调度策略枚举"""
    ROUND_ROBIN = "round_robin"  # 轮询调度
    LEAST_LOADED = "least_loaded"  # 最少负载调度
    PRIORITY_BASED = "priority_based"  # 基于优先级调度
    HEALTH_AWARE = "health_aware"  # 健康感知调度
    ADAPTIVE = "adaptive"  # 自适应调度


class SchedulerState(Enum):
    """调度器状态枚举"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class WorkerLoadInfo:
    """工作器负载信息"""
    worker_id: str
    worker: AxonWorker
    load_score: float  # 负载分数，越高表示负载越高
    priority: int  # 工作器优先级
    health_score: float  # 健康分数
    queue_size: int  # 输入队列大小
    processing_rate: float  # 处理速率（消息/秒）
    success_rate: float  # 成功率
    last_updated: float  # 最后更新时间


@dataclass
class SchedulerStats:
    """调度器统计信息"""
    scheduler_id: str
    name: str
    state: SchedulerState = SchedulerState.INITIALIZING
    start_time: float = field(default_factory=time.time)
    total_scheduled_messages: int = 0
    total_failed_schedules: int = 0
    average_scheduling_time: float = 0.0
    scheduling_rate: float = 0.0  # 调度速率（消息/秒）
    uptime: float = 0.0
    last_scheduling_time: float = 0.0
    strategy: SchedulingStrategy = SchedulingStrategy.ROUND_ROBIN
    worker_count: int = 0
    active_workers: int = 0
    load_balance_score: float = 0.0  # 负载均衡分数


class WorkerScheduler:
    """工作器调度器，负责根据负载和优先级智能调度工作器
    
    提供多种调度策略，支持动态负载均衡和自适应调整。
    监控工作器状态和性能，优化任务分配。
    """
    
    def __init__(self, 
                 name: str,
                 worker_manager: WorkerManager,
                 strategy: SchedulingStrategy = SchedulingStrategy.ADAPTIVE,
                 scheduler_id: Optional[str] = None,
                 scheduling_interval: float = 1.0,
                 load_update_interval: float = 5.0,
                 enable_adaptive_strategy: bool = True):
        """初始化工作器调度器
        
        Args:
            name: 调度器名称
            worker_manager: 工作器管理器
            strategy: 调度策略
            scheduler_id: 调度器ID，如果不提供则自动生成
            scheduling_interval: 调度间隔（秒）
            load_update_interval: 负载更新间隔（秒）
            enable_adaptive_strategy: 是否启用自适应策略调整
        """
        self.name = name
        self.worker_manager = worker_manager
        self.strategy = strategy
        self.scheduler_id = scheduler_id or str(uuid.uuid4())
        self.scheduling_interval = scheduling_interval
        self.load_update_interval = load_update_interval
        self.enable_adaptive_strategy = enable_adaptive_strategy
        
        # 调度器状态
        self._state = SchedulerState.INITIALIZING
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始状态为运行
        
        # 工作器负载信息
        self._worker_load_info: Dict[str, WorkerLoadInfo] = {}
        
        # 轮询调度索引
        self._round_robin_index = 0
        
        # 统计信息
        self._stats = SchedulerStats(
            scheduler_id=self.scheduler_id,
            name=self.name,
            state=self._state,
            strategy=self.strategy
        )
        
        # 调度线程
        self._scheduling_thread = threading.Thread(
            target=self._scheduling_loop,
            daemon=True
        )
        
        # 负载更新线程
        self._load_update_thread = threading.Thread(
            target=self._load_update_loop,
            daemon=True
        )
        
        # 策略性能统计
        self._strategy_performance: Dict[SchedulingStrategy, float] = {
            SchedulingStrategy.ROUND_ROBIN: 0.0,
            SchedulingStrategy.LEAST_LOADED: 0.0,
            SchedulingStrategy.PRIORITY_BASED: 0.0,
            SchedulingStrategy.HEALTH_AWARE: 0.0,
            SchedulingStrategy.ADAPTIVE: 0.0
        }
        
        # 策略切换阈值
        self._strategy_switch_threshold = 0.1  # 性能差异阈值
        
        # 调度事件回调
        self._scheduling_callbacks: List[Callable[[str, str, bool], None]] = []
    
    def schedule_message(self, message: NeuralImpulse, target_workers: Optional[List[str]] = None) -> bool:
        """调度消息到工作器
        
        Args:
            message: 要调度的消息
            target_workers: 目标工作器ID列表，如果为None则自动选择
            
        Returns:
            bool: 是否成功调度
        """
        start_time = time.time()
        
        try:
            # 如果指定了目标工作器，直接调度
            if target_workers:
                for worker_id in target_workers:
                    worker = self.worker_manager.get_worker(worker_id)
                    if worker and worker.get_state() == WorkerState.RUNNING:
                        worker.input_queue.put(message)
                        self._notify_scheduling_callback(worker_id, message.id, True)
                        self._update_scheduling_stats(True, time.time() - start_time)
                        return True
                
                # 所有目标工作器都不可用
                self._notify_scheduling_callback("", message.id, False)
                self._update_scheduling_stats(False, time.time() - start_time)
                return False
            
            # 自动选择工作器
            selected_worker_id = self._select_worker(message)
            
            if selected_worker_id:
                worker = self.worker_manager.get_worker(selected_worker_id)
                if worker:
                    worker.input_queue.put(message)
                    self._notify_scheduling_callback(selected_worker_id, message.id, True)
                    self._update_scheduling_stats(True, time.time() - start_time)
                    return True
            
            # 没有可用的工作器
            self._notify_scheduling_callback("", message.id, False)
            self._update_scheduling_stats(False, time.time() - start_time)
            return False
            
        except Exception as e:
            print(f"Error scheduling message {message.id}: {e}")
            self._notify_scheduling_callback("", message.id, False)
            self._update_scheduling_stats(False, time.time() - start_time)
            return False
    
    def _select_worker(self, message: NeuralImpulse) -> Optional[str]:
        """根据当前策略选择工作器
        
        Args:
            message: 要调度的消息
            
        Returns:
            Optional[str]: 选中的工作器ID，如果没有可用的工作器则返回None
        """
        # 获取所有可用的工作器
        available_workers = self._get_available_workers()
        
        if not available_workers:
            return None
        
        # 根据策略选择工作器
        if self.strategy == SchedulingStrategy.ROUND_ROBIN:
            return self._select_worker_round_robin(available_workers)
        elif self.strategy == SchedulingStrategy.LEAST_LOADED:
            return self._select_worker_least_loaded(available_workers)
        elif self.strategy == SchedulingStrategy.PRIORITY_BASED:
            return self._select_worker_priority_based(available_workers)
        elif self.strategy == SchedulingStrategy.HEALTH_AWARE:
            return self._select_worker_health_aware(available_workers)
        elif self.strategy == SchedulingStrategy.ADAPTIVE:
            return self._select_worker_adaptive(available_workers, message)
        else:
            # 默认使用轮询策略
            return self._select_worker_round_robin(available_workers)
    
    def _get_available_workers(self) -> List[WorkerLoadInfo]:
        """获取所有可用的工作器
        
        Returns:
            List[WorkerLoadInfo]: 可用的工作器负载信息列表
        """
        available_workers = []
        
        for worker_id, load_info in self._worker_load_info.items():
            worker = self.worker_manager.get_worker(worker_id)
            if worker and worker.get_state() == WorkerState.RUNNING:
                available_workers.append(load_info)
        
        return available_workers
    
    def _select_worker_round_robin(self, available_workers: List[WorkerLoadInfo]) -> str:
        """使用轮询策略选择工作器
        
        Args:
            available_workers: 可用的工作器列表
            
        Returns:
            str: 选中的工作器ID
        """
        if not available_workers:
            return ""
        
        # 更新轮询索引
        self._round_robin_index = (self._round_robin_index + 1) % len(available_workers)
        
        return available_workers[self._round_robin_index].worker_id
    
    def _select_worker_least_loaded(self, available_workers: List[WorkerLoadInfo]) -> str:
        """使用最少负载策略选择工作器
        
        Args:
            available_workers: 可用的工作器列表
            
        Returns:
            str: 选中的工作器ID
        """
        if not available_workers:
            return ""
        
        # 按负载分数排序，选择负载最低的工作器
        sorted_workers = sorted(available_workers, key=lambda w: w.load_score)
        
        return sorted_workers[0].worker_id
    
    def _select_worker_priority_based(self, available_workers: List[WorkerLoadInfo]) -> str:
        """使用基于优先级策略选择工作器
        
        Args:
            available_workers: 可用的工作器列表
            
        Returns:
            str: 选中的工作器ID
        """
        if not available_workers:
            return ""
        
        # 按优先级排序，选择优先级最高的工作器
        sorted_workers = sorted(available_workers, key=lambda w: -w.priority)
        
        return sorted_workers[0].worker_id
    
    def _select_worker_health_aware(self, available_workers: List[WorkerLoadInfo]) -> str:
        """使用健康感知策略选择工作器
        
        Args:
            available_workers: 可用的工作器列表
            
        Returns:
            str: 选中的工作器ID
        """
        if not available_workers:
            return ""
        
        # 按健康分数排序，选择最健康的工作器
        sorted_workers = sorted(available_workers, key=lambda w: -w.health_score)
        
        return sorted_workers[0].worker_id
    
    def _select_worker_adaptive(self, available_workers: List[WorkerLoadInfo], message: NeuralImpulse) -> str:
        """使用自适应策略选择工作器
        
        Args:
            available_workers: 可用的工作器列表
            message: 要调度的消息
            
        Returns:
            str: 选中的工作器ID
        """
        if not available_workers:
            return ""
        
        # 计算每个工作器的综合分数
        worker_scores = []
        
        for worker_info in available_workers:
            # 综合考虑负载、优先级和健康状态
            load_factor = 1.0 / (1.0 + worker_info.load_score)  # 负载越低分数越高
            priority_factor = worker_info.priority / 100.0  # 优先级因子
            health_factor = worker_info.health_score  # 健康因子
            
            # 综合分数
            score = 0.4 * load_factor + 0.3 * priority_factor + 0.3 * health_factor
            
            worker_scores.append((score, worker_info.worker_id))
        
        # 按分数排序，选择分数最高的工作器
        worker_scores.sort(key=lambda x: -x[0])
        
        return worker_scores[0][1]
    
    def _scheduling_loop(self):
        """调度循环"""
        while not self._stop_event.is_set():
            time.sleep(self.scheduling_interval)
            
            # 检查是否暂停
            if not self._pause_event.is_set():
                continue
            
            # 更新统计信息
            self._update_stats()
            
            # 自适应策略调整
            if self.enable_adaptive_strategy:
                self._adaptive_strategy_adjustment()
    
    def _load_update_loop(self):
        """负载更新循环"""
        while not self._stop_event.is_set():
            time.sleep(self.load_update_interval)
            
            # 更新所有工作器的负载信息
            self._update_worker_load_info()
    
    def _update_worker_load_info(self):
        """更新所有工作器的负载信息"""
        all_workers = self.worker_manager.get_all_workers()
        
        for worker_id, worker in all_workers.items():
            stats = worker.get_stats()
            
            # 计算负载分数
            load_score = self._calculate_load_score(stats)
            
            # 获取工作器配置
            config = self.worker_manager._worker_configs.get(worker_id)
            priority = config.priority if config else 0
            
            # 更新负载信息
            self._worker_load_info[worker_id] = WorkerLoadInfo(
                worker_id=worker_id,
                worker=worker,
                load_score=load_score,
                priority=priority,
                health_score=stats.health_score,
                queue_size=worker.input_queue.size(),
                processing_rate=stats.processing_rate,
                success_rate=stats.success_rate,
                last_updated=time.time()
            )
    
    def _calculate_load_score(self, stats: WorkerStats) -> float:
        """计算工作器负载分数
        
        Args:
            stats: 工作器统计信息
            
        Returns:
            float: 负载分数，越高表示负载越高
        """
        # 综合考虑队列大小、处理速率和成功率
        queue_factor = stats.queue_size / 100.0  # 队列大小因子
        processing_factor = 1.0 / (1.0 + stats.processing_rate)  # 处理速率因子
        failure_factor = (100.0 - stats.success_rate) / 100.0  # 失败率因子
        
        # 综合负载分数
        load_score = 0.4 * queue_factor + 0.3 * processing_factor + 0.3 * failure_factor
        
        return load_score
    
    def _adaptive_strategy_adjustment(self):
        """自适应策略调整"""
        # 更新策略性能统计
        self._update_strategy_performance()
        
        # 找出性能最好的策略
        best_strategy = max(self._strategy_performance.items(), key=lambda x: x[1])[0]
        
        # 如果当前策略不是最佳策略且性能差异超过阈值，则切换策略
        if (self.strategy != best_strategy and 
            abs(self._strategy_performance[self.strategy] - self._strategy_performance[best_strategy]) > self._strategy_switch_threshold):
            
            print(f"Switching scheduling strategy from {self.strategy.value} to {best_strategy.value}")
            self.strategy = best_strategy
            self._stats.strategy = best_strategy
    
    def _update_strategy_performance(self):
        """更新策略性能统计"""
        # 这里简化处理，实际应用中可以根据更复杂的指标计算
        # 例如：平均处理时间、成功率、吞吐量等
        
        # 获取当前统计信息
        manager_stats = self.worker_manager.get_stats()
        
        # 计算当前策略的性能分数
        current_performance = 0.0
        
        if self.strategy == SchedulingStrategy.ROUND_ROBIN:
            # 轮询策略的性能基于平均成功率
            current_performance = manager_stats.average_success_rate / 100.0
        elif self.strategy == SchedulingStrategy.LEAST_LOADED:
            # 最少负载策略的性能基于负载均衡分数
            current_performance = self._calculate_load_balance_score()
        elif self.strategy == SchedulingStrategy.PRIORITY_BASED:
            # 优先级策略的性能基于高优先级任务的处理效率
            current_performance = manager_stats.average_success_rate / 100.0
        elif self.strategy == SchedulingStrategy.HEALTH_AWARE:
            # 健康感知策略的性能基于平均健康分数
            current_performance = manager_stats.average_health_score
        elif self.strategy == SchedulingStrategy.ADAPTIVE:
            # 自适应策略的性能基于综合指标
            current_performance = (manager_stats.average_success_rate / 100.0 + 
                                  manager_stats.average_health_score + 
                                  self._calculate_load_balance_score()) / 3.0
        
        # 更新策略性能（使用指数移动平均）
        alpha = 0.1  # 平滑因子
        self._strategy_performance[self.strategy] = (
            alpha * current_performance + 
            (1 - alpha) * self._strategy_performance[self.strategy]
        )
    
    def _calculate_load_balance_score(self) -> float:
        """计算负载均衡分数
        
        Returns:
            float: 负载均衡分数，0-1之间，越高表示负载越均衡
        """
        if not self._worker_load_info:
            return 1.0
        
        # 计算所有工作器的平均负载
        total_load = sum(info.load_score for info in self._worker_load_info.values())
        avg_load = total_load / len(self._worker_load_info)
        
        if avg_load == 0:
            return 1.0
        
        # 计算负载方差
        variance = sum((info.load_score - avg_load) ** 2 for info in self._worker_load_info.values()) / len(self._worker_load_info)
        
        # 负载均衡分数（方差越小，分数越高）
        balance_score = 1.0 / (1.0 + variance)
        
        return balance_score
    
    def _update_scheduling_stats(self, success: bool, scheduling_time: float):
        """更新调度统计信息
        
        Args:
            success: 是否成功调度
            scheduling_time: 调度耗时
        """
        self._stats.total_scheduled_messages += 1
        
        if not success:
            self._stats.total_failed_schedules += 1
        
        # 更新平均调度时间
        self._stats.average_scheduling_time = (
            (self._stats.average_scheduling_time * (self._stats.total_scheduled_messages - 1) + scheduling_time) /
            self._stats.total_scheduled_messages
        )
        
        # 更新最后调度时间
        self._stats.last_scheduling_time = time.time()
    
    def _update_stats(self):
        """更新统计信息"""
        # 更新运行时间
        self._stats.uptime = time.time() - self._stats.start_time
        
        # 更新工作器数量
        manager_stats = self.worker_manager.get_stats()
        self._stats.worker_count = manager_stats.total_workers
        self._stats.active_workers = manager_stats.running_workers
        
        # 更新负载均衡分数
        self._stats.load_balance_score = self._calculate_load_balance_score()
        
        # 计算调度速率
        if self._stats.uptime > 0:
            self._stats.scheduling_rate = self._stats.total_scheduled_messages / self._stats.uptime
        
        # 更新状态
        self._stats.state = self._state
    
    def _notify_scheduling_callback(self, worker_id: str, message_id: str, success: bool):
        """通知调度回调
        
        Args:
            worker_id: 工作器ID
            message_id: 消息ID
            success: 是否成功调度
        """
        for callback in self._scheduling_callbacks:
            try:
                callback(worker_id, message_id, success)
            except Exception as e:
                print(f"Error in scheduling callback: {e}")
    
    def add_scheduling_callback(self, callback: Callable[[str, str, bool], None]):
        """添加调度回调
        
        Args:
            callback: 回调函数，参数为(worker_id, message_id, success)
        """
        self._scheduling_callbacks.append(callback)
    
    def remove_scheduling_callback(self, callback: Callable[[str, str, bool], None]):
        """移除调度回调
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._scheduling_callbacks:
            self._scheduling_callbacks.remove(callback)
    
    def get_stats(self) -> SchedulerStats:
        """获取调度器统计信息
        
        Returns:
            SchedulerStats: 调度器统计信息
        """
        # 更新统计信息
        self._update_stats()
        
        return self._stats
    
    def get_state(self) -> SchedulerState:
        """获取调度器状态
        
        Returns:
            SchedulerState: 调度器状态
        """
        return self._state
    
    def set_strategy(self, strategy: SchedulingStrategy):
        """设置调度策略
        
        Args:
            strategy: 调度策略
        """
        self.strategy = strategy
        self._stats.strategy = strategy
        print(f"Scheduling strategy changed to {strategy.value}")
    
    def start(self):
        """启动调度器"""
        self._state = SchedulerState.RUNNING
        self._stats.state = self._state
        self._stats.start_time = time.time()
        
        # 启动调度线程
        self._scheduling_thread.start()
        
        # 启动负载更新线程
        self._load_update_thread.start()
        
        # 初始化工作器负载信息
        self._update_worker_load_info()
    
    def stop(self):
        """停止调度器"""
        self._state = SchedulerState.STOPPING
        self._stats.state = self._state
        
        # 停止线程
        self._stop_event.set()
        
        # 等待线程结束
        self._scheduling_thread.join(timeout=5.0)
        self._load_update_thread.join(timeout=5.0)
        
        self._state = SchedulerState.STOPPED
        self._stats.state = self._state
    
    def pause(self):
        """暂停调度器"""
        self._state = SchedulerState.PAUSED
        self._stats.state = self._state
        self._pause_event.clear()
    
    def resume(self):
        """恢复调度器"""
        self._state = SchedulerState.RUNNING
        self._stats.state = self._state
        self._pause_event.set()
    
    def __str__(self) -> str:
        """返回调度器的字符串表示
        
        Returns:
            str: 调度器字符串表示
        """
        return f"WorkerScheduler(name={self.name}, state={self._state.value}, strategy={self.strategy.value})"
    
    def __repr__(self) -> str:
        """返回调度器的详细字符串表示
        
        Returns:
            str: 调度器详细字符串表示
        """
        return (f"WorkerScheduler(id={self.scheduler_id}, name={self.name}, state={self._state.value}, "
                f"strategy={self.strategy.value}, scheduled_messages={self._stats.total_scheduled_messages}, "
                f"scheduling_rate={self._stats.scheduling_rate:.2f}/s, load_balance_score={self._stats.load_balance_score:.2f})")

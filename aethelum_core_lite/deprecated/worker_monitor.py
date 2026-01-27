import threading
import time
import json
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid
import statistics
from collections import deque

from .worker import AxonWorker, WorkerState, WorkerStats
from .queue import SynapticQueue
from .message import NeuralImpulse
from .worker_manager import WorkerManager
from .worker_scheduler import WorkerScheduler, SchedulerState


class AlertLevel(Enum):
    """告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MonitorState(Enum):
    """监控器状态枚举"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class MetricType(Enum):
    """指标类型枚举"""
    COUNTER = "counter"  # 计数器
    GAUGE = "gauge"  # 仪表盘
    HISTOGRAM = "histogram"  # 直方图
    RATE = "rate"  # 速率


@dataclass
class MetricValue:
    """指标值"""
    name: str
    value: float
    timestamp: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""


@dataclass
class Alert:
    """告警信息"""
    alert_id: str
    level: AlertLevel
    title: str
    message: str
    timestamp: float
    source: str  # 告警来源
    worker_id: Optional[str] = None
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    current_value: Optional[float] = None
    resolved: bool = False
    resolved_timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorStats:
    """监控器统计信息"""
    monitor_id: str
    name: str
    state: MonitorState = MonitorState.INITIALIZING
    start_time: float = field(default_factory=time.time)
    uptime: float = 0.0
    total_metrics_collected: int = 0
    total_alerts_generated: int = 0
    active_alerts: int = 0
    resolved_alerts: int = 0
    metrics_collection_rate: float = 0.0  # 指标收集速率（指标/秒）
    last_collection_time: float = 0.0
    monitored_workers: int = 0
    monitored_queues: int = 0
    health_check_rate: float = 0.0  # 健康检查速率（检查/秒）
    auto_recovery_rate: float = 0.0  # 自动恢复速率（恢复/秒）


@dataclass
class ThresholdRule:
    """阈值规则"""
    rule_id: str
    metric_name: str
    operator: str  # >, <, >=, <=, ==, !=
    threshold: float
    level: AlertLevel
    description: str
    enabled: bool = True
    cooldown_period: float = 60.0  # 冷却期（秒）
    last_triggered: float = 0.0  # 上次触发时间


class WorkerMonitor:
    """工作器监控器，负责实时监控工作器的状态、性能和健康状况
    
    提供指标收集、阈值告警、趋势分析和自动恢复功能。
    支持自定义监控规则和告警处理策略。
    """
    
    def __init__(self, 
                 name: str,
                 worker_manager: WorkerManager,
                 scheduler: Optional[WorkerScheduler] = None,
                 monitor_id: Optional[str] = None,
                 metrics_collection_interval: float = 5.0,
                 health_check_interval: float = 10.0,
                 alert_cooldown_period: float = 60.0,
                 enable_auto_recovery: bool = True,
                 max_metrics_history: int = 1000):
        """初始化工作器监控器
        
        Args:
            name: 监控器名称
            worker_manager: 工作器管理器
            scheduler: 工作器调度器，可选
            monitor_id: 监控器ID，如果不提供则自动生成
            metrics_collection_interval: 指标收集间隔（秒）
            health_check_interval: 健康检查间隔（秒）
            alert_cooldown_period: 告警冷却期（秒）
            enable_auto_recovery: 是否启用自动恢复
            max_metrics_history: 最大指标历史记录数
        """
        self.name = name
        self.worker_manager = worker_manager
        self.scheduler = scheduler
        self.monitor_id = monitor_id or str(uuid.uuid4())
        self.metrics_collection_interval = metrics_collection_interval
        self.health_check_interval = health_check_interval
        self.alert_cooldown_period = alert_cooldown_period
        self.enable_auto_recovery = enable_auto_recovery
        self.max_metrics_history = max_metrics_history
        
        # 监控器状态
        self._state = MonitorState.INITIALIZING
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始状态为运行
        
        # 指标存储
        self._metrics_history: Dict[str, deque] = {}
        self._current_metrics: Dict[str, MetricValue] = {}
        self._metrics_lock = threading.RLock()  # 保护指标数据

        # 告警存储
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._alerts_lock = threading.RLock()   # 保护告警数据
        
        # 阈值规则
        self._threshold_rules: Dict[str, ThresholdRule] = {}
        
        # 统计信息
        self._stats = MonitorStats(
            monitor_id=self.monitor_id,
            name=self.name,
            state=self._state
        )
        
        # 指标收集线程
        self._metrics_collection_thread = threading.Thread(
            target=self._metrics_collection_loop,
            daemon=True
        )
        
        # 健康检查线程
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True
        )
        
        # 告警处理线程
        self._alert_processing_thread = threading.Thread(
            target=self._alert_processing_loop,
            daemon=True
        )
        
        # 告警回调
        self._alert_callbacks: List[Callable[[Alert], None]] = []
        
        # 自动恢复回调
        self._recovery_callbacks: List[Callable[[str, str], bool]] = []
        
        # 初始化默认阈值规则
        self._init_default_threshold_rules()
    
    def _init_default_threshold_rules(self):
        """初始化默认阈值规则"""
        # 工作器CPU使用率告警
        self.add_threshold_rule(ThresholdRule(
            rule_id="worker_cpu_high",
            metric_name="worker_cpu_usage",
            operator=">",
            threshold=80.0,
            level=AlertLevel.WARNING,
            description="工作器CPU使用率过高"
        ))
        
        # 工作器内存使用率告警
        self.add_threshold_rule(ThresholdRule(
            rule_id="worker_memory_high",
            metric_name="worker_memory_usage",
            operator=">",
            threshold=80.0,
            level=AlertLevel.WARNING,
            description="工作器内存使用率过高"
        ))
        
        # 工作器队列大小告警
        self.add_threshold_rule(ThresholdRule(
            rule_id="worker_queue_size_high",
            metric_name="worker_queue_size",
            operator=">",
            threshold=100.0,
            level=AlertLevel.WARNING,
            description="工作器队列积压过多"
        ))
        
        # 工作器成功率告警
        self.add_threshold_rule(ThresholdRule(
            rule_id="worker_success_rate_low",
            metric_name="worker_success_rate",
            operator="<",
            threshold=90.0,
            level=AlertLevel.ERROR,
            description="工作器成功率过低"
        ))
        
        # 工作器健康分数告警
        self.add_threshold_rule(ThresholdRule(
            rule_id="worker_health_low",
            metric_name="worker_health_score",
            operator="<",
            threshold=0.7,
            level=AlertLevel.ERROR,
            description="工作器健康分数过低"
        ))
        
        # 工作器处理速率告警
        self.add_threshold_rule(ThresholdRule(
            rule_id="worker_processing_rate_low",
            metric_name="worker_processing_rate",
            operator="<",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="工作器处理速率过低"
        ))
    
    def add_threshold_rule(self, rule: ThresholdRule):
        """添加阈值规则
        
        Args:
            rule: 阈值规则
        """
        self._threshold_rules[rule.rule_id] = rule
    
    def remove_threshold_rule(self, rule_id: str):
        """移除阈值规则
        
        Args:
            rule_id: 规则ID
        """
        if rule_id in self._threshold_rules:
            del self._threshold_rules[rule_id]
    
    def get_threshold_rules(self) -> Dict[str, ThresholdRule]:
        """获取所有阈值规则
        
        Returns:
            Dict[str, ThresholdRule]: 阈值规则字典
        """
        return self._threshold_rules.copy()
    
    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """添加告警回调
        
        Args:
            callback: 告警回调函数
        """
        self._alert_callbacks.append(callback)
    
    def remove_alert_callback(self, callback: Callable[[Alert], None]):
        """移除告警回调
        
        Args:
            callback: 告警回调函数
        """
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)
    
    def add_recovery_callback(self, callback: Callable[[str, str], bool]):
        """添加自动恢复回调
        
        Args:
            callback: 恢复回调函数，参数为(worker_id, alert_id)，返回是否成功恢复
        """
        self._recovery_callbacks.append(callback)
    
    def remove_recovery_callback(self, callback: Callable[[str, str], bool]):
        """移除自动恢复回调
        
        Args:
            callback: 恢复回调函数
        """
        if callback in self._recovery_callbacks:
            self._recovery_callbacks.remove(callback)
    
    def _metrics_collection_loop(self):
        """指标收集循环（带异常处理）"""
        while not self._stop_event.is_set():
            try:
                time.sleep(self.metrics_collection_interval)

                # 检查是否暂停
                if not self._pause_event.is_set():
                    continue

                # 收集工作器指标（添加异常保护）
                try:
                    self._collect_worker_metrics()
                except Exception as e:
                    self.logger.error(
                        f"[Monitor] Error collecting worker metrics: {repr(e)}",
                        exc_info=True
                    )
                    # 继续运行，不退出循环

                # 收集调度器指标（添加异常保护）
                try:
                    if self.scheduler:
                        self._collect_scheduler_metrics()
                except Exception as e:
                    self.logger.error(
                        f"[Monitor] Error collecting scheduler metrics: {repr(e)}",
                        exc_info=True
                    )
                    # 继续运行，不退出循环

                # 更新统计信息（添加异常保护）
                try:
                    self._update_stats()
                except Exception as e:
                    self.logger.error(
                        f"[Monitor] Error updating stats: {repr(e)}",
                        exc_info=True
                    )

            except Exception as e:
                # 捕获循环级别的异常
                self.logger.error(
                    f"[Monitor] Unexpected error in metrics collection loop: {repr(e)}",
                    exc_info=True
                )
                # 继续运行，不退出

        self.logger.info(f"[Monitor] Metrics collection loop exited")
    
    def _collect_worker_metrics(self):
        """收集工作器指标"""
        all_workers = self.worker_manager.get_all_workers()
        
        for worker_id, worker in all_workers.items():
            stats = worker.get_stats()
            
            # 收集各种指标
            self._record_metric(
                name="worker_queue_size",
                value=stats.queue_size,
                metric_type=MetricType.GAUGE,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="messages",
                description="工作器队列大小"
            )
            
            self._record_metric(
                name="worker_processing_rate",
                value=stats.processing_rate,
                metric_type=MetricType.RATE,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="messages/sec",
                description="工作器处理速率"
            )
            
            self._record_metric(
                name="worker_success_rate",
                value=stats.success_rate,
                metric_type=MetricType.GAUGE,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="percent",
                description="工作器成功率"
            )
            
            self._record_metric(
                name="worker_health_score",
                value=stats.health_score,
                metric_type=MetricType.GAUGE,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="score",
                description="工作器健康分数"
            )
            
            self._record_metric(
                name="worker_uptime",
                value=stats.uptime,
                metric_type=MetricType.GAUGE,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="seconds",
                description="工作器运行时间"
            )
            
            self._record_metric(
                name="worker_total_processed",
                value=stats.total_processed,
                metric_type=MetricType.COUNTER,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="messages",
                description="工作器处理的消息总数"
            )
            
            self._record_metric(
                name="worker_total_failed",
                value=stats.total_failed,
                metric_type=MetricType.COUNTER,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="messages",
                description="工作器处理失败的消息总数"
            )
            
            # 模拟CPU和内存使用率（实际应用中可以从系统获取）
            cpu_usage = min(100.0, stats.processing_rate * 10)  # 简单模拟
            memory_usage = min(100.0, stats.queue_size / 2)  # 简单模拟
            
            self._record_metric(
                name="worker_cpu_usage",
                value=cpu_usage,
                metric_type=MetricType.GAUGE,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="percent",
                description="工作器CPU使用率"
            )
            
            self._record_metric(
                name="worker_memory_usage",
                value=memory_usage,
                metric_type=MetricType.GAUGE,
                labels={"worker_id": worker_id, "worker_name": worker.name},
                unit="percent",
                description="工作器内存使用率"
            )
    
    def _collect_scheduler_metrics(self):
        """收集调度器指标"""
        if not self.scheduler:
            return
        
        stats = self.scheduler.get_stats()
        
        self._record_metric(
            name="scheduler_scheduling_rate",
            value=stats.scheduling_rate,
            metric_type=MetricType.RATE,
            labels={"scheduler_id": self.scheduler.scheduler_id, "scheduler_name": self.scheduler.name},
            unit="messages/sec",
            description="调度器调度速率"
        )
        
        self._record_metric(
            name="scheduler_load_balance_score",
            value=stats.load_balance_score,
            metric_type=MetricType.GAUGE,
            labels={"scheduler_id": self.scheduler.scheduler_id, "scheduler_name": self.scheduler.name},
            unit="score",
            description="调度器负载均衡分数"
        )
        
        self._record_metric(
            name="scheduler_active_workers",
            value=stats.active_workers,
            metric_type=MetricType.GAUGE,
            labels={"scheduler_id": self.scheduler.scheduler_id, "scheduler_name": self.scheduler.name},
            unit="workers",
            description="调度器活跃工作器数量"
        )
    
    def _record_metric(self,
                      name: str,
                      value: float,
                      metric_type: MetricType,
                      labels: Dict[str, str] = None,
                      unit: str = "",
                      description: str = ""):
        """记录指标

        Args:
            name: 指标名称
            value: 指标值
            metric_type: 指标类型
            labels: 标签
            unit: 单位
            description: 描述
        """
        timestamp = time.time()

        # 创建指标值
        metric = MetricValue(
            name=name,
            value=value,
            timestamp=timestamp,
            metric_type=metric_type,
            labels=labels or {},
            unit=unit,
            description=description
        )

        # 更新当前指标和历史记录（线程安全）
        with self._metrics_lock:
            self._current_metrics[name] = metric

            # 添加到历史记录
            if name not in self._metrics_history:
                self._metrics_history[name] = deque(maxlen=self.max_metrics_history)

            self._metrics_history[name].append(metric)

        # 更新统计信息
        self._stats.total_metrics_collected += 1
        self._stats.last_collection_time = timestamp
    
    def _health_check_loop(self):
        """健康检查循环（带异常处理）"""
        while not self._stop_event.is_set():
            try:
                time.sleep(self.health_check_interval)

                # 检查是否暂停
                if not self._pause_event.is_set():
                    continue

                # 执行健康检查（添加异常保护）
                try:
                    self._perform_health_checks()
                except Exception as e:
                    self.logger.error(
                        f"[Monitor] Error performing health checks: {repr(e)}",
                        exc_info=True
                    )
                    # 继续运行，不退出循环

            except Exception as e:
                # 捕获循环级别的异常
                self.logger.error(
                    f"[Monitor] Unexpected error in health check loop: {repr(e)}",
                    exc_info=True
                )
                # 继续运行，不退出

        self.logger.info(f"[Monitor] Health check loop exited")
    
    def _perform_health_checks(self):
        """执行健康检查"""
        all_workers = self.worker_manager.get_all_workers()
        
        for worker_id, worker in all_workers.items():
            # 检查工作器状态
            state = worker.get_state()
            
            if state == WorkerState.ERROR:
                self._create_alert(
                    level=AlertLevel.ERROR,
                    title="工作器错误状态",
                    message=f"工作器 {worker.name} 处于错误状态",
                    source="health_check",
                    worker_id=worker_id,
                    metadata={"state": state.value}
                )
            
            # 检查工作器健康分数
            stats = worker.get_stats()
            
            if stats.health_score < 0.5:
                self._create_alert(
                    level=AlertLevel.WARNING,
                    title="工作器健康分数低",
                    message=f"工作器 {worker.name} 健康分数过低: {stats.health_score:.2f}",
                    source="health_check",
                    worker_id=worker_id,
                    metric_name="worker_health_score",
                    current_value=stats.health_score,
                    threshold=0.5
                )
            
            # 检查工作器队列积压
            if stats.queue_size > 200:
                self._create_alert(
                    level=AlertLevel.WARNING,
                    title="工作器队列积压",
                    message=f"工作器 {worker.name} 队列积压过多: {stats.queue_size}",
                    source="health_check",
                    worker_id=worker_id,
                    metric_name="worker_queue_size",
                    current_value=stats.queue_size,
                    threshold=200
                )
    
    def _alert_processing_loop(self):
        """告警处理循环（带异常处理）"""
        while not self._stop_event.is_set():
            try:
                time.sleep(1.0)  # 每秒检查一次

                # 检查是否暂停
                if not self._pause_event.is_set():
                    continue

                # 检查阈值规则（添加异常保护）
                try:
                    self._check_threshold_rules()
                except Exception as e:
                    self.logger.error(
                        f"[Monitor] Error checking threshold rules: {repr(e)}",
                        exc_info=True
                    )
                    # 继续运行，不退出循环

                # 处理自动恢复（添加异常保护）
                try:
                    if self.enable_auto_recovery:
                        self._process_auto_recovery()
                except Exception as e:
                    self.logger.error(
                        f"[Monitor] Error processing auto recovery: {repr(e)}",
                        exc_info=True
                    )
                    # 继续运行，不退出循环

            except Exception as e:
                # 捕获循环级别的异常
                self.logger.error(
                    f"[Monitor] Unexpected error in alert processing loop: {repr(e)}",
                    exc_info=True
                )
                # 继续运行，不退出

        self.logger.info(f"[Monitor] Alert processing loop exited")
    
    def _check_threshold_rules(self):
        """检查阈值规则"""
        current_time = time.time()

        for rule_id, rule in self._threshold_rules.items():
            if not rule.enabled:
                continue

            # 检查冷却期
            if current_time - rule.last_triggered < rule.cooldown_period:
                continue

            # 线程安全地获取指标值
            with self._metrics_lock:
                if rule.metric_name not in self._current_metrics:
                    continue

                metric = self._current_metrics[rule.metric_name]

                # 检查阈值
                triggered = False

                if rule.operator == ">" and metric.value > rule.threshold:
                    triggered = True
                elif rule.operator == ">=" and metric.value >= rule.threshold:
                    triggered = True
                elif rule.operator == "<" and metric.value < rule.threshold:
                    triggered = True
                elif rule.operator == "<=" and metric.value <= rule.threshold:
                    triggered = True
                elif rule.operator == "==" and metric.value == rule.threshold:
                    triggered = True
                elif rule.operator == "!=" and metric.value != rule.threshold:
                    triggered = True

                if triggered:
                    # 创建告警
                    worker_id = metric.labels.get("worker_id")

                    # 复制需要的值，避免在锁外使用可能被修改的对象
                    metric_value = metric.value
                    metric_labels = metric.labels.copy()

            # 在锁外创建告警，避免死锁
            if triggered:
                self._create_alert(
                    level=rule.level,
                    title=f"阈值告警: {rule.description}",
                    message=f"指标 {rule.metric_name} 值 {metric_value} {rule.operator} 阈值 {rule.threshold}",
                    source="threshold_rule",
                    worker_id=worker_id,
                    metric_name=rule.metric_name,
                    current_value=metric_value,
                    threshold=rule.threshold,
                    metadata={"rule_id": rule_id, "operator": rule.operator}
                )

                # 更新规则触发时间
                rule.last_triggered = current_time
    
    def _create_alert(self,
                     level: AlertLevel,
                     title: str,
                     message: str,
                     source: str,
                     worker_id: Optional[str] = None,
                     metric_name: Optional[str] = None,
                     current_value: Optional[float] = None,
                     threshold: Optional[float] = None,
                     metadata: Dict[str, Any] = None):
        """创建告警

        Args:
            level: 告警级别
            title: 告警标题
            message: 告警消息
            source: 告警来源
            worker_id: 工作器ID
            metric_name: 指标名称
            current_value: 当前值
            threshold: 阈值
            metadata: 元数据
        """
        alert_id = str(uuid.uuid4())
        timestamp = time.time()

        alert = Alert(
            alert_id=alert_id,
            level=level,
            title=title,
            message=message,
            timestamp=timestamp,
            source=source,
            worker_id=worker_id,
            metric_name=metric_name,
            current_value=current_value,
            threshold=threshold,
            metadata=metadata or {}
        )

        # 添加到活跃告警和历史记录（线程安全）
        with self._alerts_lock:
            self._active_alerts[alert_id] = alert

            # 添加到历史记录
            self._alert_history.append(alert)

            # 更新统计信息
            self._stats.total_alerts_generated += 1
            self._stats.active_alerts = len(self._active_alerts)

        # 通知告警回调
        self._notify_alert_callbacks(alert)
    
    def _notify_alert_callbacks(self, alert: Alert):
        """通知告警回调
        
        Args:
            alert: 告警信息
        """
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                print(f"Error in alert callback: {e}")
    
    def _process_auto_recovery(self):
        """处理自动恢复"""
        # 获取活跃告警的快照，避免在锁定状态下调用恢复回调
        with self._alerts_lock:
            active_alerts = list(self._active_alerts.items())

        for alert_id, alert in active_alerts:
            # 只处理错误和严重级别的告警
            if alert.level not in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
                continue

            # 只处理工作器相关的告警
            if not alert.worker_id:
                continue

            # 尝试自动恢复
            recovered = False

            for callback in self._recovery_callbacks:
                try:
                    if callback(alert.worker_id, alert_id):
                        recovered = True
                        break
                except Exception as e:
                    print(f"Error in recovery callback: {e}")

            if recovered:
                # 标记告警为已解决并从活跃告警中移除（线程安全）
                with self._alerts_lock:
                    if alert_id in self._active_alerts:
                        alert_to_resolve = self._active_alerts[alert_id]
                        alert_to_resolve.resolved = True
                        alert_to_resolve.resolved_timestamp = time.time()

                        # 从活跃告警中移除
                        del self._active_alerts[alert_id]

                        # 更新统计信息
                        self._stats.active_alerts = len(self._active_alerts)
                        self._stats.resolved_alerts += 1

                print(f"Auto-recovered worker {alert.worker_id} for alert {alert_id}")
    
    def _update_stats(self):
        """更新统计信息"""
        # 更新运行时间
        self._stats.uptime = time.time() - self._stats.start_time
        
        # 更新监控的工作器和队列数量
        self._stats.monitored_workers = len(self.worker_manager.get_all_workers())
        
        # 计算指标收集速率
        if self._stats.uptime > 0:
            self._stats.metrics_collection_rate = self._stats.total_metrics_collected / self._stats.uptime
        
        # 计算健康检查速率
        if self._stats.uptime > 0:
            self._stats.health_check_rate = self._stats.uptime / self.health_check_interval
        
        # 计算自动恢复速率
        if self._stats.uptime > 0:
            self._stats.auto_recovery_rate = self._stats.resolved_alerts / self._stats.uptime
        
        # 更新状态
        self._stats.state = self._state
    
    def get_stats(self) -> MonitorStats:
        """获取监控器统计信息

        Returns:
            MonitorStats: 监控器统计信息
        """
        # 更新统计信息
        self._update_stats()

        # 返回副本而非引用，防止外部代码修改内部状态（线程安全）
        return MonitorStats(
            monitor_id=self._stats.monitor_id,
            name=self._stats.name,
            state=self._stats.state,
            start_time=self._stats.start_time,
            uptime=self._stats.uptime,
            total_metrics_collected=self._stats.total_metrics_collected,
            total_alerts_generated=self._stats.total_alerts_generated,
            active_alerts=self._stats.active_alerts,
            resolved_alerts=self._stats.resolved_alerts,
            metrics_collection_rate=self._stats.metrics_collection_rate,
            last_collection_time=self._stats.last_collection_time,
            monitored_workers=self._stats.monitored_workers,
            monitored_queues=self._stats.monitored_queues,
            health_check_rate=self._stats.health_check_rate,
            auto_recovery_rate=self._stats.auto_recovery_rate
        )
    
    def get_state(self) -> MonitorState:
        """获取监控器状态
        
        Returns:
            MonitorState: 监控器状态
        """
        return self._state
    
    def get_active_alerts(self) -> Dict[str, Alert]:
        """获取活跃告警

        Returns:
            Dict[str, Alert]: 活跃告警字典
        """
        with self._alerts_lock:
            return self._active_alerts.copy()
    
    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """获取告警历史

        Args:
            limit: 返回的最大告警数量

        Returns:
            List[Alert]: 告警历史列表
        """
        with self._alerts_lock:
            return self._alert_history[-limit:]
    
    def get_current_metrics(self) -> Dict[str, MetricValue]:
        """获取当前指标

        Returns:
            Dict[str, MetricValue]: 当前指标字典
        """
        with self._metrics_lock:
            return self._current_metrics.copy()
    
    def get_metric_history(self, metric_name: str, limit: int = 100) -> List[MetricValue]:
        """获取指标历史

        Args:
            metric_name: 指标名称
            limit: 返回的最大指标数量

        Returns:
            List[MetricValue]: 指标历史列表
        """
        with self._metrics_lock:
            if metric_name not in self._metrics_history:
                return []

            history = list(self._metrics_history[metric_name])
            return history[-limit:]
    
    def resolve_alert(self, alert_id: str):
        """解决告警

        Args:
            alert_id: 告警ID
        """
        with self._alerts_lock:
            if alert_id in self._active_alerts:
                alert = self._active_alerts[alert_id]
                alert.resolved = True
                alert.resolved_timestamp = time.time()

                # 从活跃告警中移除
                del self._active_alerts[alert_id]

                # 更新统计信息
                self._stats.active_alerts = len(self._active_alerts)
                self._stats.resolved_alerts += 1
    
    def start(self):
        """启动监控器"""
        self._state = MonitorState.RUNNING
        self._stats.state = self._state
        self._stats.start_time = time.time()
        
        # 启动指标收集线程
        self._metrics_collection_thread.start()
        
        # 启动健康检查线程
        self._health_check_thread.start()
        
        # 启动告警处理线程
        self._alert_processing_thread.start()
    
    def stop(self):
        """停止监控器"""
        self._state = MonitorState.STOPPING
        self._stats.state = self._state
        
        # 停止线程
        self._stop_event.set()
        
        # 等待线程结束
        self._metrics_collection_thread.join(timeout=5.0)
        self._health_check_thread.join(timeout=5.0)
        self._alert_processing_thread.join(timeout=5.0)
        
        self._state = MonitorState.STOPPED
        self._stats.state = self._state
    
    def pause(self):
        """暂停监控器"""
        self._state = MonitorState.PAUSED
        self._stats.state = self._state
        self._pause_event.clear()
    
    def resume(self):
        """恢复监控器"""
        self._state = MonitorState.RUNNING
        self._stats.state = self._state
        self._pause_event.set()
    
    def export_metrics(self, file_path: str):
        """导出指标到文件

        Args:
            file_path: 文件路径
        """
        try:
            # 线程安全地获取指标数据
            with self._metrics_lock:
                current_metrics_copy = {
                    name: {
                        "value": metric.value,
                        "timestamp": metric.timestamp,
                        "metric_type": metric.metric_type.value,
                        "labels": metric.labels,
                        "unit": metric.unit,
                        "description": metric.description
                    }
                    for name, metric in self._current_metrics.items()
                }

            with open(file_path, 'w') as f:
                json.dump({
                    "current_metrics": current_metrics_copy,
                    "stats": {
                        "monitor_id": self._stats.monitor_id,
                        "name": self._stats.name,
                        "state": self._stats.state.value,
                        "uptime": self._stats.uptime,
                        "total_metrics_collected": self._stats.total_metrics_collected,
                        "total_alerts_generated": self._stats.total_alerts_generated,
                        "active_alerts": self._stats.active_alerts,
                        "resolved_alerts": self._stats.resolved_alerts,
                        "metrics_collection_rate": self._stats.metrics_collection_rate,
                        "monitored_workers": self._stats.monitored_workers
                    }
                }, f, indent=2)

            print(f"Metrics exported to {file_path}")
        except Exception as e:
            print(f"Error exporting metrics: {e}")
    
    def __str__(self) -> str:
        """返回监控器的字符串表示
        
        Returns:
            str: 监控器字符串表示
        """
        return f"WorkerMonitor(name={self.name}, state={self._state.value}, workers={self._stats.monitored_workers})"
    
    def __repr__(self) -> str:
        """返回监控器的详细字符串表示
        
        Returns:
            str: 监控器详细字符串表示
        """
        return (f"WorkerMonitor(id={self.monitor_id}, name={self.name}, state={self._state.value}, "
                f"monitored_workers={self._stats.monitored_workers}, active_alerts={self._stats.active_alerts}, "
                f"metrics_collected={self._stats.total_metrics_collected}, uptime={self._stats.uptime:.2f}s)")

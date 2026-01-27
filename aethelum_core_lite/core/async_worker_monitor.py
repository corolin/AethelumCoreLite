"""
异步工作器监控器实现

提供异步版本的Worker监控功能，包括指标收集、健康检查、告警和自动恢复。
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class AsyncAlertLevel(Enum):
    """异步告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AsyncMonitorState(Enum):
    """异步监控器状态枚举"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class MetricType(Enum):
    """指标类型枚举（与同步版本对齐）"""
    COUNTER = "counter"  # 计数器（单调递增）
    GAUGE = "gauge"  # 仪表盘（可增可减）
    HISTOGRAM = "histogram"  # 直方图（分布统计）
    RATE = "rate"  # 速率（每秒变化）


@dataclass
class MetricValue:
    """指标值（与同步版本对齐）"""
    name: str
    value: float
    timestamp: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""


@dataclass
class AsyncAlert:
    """异步告警信息（增强版，与同步版本对齐）"""
    alert_id: str
    level: AsyncAlertLevel
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
class AsyncMonitorStats:
    """异步监控器统计信息（增强版，与同步版本对齐）"""
    monitor_id: str
    name: str = ""
    state: AsyncMonitorState = AsyncMonitorState.INITIALIZING
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
    level: AsyncAlertLevel
    description: str
    enabled: bool = True
    cooldown_period: float = 60.0  # 冷却期（秒）
    last_triggered: float = 0.0  # 上次触发时间


class AsyncWorkerMonitor:
    """
    异步工作器监控器

    负责实时监控工作器的状态、性能和健康状况。
    提供指标收集、阈值告警、趋势分析和自动恢复功能。
    """

    def __init__(self,
                 name: str,
                 router: 'AsyncNeuralSomaRouter',
                 monitor_id: Optional[str] = None,
                 metrics_collection_interval: float = 5.0,
                 health_check_interval: float = 10.0,
                 alert_cooldown_period: float = 60.0,
                 enable_auto_recovery: bool = True,
                 max_metrics_history: int = 1000):
        """
        初始化异步工作器监控器

        Args:
            name: 监控器名称
            router: 异步路由器引用
            monitor_id: 监控器ID
            metrics_collection_interval: 指标收集间隔（秒）
            health_check_interval: 健康检查间隔（秒）
            alert_cooldown_period: 告警冷却期（秒）
            enable_auto_recovery: 是否启用自动恢复
            max_metrics_history: 最大指标历史记录数
        """
        self.name = name
        self.router = router
        self.monitor_id = monitor_id or str(uuid.uuid4())
        self.metrics_collection_interval = metrics_collection_interval
        self.health_check_interval = health_check_interval
        self.alert_cooldown_period = alert_cooldown_period
        self.enable_auto_recovery = enable_auto_recovery
        self.max_metrics_history = max_metrics_history

        # 状态管理
        self._state = AsyncMonitorState.INITIALIZING
        self._stop_event = asyncio.Event()

        # 并发保护
        self._state_lock = asyncio.Lock()
        self._metrics_lock = asyncio.Lock()
        self._alerts_lock = asyncio.Lock()

        # 存储和指标
        self._metrics_history: Dict[str, deque] = {}
        self._current_metrics: Dict[str, MetricValue] = {}  # 当前指标值（与同步版本对齐）
        self._alerts: List[AsyncAlert] = []
        self._alert_history: List[AsyncAlert] = []  # 历史告警记录（包括已解决的）
        self._threshold_rules = self._get_default_threshold_rules()

        # 回调系统（与同步版本对齐）
        self._alert_callbacks: List[Callable[[AsyncAlert], None]] = []
        self._recovery_callbacks: List[Callable[[AsyncAxonWorker], None]] = []

        # 统计信息
        self._stats = AsyncMonitorStats(
            monitor_id=self.monitor_id,
            name=name
        )

        # 后台任务
        self._collection_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._alert_processing_task: Optional[asyncio.Task] = None

        logger.info(f"[Monitor] {self.name} 初始化完成")

    def _get_default_threshold_rules(self) -> List[ThresholdRule]:
        """获取默认阈值规则"""
        return [
            ThresholdRule(
                rule_id="cpu_high",
                metric_name="cpu_percent",
                operator=">",
                threshold=80.0,
                level=AsyncAlertLevel.WARNING,
                description="CPU使用率过高"
            ),
            ThresholdRule(
                rule_id="memory_high",
                metric_name="memory_percent",
                operator=">",
                threshold=85.0,
                level=AsyncAlertLevel.WARNING,
                description="内存使用率过高"
            ),
            ThresholdRule(
                rule_id="queue_size_large",
                metric_name="queue_size",
                operator=">",
                threshold=1000,
                level=AsyncAlertLevel.INFO,
                description="队列积压严重"
            ),
            ThresholdRule(
                rule_id="success_rate_low",
                metric_name="success_rate",
                operator="<",
                threshold=90.0,
                level=AsyncAlertLevel.ERROR,
                description="成功率过低"
            ),
            ThresholdRule(
                rule_id="health_score_low",
                metric_name="health_score",
                operator="<",
                threshold=50.0,
                level=AsyncAlertLevel.ERROR,
                description="健康分数过低"
            ),
            ThresholdRule(
                rule_id="processing_rate_low",
                metric_name="processing_rate",
                operator="<",
                threshold=1.0,
                level=AsyncAlertLevel.WARNING,
                description="处理速率过低"
            ),
        ]

    async def start(self):
        """启动监控器"""
        async with self._state_lock:
            if self._state != AsyncMonitorState.INITIALIZING:
                logger.warning(f"[Monitor] {self.name} already started or not in initializing state")
                return

            self._state = AsyncMonitorState.RUNNING

        # 启动指标收集任务
        self._collection_task = asyncio.create_task(self._metrics_collection_loop())

        # 启动健康检查任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # 启动告警处理任务
        self._alert_processing_task = asyncio.create_task(self._alert_processing_loop())

        logger.info(f"[Monitor] {self.name} 已启动")

    async def stop(self):
        """停止监控器"""
        async with self._state_lock:
            if self._state == AsyncMonitorState.STOPPED:
                logger.warning(f"[Monitor] {self.name} already stopped")
                return
            self._state = AsyncMonitorState.STOPPING

        self._stop_event.set()

        # 取消后台任务
        tasks = []
        if self._collection_task:
            self._collection_task.cancel()
            tasks.append(self._collection_task)
        if self._health_check_task:
            self._health_check_task.cancel()
            tasks.append(self._health_check_task)
        if self._alert_processing_task:
            self._alert_processing_task.cancel()
            tasks.append(self._alert_processing_task)

        # 等待任务结束
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        async with self._state_lock:
            self._state = AsyncMonitorState.STOPPED

        logger.info(f"[Monitor] {self.name} 已停止")

    async def _metrics_collection_loop(self):
        """指标收集循环"""
        while not self._stop_event.is_set():
            try:
                # 收集所有Worker的指标
                for worker_id, worker in self.router._workers.items():
                    stats = await worker.get_stats()
                    await self._store_metrics(worker_id, stats)

                # 收集所有Queue的指标
                for queue_id, queue in self.router._queues.items():
                    metrics = await queue.get_metrics()
                    await self._store_metrics(queue_id, metrics)

                await asyncio.sleep(self.metrics_collection_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Monitor] {self.name} 指标收集出错: {e}")

    async def _health_check_loop(self):
        """健康检查循环"""
        while not self._stop_event.is_set():
            try:
                for worker_id, worker in self.router._workers.items():
                    health_score = await self._calculate_health_score(worker)

                    # 健康分数过低，触发告警
                    if health_score < 50:
                        await self._create_alert(
                            level=AsyncAlertLevel.ERROR,
                            title=f"Worker {worker_id} 健康状况不佳",
                            message=f"健康分数: {health_score:.1f}",
                            worker_id=worker_id
                        )

                    # 自动恢复
                    if self.enable_auto_recovery and health_score < 30:
                        await self._attempt_recovery(worker)

                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Monitor] {self.name} 健康检查出错: {e}")

    async def _alert_processing_loop(self):
        """告警处理循环"""
        while not self._stop_event.is_set():
            try:
                # 检查阈值规则
                await self._check_threshold_rules()

                await asyncio.sleep(self.metrics_collection_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Monitor] {self.name} 告警处理出错: {e}")

    async def _store_metrics(self, component_id: str, metrics: Any):
        """存储指标到历史记录"""
        async with self._metrics_lock:
            if component_id not in self._metrics_history:
                self._metrics_history[component_id] = deque(maxlen=self.max_metrics_history)

            # 提取关键指标
            if hasattr(metrics, 'metrics'):
                metric_data = {
                    'timestamp': time.time(),
                    'data': metrics.metrics
                }
            else:
                metric_data = {
                    'timestamp': time.time(),
                    'data': metrics
                }

            self._metrics_history[component_id].append(metric_data)

    async def _calculate_health_score(self, worker: 'AsyncAxonWorker') -> float:
        """
        计算Worker健康分数

        Args:
            worker: 异步Worker实例

        Returns:
            float: 健康分数（0-100）
        """
        stats = await worker.get_stats()

        # 基于成功率和连续失败次数计算
        score = 100.0

        if stats.processed_messages > 0:
            score *= (stats.success_rate / 100.0)

        # 连续失败惩罚
        if hasattr(stats, 'consecutive_failures'):
            score -= (stats.consecutive_failures * 10)

        return max(0, min(100, score))

    async def _attempt_recovery(self, worker: 'AsyncAxonWorker'):
        """
        尝试恢复Worker

        Args:
            worker: 异步Worker实例
        """
        logger.warning(f"[Monitor] 尝试恢复Worker {worker.worker_id}")

        try:
            # 重启Worker
            await worker.stop()
            await asyncio.sleep(1)
            await worker.start()

            logger.info(f"[Monitor] Worker {worker.worker_id} 已恢复")

            # 创建恢复告警
            await self._create_alert(
                level=AsyncAlertLevel.INFO,
                title=f"Worker {worker.worker_id} 已恢复",
                message=f"Worker已成功重启",
                worker_id=worker.worker_id
            )

        except Exception as e:
            logger.error(f"[Monitor] Worker {worker.worker_id} 恢复失败: {e}")
            await self._create_alert(
                level=AsyncAlertLevel.CRITICAL,
                title=f"Worker {worker.worker_id} 恢复失败",
                message=f"恢复失败: {str(e)}",
                worker_id=worker.worker_id
            )

    async def _check_threshold_rules(self):
        """检查阈值规则并生成告警"""
        current_time = time.time()

        for rule in self._threshold_rules:
            if not rule.enabled:
                continue

            # 检查冷却期
            if current_time - rule.last_triggered < rule.cooldown_period:
                continue

            # 检查所有组件的指标
            for component_id, metric_history in self._metrics_history.items():
                if not metric_history:
                    continue

                # 获取最新指标
                latest_metric = metric_history[-1]
                metric_value = latest_metric['data'].get(rule.metric_name)

                if metric_value is None:
                    continue

                # 检查阈值
                triggered = False
                if rule.operator == ">":
                    triggered = metric_value > rule.threshold
                elif rule.operator == "<":
                    triggered = metric_value < rule.threshold
                elif rule.operator == ">=":
                    triggered = metric_value >= rule.threshold
                elif rule.operator == "<=":
                    triggered = metric_value <= rule.threshold
                elif rule.operator == "==":
                    triggered = metric_value == rule.threshold
                elif rule.operator == "!=":
                    triggered = metric_value != rule.threshold

                if triggered:
                    await self._create_alert(
                        level=rule.level,
                        title=f"{rule.description} - {component_id}",
                        message=f"{rule.metric_name}={metric_value:.2f}, 阈值={rule.threshold}",
                        worker_id=component_id
                    )

                    # 更新触发时间
                    rule.last_triggered = current_time

    async def _create_alert(
        self,
        level: AsyncAlertLevel,
        title: str,
        message: str,
        worker_id: Optional[str] = None
    ):
        """
        创建告警

        Args:
            level: 告警级别
            title: 告警标题
            message: 告警消息
            worker_id: 关联的Worker ID
        """
        async with self._alerts_lock:
            alert = AsyncAlert(
                alert_id=str(uuid.uuid4()),
                level=level,
                title=title,
                message=message,
                timestamp=time.time(),
                worker_id=worker_id
            )
            self._alerts.append(alert)

            logger.warning(
                f"[Monitor] 告警: [{level.value.upper()}] {title} - {message}"
            )

    async def get_stats(self) -> AsyncMonitorStats:
        """
        获取监控器统计信息

        Returns:
            AsyncMonitorStats: 统计信息
        """
        async with self._metrics_lock:
            async with self._alerts_lock:
                total_metrics = sum(
                    len(history) for history in self._metrics_history.values()
                )

                return AsyncMonitorStats(
                    monitor_id=self.monitor_id,
                    total_metrics_collected=total_metrics,
                    total_alerts_generated=len(self._alerts),
                    active_alerts=sum(1 for a in self._alerts if not a.resolved)
                )

    def add_threshold_rule(self, rule: ThresholdRule):
        """
        添加阈值规则

        Args:
            rule: 阈值规则
        """
        self._threshold_rules.append(rule)
        logger.info(f"[Monitor] 添加阈值规则: {rule.rule_id}")

    def remove_threshold_rule(self, rule_id: str):
        """
        移除阈值规则

        Args:
            rule_id: 规则ID
        """
        self._threshold_rules = [
            rule for rule in self._threshold_rules if rule.rule_id != rule_id
        ]
        logger.info(f"[Monitor] 移除阈值规则: {rule_id}")

    async def get_active_alerts(self) -> List[AsyncAlert]:
        """
        获取活跃告警

        Returns:
            List[AsyncAlert]: 活跃告警列表
        """
        async with self._alerts_lock:
            return [alert for alert in self._alerts if not alert.resolved]

    async def resolve_alert(self, alert_id: str):
        """
        解决告警（增强版，添加到历史记录）

        Args:
            alert_id: 告警ID
        """
        async with self._alerts_lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.resolved = True
                    alert.resolved_timestamp = time.time()
                    # 添加到历史记录
                    self._alert_history.append(alert)
                    logger.info(f"[Monitor] 告警已解决: {alert_id}")
                    return

    @property
    def state(self) -> AsyncMonitorState:
        """获取监控器状态"""
        return self._state

    async def add_alert_callback(self, callback: Callable[[AsyncAlert], None]):
        """添加告警回调

        Args:
            callback: 告警回调函数
        """
        if callback not in self._alert_callbacks:
            self._alert_callbacks.append(callback)

    async def remove_alert_callback(self, callback: Callable[[AsyncAlert], None]):
        """移除告警回调

        Args:
            callback: 告警回调函数
        """
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)

    async def add_recovery_callback(self, callback: Callable[[AsyncAxonWorker], None]):
        """添加自动恢复回调

        Args:
            callback: 恢复回调函数，参数为AsyncAxonWorker
        """
        if callback not in self._recovery_callbacks:
            self._recovery_callbacks.append(callback)

    async def remove_recovery_callback(self, callback: Callable[[AsyncAxonWorker], None]):
        """移除自动恢复回调

        Args:
            callback: 恢复回调函数
        """
        if callback in self._recovery_callbacks:
            self._recovery_callbacks.remove(callback)

    async def get_metric_history(
        self,
        metric_name: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: Optional[int] = None
    ) -> List[Union['MetricValue', Tuple[float, float]]]:
        """获取指标历史数据（与同步版本对齐）

        Args:
            metric_name: 指标名称
            start_time: 起始时间戳（None = 从最早开始）
            end_time: 结束时间戳（None = 到最新）
            limit: 返回条数限制（None = 全部返回）

        Returns:
            历史数据列表（MetricValue对象或(timestamp, value)元组）
        """
        async with self._metrics_lock:
            if metric_name not in self._metrics_history:
                return []

            # 获取历史数据
            history = list(self._metrics_history[metric_name])

            # 时间范围过滤
            if start_time is not None:
                history = [
                    h for h in history
                    if hasattr(h, 'timestamp') and h.timestamp >= start_time
                    or (isinstance(h, tuple) and h[0] >= start_time)
                ]
            if end_time is not None:
                history = [
                    h for h in history
                    if hasattr(h, 'timestamp') and h.timestamp <= end_time
                    or (isinstance(h, tuple) and h[0] <= end_time)
                ]

            # 数量限制
            if limit is not None:
                history = history[-limit:]

            return history

    async def export_metrics(self, file_path: str):
        """
        导出指标到文件（与同步版本对齐）

        Args:
            file_path: 文件路径
        """
        try:
            # 线程安全地获取指标数据
            async with self._metrics_lock:
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

            # 获取统计信息
            async with self._alerts_lock:
                stats_dict = {
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

            import json
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "current_metrics": current_metrics_copy,
                    "stats": stats_dict
                }, f, indent=2)

            logger.info(f"[Monitor] Metrics exported to {file_path}")
        except Exception as e:
            logger.error(f"[Monitor] Error exporting metrics: {e}")

    async def get_alert_history(self, limit: Optional[int] = None) -> List[AsyncAlert]:
        """
        获取历史告警记录（包括已解决的告警）

        Args:
            limit: 返回的最大数量，None 表示返回所有

        Returns:
            List[AsyncAlert]: 历史告警列表（按时间倒序）
        """
        async with self._alerts_lock:
            # 合并当前告警和历史告警
            all_alerts = self._alerts + self._alert_history
            # 按时间倒序排序
            all_alerts.sort(key=lambda a: a.timestamp, reverse=True)
            # 应用限制
            if limit is not None:
                return all_alerts[:limit]
            return all_alerts

    async def get_current_metrics(self) -> Dict[str, MetricValue]:
        """
        获取当前指标值

        Returns:
            Dict[str, MetricValue]: 当前指标字典
        """
        async with self._metrics_lock:
            return dict(self._current_metrics)

    def add_metric(self, name: str, value: float, metric_type: MetricType,
                   labels: Optional[Dict[str, str]] = None,
                   unit: str = "", description: str = ""):
        """
        添加或更新指标（与同步版本对齐）

        Args:
            name: 指标名称
            value: 指标值
            metric_type: 指标类型
            labels: 标签字典
            unit: 单位
            description: 描述
        """
        metric = MetricValue(
            name=name,
            value=value,
            timestamp=time.time(),
            metric_type=metric_type,
            labels=labels or {},
            unit=unit,
            description=description
        )

        # 这是同步方法，但会在收集循环中被调用
        # 使用 asyncio.Lock 可能会有问题，所以在实际的异步环境中
        # 应该使用异步版本或确保在正确的上下文中调用
        self._current_metrics[name] = metric

        # 添加到历史记录
        if name not in self._metrics_history:
            self._metrics_history[name] = deque(maxlen=self.max_metrics_history)
        self._metrics_history[name].append(value)

        logger.debug(f"[Monitor] Metric added: {name}={value}")

"""
AsyncWorkerMonitor 增强功能测试

测试新增的监控功能：
- MetricType 枚举和指标类型系统
- export_metrics 功能
- 历史告警记录
"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from aethelum_core_lite.core.async_worker_monitor import (
    AsyncWorkerMonitor,
    MetricType,
    MetricValue,
    AsyncAlert,
    AsyncAlertLevel,
    AsyncMonitorStats,
    ThresholdRule
)


@pytest.mark.asyncio
async def test_metric_type_enum():
    """测试 MetricType 枚举"""
    assert MetricType.COUNTER.value == "counter"
    assert MetricType.GAUGE.value == "gauge"
    assert MetricType.HISTOGRAM.value == "histogram"
    assert MetricType.RATE.value == "rate"


@pytest.mark.asyncio
async def test_metric_value_creation():
    """测试 MetricValue 数据类"""
    metric = MetricValue(
        name="test_metric",
        value=100.0,
        timestamp=1234567890.0,
        metric_type=MetricType.COUNTER,
        labels={"worker": "worker1"},
        unit="count",
        description="Test metric"
    )

    assert metric.name == "test_metric"
    assert metric.value == 100.0
    assert metric.metric_type == MetricType.COUNTER
    assert metric.labels["worker"] == "worker1"
    assert metric.unit == "count"
    assert metric.description == "Test metric"


@pytest.mark.asyncio
async def test_async_alert_enhanced():
    """测试增强的 AsyncAlert 数据类"""
    alert = AsyncAlert(
        alert_id="alert-1",
        level=AsyncAlertLevel.WARNING,
        title="Test Alert",
        message="This is a test alert",
        timestamp=1234567890.0,
        source="test_monitor",
        worker_id="worker-1",
        metric_name="cpu_percent",
        threshold=80.0,
        current_value=85.0,
        resolved=False,
        resolved_timestamp=None,
        metadata={"key": "value"}
    )

    assert alert.alert_id == "alert-1"
    assert alert.level == AsyncAlertLevel.WARNING
    assert alert.source == "test_monitor"
    assert alert.metric_name == "cpu_percent"
    assert alert.threshold == 80.0
    assert alert.current_value == 85.0
    assert alert.resolved is False
    assert alert.metadata["key"] == "value"


@pytest.mark.asyncio
async def test_async_monitor_stats_enhanced():
    """测试增强的 AsyncMonitorStats 数据类"""
    stats = AsyncMonitorStats(
        monitor_id="monitor-1",
        name="test_monitor",
        start_time=1234567890.0,
        uptime=3600.0,
        total_metrics_collected=1000,
        total_alerts_generated=10,
        active_alerts=2,
        resolved_alerts=8,
        metrics_collection_rate=10.0,
        monitored_workers=5,
        monitored_queues=3
    )

    assert stats.monitor_id == "monitor-1"
    assert stats.name == "test_monitor"
    assert stats.uptime == 3600.0
    assert stats.resolved_alerts == 8
    assert stats.monitored_workers == 5
    assert stats.monitored_queues == 3


@pytest.mark.asyncio
async def test_export_metrics():
    """测试 export_metrics 功能"""
    from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 添加一些测试指标
    monitor.add_metric(
        name="test_counter",
        value=100.0,
        metric_type=MetricType.COUNTER,
        unit="count",
        description="Test counter metric"
    )

    monitor.add_metric(
        name="test_gauge",
        value=75.5,
        metric_type=MetricType.GAUGE,
        unit="percent",
        description="Test gauge metric"
    )

    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_file = f.name

    try:
        # 导出指标
        await monitor.export_metrics(temp_file)

        # 验证文件存在
        assert Path(temp_file).exists()

        # 读取并验证内容
        with open(temp_file, 'r') as f:
            data = json.load(f)

        assert "current_metrics" in data
        assert "stats" in data
        assert "test_counter" in data["current_metrics"]
        assert "test_gauge" in data["current_metrics"]
        assert data["current_metrics"]["test_counter"]["value"] == 100.0
        assert data["current_metrics"]["test_gauge"]["metric_type"] == "gauge"

    finally:
        # 清理临时文件
        Path(temp_file).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_get_alert_history():
    """测试获取历史告警记录"""
    from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 创建一些测试告警
    alert1 = AsyncAlert(
        alert_id="alert-1",
        level=AsyncAlertLevel.WARNING,
        title="Alert 1",
        message="First alert",
        timestamp=1000.0,
        source="test_monitor"
    )

    alert2 = AsyncAlert(
        alert_id="alert-2",
        level=AsyncAlertLevel.ERROR,
        title="Alert 2",
        message="Second alert",
        timestamp=2000.0,
        source="test_monitor"
    )

    # 添加到当前告警列表
    monitor._alerts.append(alert1)
    monitor._alerts.append(alert2)

    # 解决第二个告警
    await monitor.resolve_alert("alert-2")

    # 获取所有历史记录
    history = await monitor.get_alert_history()
    assert len(history) == 2

    # 验证已解决标记
    alert2_in_history = next(a for a in history if a.alert_id == "alert-2")
    assert alert2_in_history.resolved is True
    assert alert2_in_history.resolved_timestamp is not None


@pytest.mark.asyncio
async def test_get_current_metrics():
    """测试获取当前指标"""
    from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 添加测试指标
    monitor.add_metric("metric1", 10.0, MetricType.COUNTER)
    monitor.add_metric("metric2", 20.0, MetricType.GAUGE)

    # 获取当前指标
    metrics = await monitor.get_current_metrics()

    assert len(metrics) == 2
    assert "metric1" in metrics
    assert "metric2" in metrics
    assert metrics["metric1"].value == 10.0
    assert metrics["metric2"].value == 20.0


@pytest.mark.asyncio
async def test_add_metric():
    """测试添加指标"""
    from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 添加指标
    monitor.add_metric(
        name="test_metric",
        value=42.0,
        metric_type=MetricType.HISTOGRAM,
        labels={"label1": "value1"},
        unit="ms",
        description="Test histogram metric"
    )

    # 验证指标已添加
    assert "test_metric" in monitor._current_metrics
    assert monitor._current_metrics["test_metric"].value == 42.0
    assert monitor._current_metrics["test_metric"].metric_type == MetricType.HISTOGRAM
    assert monitor._current_metrics["test_metric"].labels["label1"] == "value1"
    assert monitor._current_metrics["test_metric"].unit == "ms"

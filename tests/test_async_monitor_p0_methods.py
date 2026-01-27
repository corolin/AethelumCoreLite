"""
异步Monitor组件P0方法单元测试

测试新增的5个P0方法：
- add_alert_callback()
- remove_alert_callback()
- add_recovery_callback()
- remove_recovery_callback()
- get_metric_history()
"""

import pytest
import asyncio
import time
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_worker_monitor import (
    AsyncWorkerMonitor,
    AsyncAlert,
    AsyncAlertLevel,
    MetricValue,
    MetricType
)
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.message import NeuralImpulse


@pytest.mark.asyncio
async def test_add_alert_callback():
    """测试添加告警回调"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 创建回调函数
    callback_called = []
    async def alert_callback(alert):
        callback_called.append(alert)

    # 添加回调
    await monitor.add_alert_callback(alert_callback)

    # 验证回调已添加
    assert alert_callback in monitor._alert_callbacks
    assert len(monitor._alert_callbacks) == 1


@pytest.mark.asyncio
async def test_remove_alert_callback():
    """测试移除告警回调"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 创建回调函数
    async def alert_callback(alert):
        pass

    # 添加并移除回调
    await monitor.add_alert_callback(alert_callback)
    await monitor.remove_alert_callback(alert_callback)

    # 验证回调已移除
    assert alert_callback not in monitor._alert_callbacks
    assert len(monitor._alert_callbacks) == 0


@pytest.mark.asyncio
async def test_remove_nonexistent_alert_callback():
    """测试移除不存在的告警回调"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    async def alert_callback(alert):
        pass

    # 尝试移除未添加的回调（不应该抛出异常）
    await monitor.remove_alert_callback(alert_callback)

    assert len(monitor._alert_callbacks) == 0


@pytest.mark.asyncio
async def test_add_recovery_callback():
    """测试添加恢复回调"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 创建回调函数
    callback_called = []
    async def recovery_callback(worker):
        callback_called.append(worker)

    # 添加回调
    await monitor.add_recovery_callback(recovery_callback)

    # 验证回调已添加
    assert recovery_callback in monitor._recovery_callbacks
    assert len(monitor._recovery_callbacks) == 1


@pytest.mark.asyncio
async def test_remove_recovery_callback():
    """测试移除恢复回调"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 创建回调函数
    async def recovery_callback(worker):
        pass

    # 添加并移除回调
    await monitor.add_recovery_callback(recovery_callback)
    await monitor.remove_recovery_callback(recovery_callback)

    # 验证回调已移除
    assert recovery_callback not in monitor._recovery_callbacks
    assert len(monitor._recovery_callbacks) == 0


@pytest.mark.asyncio
async def test_add_duplicate_callback():
    """测试添加重复回调（不应该重复添加）"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    async def callback(alert):
        pass

    # 添加两次相同的回调
    await monitor.add_alert_callback(callback)
    await monitor.add_alert_callback(callback)

    # 验证只有一个回调
    assert monitor._alert_callbacks.count(callback) == 1


@pytest.mark.asyncio
async def test_get_metric_history_empty():
    """测试获取空指标的历��"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 获取不存在的指标历史
    history = await monitor.get_metric_history("nonexistent_metric")

    assert history == []


@pytest.mark.asyncio
async def test_get_metric_history_with_limit():
    """测试获取指标历史（限制数量）"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 添加指标历史
    for i in range(10):
        metric = MetricValue(
            name="test_metric",
            value=float(i),
            timestamp=time.time() + i,
            metric_type=MetricType.COUNTER
        )
        monitor._metrics_history.setdefault("test_metric", []).append(metric)

    # 获取最后5条记录
    history = await monitor.get_metric_history("test_metric", limit=5)

    assert len(history) == 5
    # 验证是最后5条记录
    assert history[0].value == 5.0
    assert history[-1].value == 9.0


@pytest.mark.asyncio
async def test_get_metric_history_with_time_range():
    """测试获取指标历史（时间范围过滤）"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    base_time = time.time()

    # 添加不同时间点的指标
    for i in range(10):
        metric = MetricValue(
            name="test_metric",
            value=float(i),
            timestamp=base_time + i,
            metric_type=MetricType.COUNTER
        )
        monitor._metrics_history.setdefault("test_metric", []).append(metric)

    # 获取中间5秒的数据（从第2秒到第7秒）
    history = await monitor.get_metric_history(
        "test_metric",
        start_time=base_time + 2,
        end_time=base_time + 7
    )

    assert len(history) == 6  # 包含2,3,4,5,6,7
    assert history[0].value == 2.0
    assert history[-1].value == 7.0


@pytest.mark.asyncio
async def test_get_metric_history_all():
    """测试获取所有指标历史"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 添加指标历史
    for i in range(5):
        metric = MetricValue(
            name="test_metric",
            value=float(i),
            timestamp=time.time() + i,
            metric_type=MetricType.COUNTER
        )
        monitor._metrics_history.setdefault("test_metric", []).append(metric)

    # 获取所有历史（不限制数量）
    history = await monitor.get_metric_history("test_metric")

    assert len(history) == 5


@pytest.mark.asyncio
async def test_integration_callback_system():
    """集成测试：回调系统整体工作流程"""
    router = AsyncNeuralSomaRouter("test_router")
    monitor = AsyncWorkerMonitor("test_monitor", router)

    # 记录回调调用
    alert_log = []
    recovery_log = []

    async def alert_callback(alert):
        alert_log.append(alert)

    async def recovery_callback(worker):
        recovery_log.append(worker)

    # 添加回调
    await monitor.add_alert_callback(alert_callback)
    await monitor.add_recovery_callback(recovery_callback)

    # 创建测试告警
    test_alert = AsyncAlert(
        alert_id="test-001",
        level=AsyncAlertLevel.WARNING,
        title="Test Alert",
        message="This is a test alert",
        timestamp=time.time(),
        source="test_monitor"
    )

    # 手动调用回调（模拟告警触发）
    for callback in monitor._alert_callbacks:
        await callback(test_alert)

    # 验证告警回调被调用
    assert len(alert_log) == 1
    assert alert_log[0].alert_id == "test-001"

    # 移除回调
    await monitor.remove_alert_callback(alert_callback)

    # 再次调用（不应该触发）
    for callback in monitor._alert_callbacks:
        await callback(test_alert)

    # 验证回调已被移除，数量没有增加
    assert len(alert_log) == 1

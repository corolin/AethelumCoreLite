"""
异步架构P0功能集成测试

测试Router和Monitor组件新增的P0方法协同工作
"""

import pytest
import asyncio
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_worker_monitor import AsyncWorkerMonitor
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_hooks import AsyncHookType
from aethelum_core_lite.core.queue import QueuePriority
from aethelum_core_lite.core.message import NeuralImpulse


@pytest.mark.asyncio
async def test_dynamic_worker_scaling_workflow():
    """测试动态Worker伸缩工作流程"""
    router = AsyncNeuralSomaRouter("scaling_router")
    monitor = AsyncWorkerMonitor("scaling_monitor", router)

    # 1. 创建队列并设置优先级
    queue = AsyncSynapticQueue("scaling_queue", enable_wal=False)
    router.register_queue(queue, priority=QueuePriority.NORMAL)

    # 2. 设置高优先级
    await router.set_queue_priority("scaling_queue", QueuePriority.HIGH)
    priority = await router.get_queue_priority("scaling_queue")
    assert priority == QueuePriority.HIGH

    # 3. 初始启动2个Worker
    await router.start_workers_async("scaling_queue", 2)

    # 4. 动态扩容到10个Worker
    result = await router.adjust_workers("scaling_queue", 10)
    assert result["added"] == 8

    # 5. 检查队列大小
    sizes = await router.get_queue_sizes()
    assert "scaling_queue" in sizes

    # 6. 动态缩容到3个Worker
    result = await router.adjust_workers("scaling_queue", 3)
    assert result["removed"] == 7


@pytest.mark.asyncio
async def test_callback_system_workflow():
    """测试回调系统工作流程"""
    router = AsyncNeuralSomaRouter("callback_router")
    monitor = AsyncWorkerMonitor("callback_monitor", router)

    # 1. 创建队列
    queue = AsyncSynapticQueue("callback_queue", enable_wal=False)
    router.register_queue(queue)

    # 2. 添加自定义告警和恢复回调
    alert_triggered = []
    recovery_triggered = []

    async def custom_alert_handler(alert):
        alert_triggered.append(alert.alert_id)

    async def custom_recovery_handler(worker):
        recovery_triggered.append(worker.worker_id)

    await monitor.add_alert_callback(custom_alert_handler)
    await monitor.add_recovery_callback(custom_recovery_handler)

    # 3. 验证回调已注册
    assert len(monitor._alert_callbacks) == 1
    assert len(monitor._recovery_callbacks) == 1

    # 4. 移除告警回调
    await monitor.remove_alert_callback(custom_alert_handler)
    assert len(monitor._alert_callbacks) == 0


@pytest.mark.asyncio
async def test_hook_management_workflow():
    """测试Hook管理工作流程"""
    router = AsyncNeuralSomaRouter("hook_router")

    # 1. 创建队列
    queue = AsyncSynapticQueue("hook_queue", enable_wal=False)
    router.register_queue(queue)

    # 2. 注册多个Hook
    async def hook1(impulse):
        impulse.metadata["hook1"] = True
        return impulse

    async def hook2(impulse):
        impulse.metadata["hook2"] = True
        return impulse

    async def hook3(impulse):
        impulse.metadata["hook3"] = True
        return impulse

    await router.register_hook("hook_queue", hook1, AsyncHookType.PRE_PROCESS)
    await router.register_hook("hook_queue", hook2, AsyncHookType.PRE_PROCESS)
    await router.register_hook("hook_queue", hook3, AsyncHookType.POST_PROCESS)

    # 3. 验证Hook已注册
    pre_hooks = router.get_hooks("hook_queue", AsyncHookType.PRE_PROCESS)
    assert len(pre_hooks) == 2

    # 4. 按类型移除Hook
    removed = await router.unregister_hook("hook_queue", hook_type=AsyncHookType.PRE_PROCESS)
    assert removed == 2

    # 5. 验证Hook已移除
    pre_hooks = router.get_hooks("hook_queue", AsyncHookType.PRE_PROCESS)
    assert len(pre_hooks) == 0


@pytest.mark.asyncio
async def test_metric_history_workflow():
    """测试指标历史工作流程"""
    router = AsyncNeuralSomaRouter("metric_router")
    monitor = AsyncWorkerMonitor("metric_monitor", router)

    # 1. 添加指标
    for i in range(20):
        await monitor.add_metric(
            name="test_counter",
            value=float(i),
            metric_type="counter"
        )

    # 2. 获取所有历史
    all_history = await monitor.get_metric_history("test_counter")
    assert len(all_history) == 20

    # 3. 获取限制数量的历史
    limited_history = await monitor.get_metric_history("test_counter", limit=10)
    assert len(limited_history) == 10

    # 4. 获取时间范围的历史
    import time
    base_time = time.time()
    recent_history = await monitor.get_metric_history(
        "test_counter",
        start_time=base_time - 10,
        limit=5
    )
    assert len(recent_history) <= 5


@pytest.mark.asyncio
async def test_end_to_end_workflow():
    """端到端集成测试"""
    router = AsyncNeuralSomaRouter("e2e_router")
    monitor = AsyncWorkerMonitor("e2e_monitor", router)

    # 1. 创建多个队列
    queue1 = AsyncSynapticQueue("queue1", enable_wal=False)
    queue2 = AsyncSynapticQueue("queue2", enable_wal=False)
    router.register_queue(queue1, priority=QueuePriority.HIGH)
    router.register_queue(queue2, priority=QueuePriority.NORMAL)

    # 2. 启动Worker
    await router.start_workers_async("queue1", 3)
    await router.start_workers_async("queue2", 2)

    # 3. 添加消息
    await queue1.async_put("message1")
    await queue1.async_put("message2")
    await queue2.async_put("message3")

    # 4. 检查队列大小
    sizes = await router.get_queue_sizes()
    assert sizes["queue1"] == 2
    assert sizes["queue2"] == 1

    # 5. 动态调整队列1的Worker数量
    result = await router.adjust_workers("queue1", 5)
    assert result["added"] == 2

    # 6. 获取队列优先级
    priority1 = await router.get_queue_priority("queue1")
    priority2 = await router.get_queue_priority("queue2")
    assert priority1 == QueuePriority.HIGH
    assert priority2 == QueuePriority.NORMAL

    # 7. 动态修改队列优先级
    await router.set_queue_priority("queue2", QueuePriority.CRITICAL)
    priority2 = await router.get_queue_priority("queue2")
    assert priority2 == QueuePriority.CRITICAL

    # 8. 清理
    result = await router.adjust_workers("queue1", 0)
    assert result["removed"] == 5

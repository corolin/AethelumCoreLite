"""
异步Router组件P0方法单元测试

测试新增的5个P0方法：
- adjust_workers()
- unregister_hook()
- set_queue_priority()
- get_queue_priority()
- get_queue_sizes()
"""

import pytest
import asyncio
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_hooks import AsyncHookType
from aethelum_core_lite.core.queue import QueuePriority


@pytest.mark.asyncio
async def test_adjust_workers_scale_out():
    """测试动态扩容Worker"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue)

    # 初始启动3个Worker
    await router.start_workers_async("test_queue", 3)
    result = await router.adjust_workers("test_queue", 10)

    assert result["before"] == 3
    assert result["after"] == 10
    assert result["added"] == 7
    assert result["removed"] == 0


@pytest.mark.asyncio
async def test_adjust_workers_scale_in():
    """测试动态缩容Worker"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue)

    # 初始启动5个Worker
    await router.start_workers_async("test_queue", 5)
    result = await router.adjust_workers("test_queue", 2)

    assert result["before"] == 5
    assert result["after"] == 2
    assert result["added"] == 0
    assert result["removed"] == 3


@pytest.mark.asyncio
async def test_adjust_workers_no_change():
    """测试调整数量相同时的情况"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue)

    # 初始启动3个Worker
    await router.start_workers_async("test_queue", 3)
    result = await router.adjust_workers("test_queue", 3)

    assert result["before"] == 3
    assert result["after"] == 3
    assert result["added"] == 0
    assert result["removed"] == 0


@pytest.mark.asyncio
async def test_adjust_workers_invalid_queue():
    """测试调整不存在的队列"""
    router = AsyncNeuralSomaRouter("test_router")

    with pytest.raises(ValueError, match="队列不存在"):
        await router.adjust_workers("nonexistent_queue", 5)


@pytest.mark.asyncio
async def test_unregister_hook_by_type():
    """测试按Hook类型注销"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue)

    # 注册多个Hook
    async def hook1(impulse):
        return impulse

    async def hook2(impulse):
        return impulse

    await router.register_hook("test_queue", hook1, AsyncHookType.PRE_PROCESS)
    await router.register_hook("test_queue", hook2, AsyncHookType.PRE_PROCESS)

    # 注销所有PRE_PROCESS类型的Hook
    removed_count = await router.unregister_hook(
        "test_queue",
        hook_type=AsyncHookType.PRE_PROCESS
    )

    assert removed_count == 2
    hooks = router.get_hooks("test_queue", AsyncHookType.PRE_PROCESS)
    assert len(hooks) == 0


@pytest.mark.asyncio
async def test_unregister_hook_by_function():
    """测试按Hook函数注销"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue)

    # 注册多个Hook
    async def hook1(impulse):
        return impulse

    async def hook2(impulse):
        return impulse

    await router.register_hook("test_queue", hook1, AsyncHookType.PRE_PROCESS)
    await router.register_hook("test_queue", hook2, AsyncHookType.PRE_PROCESS)

    # 注销特定的Hook函数
    removed_count = await router.unregister_hook("test_queue", hook_function=hook1)

    assert removed_count == 1
    hooks = router.get_hooks("test_queue", AsyncHookType.PRE_PROCESS)
    assert len(hooks) == 1
    assert hook2 in hooks


@pytest.mark.asyncio
async def test_unregister_hook_all():
    """测试注销所有Hook"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue)

    # 注册多个不同类型的Hook
    async def hook1(impulse):
        return impulse

    async def hook2(impulse):
        return impulse

    await router.register_hook("test_queue", hook1, AsyncHookType.PRE_PROCESS)
    await router.register_hook("test_queue", hook2, AsyncHookType.POST_PROCESS)

    # 注销所有Hook
    removed_count = await router.unregister_hook("test_queue")

    assert removed_count == 2
    all_hooks = router.get_hooks("test_queue")
    assert len(all_hooks) == 0


@pytest.mark.asyncio
async def test_unregister_hook_nonexistent_queue():
    """测试注销不存在队列的Hook"""
    router = AsyncNeuralSomaRouter("test_router")

    # 尝试注销不存在队列的Hook
    removed_count = await router.unregister_hook("nonexistent_queue")

    assert removed_count == 0


@pytest.mark.asyncio
async def test_set_queue_priority():
    """测试设置队列优先级"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列（默认NORMAL优先级）
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue, priority=QueuePriority.NORMAL)

    # 修改优先级为HIGH
    success = await router.set_queue_priority("test_queue", QueuePriority.HIGH)

    assert success is True
    priority = await router.get_queue_priority("test_queue")
    assert priority == QueuePriority.HIGH


@pytest.mark.asyncio
async def test_set_queue_priority_invalid_queue():
    """测试设置不存在队列的优先级"""
    router = AsyncNeuralSomaRouter("test_router")

    success = await router.set_queue_priority("nonexistent_queue", QueuePriority.HIGH)

    assert success is False


@pytest.mark.asyncio
async def test_get_queue_priority():
    """测试获取队列优先级"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue, priority=QueuePriority.CRITICAL)

    priority = await router.get_queue_priority("test_queue")

    assert priority == QueuePriority.CRITICAL


@pytest.mark.asyncio
async def test_get_queue_priority_nonexistent():
    """测试获取不存在队列的优先级"""
    router = AsyncNeuralSomaRouter("test_router")

    priority = await router.get_queue_priority("nonexistent_queue")

    assert priority is None


@pytest.mark.asyncio
async def test_get_queue_sizes():
    """测试获取所有队列大小"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建多个队列
    queue1 = AsyncSynapticQueue("queue1", enable_wal=False)
    queue2 = AsyncSynapticQueue("queue2", enable_wal=False)
    router.register_queue(queue1)
    router.register_queue(queue2)

    # 添加消息到队列
    await queue1.async_put("message1")
    await queue1.async_put("message2")
    await queue2.async_put("message3")

    sizes = await router.get_queue_sizes()

    assert sizes["queue1"] == 2
    assert sizes["queue2"] == 1


@pytest.mark.asyncio
async def test_get_queue_sizes_empty():
    """测试获取空队列的大小"""
    router = AsyncNeuralSomaRouter("test_router")

    # 创建空队列
    queue = AsyncSynapticQueue("test_queue", enable_wal=False)
    router.register_queue(queue)

    sizes = await router.get_queue_sizes()

    assert sizes["test_queue"] == 0


@pytest.mark.asyncio
async def test_integration_all_p0_methods():
    """集成测试：所有P0方法协同工作"""
    router = AsyncNeuralSomaRouter("integration_test_router")

    # 1. 创建队列并设置优先级
    queue = AsyncSynapticQueue("integration_queue", enable_wal=False)
    router.register_queue(queue, priority=QueuePriority.NORMAL)
    await router.set_queue_priority("integration_queue", QueuePriority.HIGH)

    # 2. 注册Hook
    async def test_hook(impulse):
        impulse.metadata["hook_executed"] = True
        return impulse

    await router.register_hook("integration_queue", test_hook, AsyncHookType.PRE_PROCESS)

    # 3. 启动Worker并动态调整
    await router.start_workers_async("integration_queue", 2)
    result = await router.adjust_workers("integration_queue", 5)
    assert result["added"] == 3

    # 4. 检查队列状态
    sizes = await router.get_queue_sizes()
    assert "integration_queue" in sizes

    priority = await router.get_queue_priority("integration_queue")
    assert priority == QueuePriority.HIGH

    # 5. 清理Hook
    removed = await router.unregister_hook("integration_queue", hook_function=test_hook)
    assert removed == 1

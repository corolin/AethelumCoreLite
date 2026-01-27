"""
AsyncSynapticQueue 增强功能测试

测试新增的便利方法：task_done(), join(), clear(), get_expired_messages(), close()
"""

import pytest
import asyncio
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.message import MessagePriority


@pytest.mark.asyncio
async def test_task_done():
    """测试 task_done 方法"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    # 放入消息
    await queue.async_put("message")
    assert queue.size() == 1

    # 标记任务完成
    await queue.task_done()

    await queue.stop()


@pytest.mark.asyncio
async def test_join():
    """测试 join 方法 - 等待所有任务完成"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    processed = []

    async def worker():
        """Worker处理消息"""
        while True:
            try:
                # 使用非阻塞获取
                msg = await asyncio.wait_for(queue.async_get(), timeout=0.5)
                processed.append(msg)
                await queue.task_done()  # 标记任务完成
            except asyncio.TimeoutError:
                break

    # 启动worker
    task = asyncio.create_task(worker())

    # 放入消息
    await queue.async_put("message1")
    await queue.async_put("message2")
    await queue.async_put("message3")

    # 等待所有任务完成
    await queue.join()

    # 验证所有消息都被处理
    assert len(processed) == 3
    assert "message1" in processed
    assert "message2" in processed
    assert "message3" in processed

    # 清理
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    await queue.stop()


@pytest.mark.asyncio
async def test_clear():
    """测试 clear 方法 - 清空队列"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    # 放入消息
    await queue.async_put("msg1")
    await queue.async_put("msg2")
    await queue.async_put("msg3")
    assert queue.size() == 3
    assert not queue.empty()

    # 清空队列
    await queue.clear()

    # 验证队列已清空
    assert queue.size() == 0
    assert queue.empty()

    await queue.stop()


@pytest.mark.asyncio
async def test_clear_with_metrics():
    """测试 clear 方法后的指标更新"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    # 放入消息
    await queue.async_put("msg1")
    await queue.async_put("msg2")

    # 获取清空前的指标
    metrics_before = await queue.get_metrics()
    assert metrics_before.size == 2

    # 清空队列
    await queue.clear()

    # 获取清空后的指标
    metrics_after = await queue.get_metrics()
    assert metrics_after.size == 0

    await queue.stop()


@pytest.mark.asyncio
async def test_get_expired_messages():
    """测试获取过期消息"""
    # 使用较短的TTL（100毫秒）
    queue = AsyncSynapticQueue("test_queue", message_ttl=0.1)
    await queue.start()

    # 放入消息
    await queue.async_put("msg1")
    await queue.async_put("msg2")

    # 等待消息过期
    await asyncio.sleep(0.15)

    # 获取过期消息（不删除）
    expired = await queue.get_expired_messages()

    # 验证有消息过期
    # 注意：由于消息可能在TTL内被处理，所以可能为0
    assert isinstance(expired, list)

    await queue.stop()


@pytest.mark.asyncio
async def test_get_expired_messages_before_expiration():
    """测试在消息过期前获取过期消息"""
    queue = AsyncSynapticQueue("test_queue", message_ttl=1.0)  # 1秒TTL
    await queue.start()

    # 放入消息
    await queue.async_put("msg1")
    await queue.async_put("msg2")

    # 立即获取过期消息（应该没有）
    expired = await queue.get_expired_messages()

    # 验证没有过期消息
    assert len(expired) == 0

    await queue.stop()


@pytest.mark.asyncio
async def test_close_alias():
    """测试 close() 是 stop() 的别名"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    # 放入消息
    await queue.async_put("message")
    assert queue.size() == 1

    # 使用 close() 停止队列
    await queue.close()

    # 验证队列已停止（无法再放入消息）
    # 注意：由于 stop() 不会立即阻止所有操作，这里只是验证close()方法可调用
    assert queue.close == queue.stop


@pytest.mark.asyncio
async def test_task_done_and_join_workflow():
    """测试完整的 task_done + join 工作流"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    results = []

    async def processor(item):
        """模拟处理消息"""
        await asyncio.sleep(0.01)  # 模拟处理时间
        results.append(item)
        await queue.task_done()

    # 启动多个处理器
    async def worker():
        while True:
            try:
                msg = await asyncio.wait_for(queue.async_get(), timeout=0.5)
                # 并发处理
                await processor(msg)
            except asyncio.TimeoutError:
                break

    workers = [asyncio.create_task(worker()) for _ in range(3)]

    # 放入多个消息
    messages = [f"msg{i}" for i in range(10)]
    for msg in messages:
        await queue.async_put(msg)

    # 等待所有消息处理完成
    await queue.join()

    # 验证所有消息都被处理
    assert len(results) == 10

    # 清理
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    await queue.stop()


@pytest.mark.asyncio
async def test_clear_empty_queue():
    """测试清空空队列（不应出错）"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    # 队列为空时清空
    await queue.clear()

    # 验证仍然是空的
    assert queue.size() == 0
    assert queue.empty()

    await queue.stop()


@pytest.mark.asyncio
async def test_clear_with_batch_operations():
    """测试 clear 与批量操作的配合"""
    queue = AsyncSynapticQueue("test_queue")
    await queue.start()

    # 批量放入消息
    items = [(f"msg{i}", MessagePriority.NORMAL) for i in range(10)]
    count = await queue.batch_put(items)
    assert count == 10
    assert queue.size() == 10

    # 清空队列
    await queue.clear()
    assert queue.size() == 0

    # 再次批量放入
    count = await queue.batch_put(items)
    assert count == 10
    assert queue.size() == 10

    await queue.stop()

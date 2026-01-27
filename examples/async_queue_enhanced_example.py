"""
AsyncSynapticQueue 增强功能示例

演示新增的便利方法：
- task_done() - 标记任务完成
- join() - 等待所有任务完成
- clear() - 清空队列
- get_expired_messages() - 获取过期消息
- close() - stop() 的别名
"""

import asyncio
import logging
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.message import MessagePriority

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_basic_usage():
    """示例1：基础使用 - task_done 和 join"""
    print("\n" + "="*60)
    print("示例1：基础使用 - task_done 和 join")
    print("="*60)

    queue = AsyncSynapticQueue("example_queue")
    await queue.start()

    processed = []

    async def worker():
        """Worker处理消息"""
        while True:
            try:
                # 获取消息（带超时）
                msg = await asyncio.wait_for(queue.async_get(), timeout=1.0)
                logger.info(f"处理消息: {msg}")
                processed.append(msg)

                # 标记任务完成
                await queue.task_done()
            except asyncio.TimeoutError:
                break

    # 启动worker
    worker_task = asyncio.create_task(worker())

    # 放入消息
    messages = ["task1", "task2", "task3", "task4", "task5"]
    for msg in messages:
        await queue.async_put(msg)
        logger.info(f"已放入消息: {msg}, 当前队列大小: {queue.size()}")

    # 等待所有任务完成
    logger.info("等待所有任务完成...")
    await queue.join()
    logger.info(f"所有任务已完成！处理了 {len(processed)} 个消息")

    # 清理
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    await queue.close()  # 使用 close() 别名
    logger.info("队列已关闭\n")


async def example_clear_queue():
    """示例2：清空队列"""
    print("\n" + "="*60)
    print("示例2：清空队列")
    print("="*60)

    queue = AsyncSynapticQueue("clear_example")
    await queue.start()

    # 批量放入消息
    items = [(f"msg{i}", MessagePriority.NORMAL) for i in range(100)]
    count = await queue.batch_put(items)
    logger.info(f"批量放入 {count} 条消息")
    logger.info(f"当前队列大小: {queue.size()}")

    # 清空队列
    logger.info("清空队列...")
    await queue.clear()
    logger.info(f"清空后队列大小: {queue.size()}, 是否为空: {queue.empty()}")

    # 再次放入消息验证队列仍可用
    await queue.async_put("new_message")
    logger.info(f"重新放入消息后队列大小: {queue.size()}")

    await queue.close()
    logger.info("队列已关闭\n")


async def example_expired_messages():
    """示例3：处理过期消息"""
    print("\n" + "="*60)
    print("示例3：处理过期消息")
    print("="*60)

    # 创建带TTL的队列（500毫秒过期）
    queue = AsyncSynapticQueue("ttl_example", message_ttl=0.5)
    await queue.start()

    # 放入消息
    await queue.async_put("msg1")
    await queue.async_put("msg2")
    await queue.async_put("msg3")
    logger.info(f"放入3条消息，TTL=500ms")

    # 立即检查过期消息（应该没有）
    expired = await queue.get_expired_messages()
    logger.info(f"立即检查过期消息: {len(expired)} 条")

    # 等待消息过期
    logger.info("等待600ms...")
    await asyncio.sleep(0.6)

    # 检查过期消息
    expired = await queue.get_expired_messages()
    logger.info(f"600ms后检查过期消息: {len(expired)} 条")

    # 移除过期消息
    removed = await queue.remove_expired_messages()
    logger.info(f"移除了 {removed} 条过期消息")
    logger.info(f"当前队列大小: {queue.size()}")

    await queue.close()
    logger.info("队列已关闭\n")


async def example_multiple_workers():
    """示例4：多Worker协同 - 使用 join 等待所有任务"""
    print("\n" + "="*60)
    print("示例4：多Worker协同")
    print("="*60)

    queue = AsyncSynapticQueue("multi_worker_example")
    await queue.start()

    results = []
    worker_count = 3

    async def worker(worker_id):
        """Worker处理消息"""
        while True:
            try:
                msg = await asyncio.wait_for(queue.async_get(), timeout=1.0)
                logger.info(f"Worker-{worker_id} 处理消息: {msg}")

                # 模拟处理时间
                await asyncio.sleep(0.1)

                results.append((worker_id, msg))
                await queue.task_done()
            except asyncio.TimeoutError:
                break

    # 启动多个worker
    workers = [asyncio.create_task(worker(i)) for i in range(worker_count)]
    logger.info(f"启动了 {worker_count} 个worker")

    # 放入多个消息
    messages = [f"task{i}" for i in range(10)]
    for msg in messages:
        await queue.async_put(msg)

    logger.info(f"放入 {len(messages)} 条消息，等待处理...")

    # 等待所有任务完成
    await queue.join()
    logger.info(f"所有任务已完成！处理了 {len(results)} 个消息")

    # 分析结果
    from collections import Counter
    worker_distribution = Counter([w for w, _ in results])
    logger.info(f"Worker任务分布: {dict(worker_distribution)}")

    # 清理
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    await queue.close()
    logger.info("队列已关闭\n")


async def example_priority_with_enhancements():
    """示例5：优先级队列 + 增强功能"""
    print("\n" + "="*60)
    print("示例5：优先级队列 + 增强功能")
    print("="*60)

    queue = AsyncSynapticQueue("priority_example")
    await queue.start()

    # 使用不同优先级放入消息
    messages = [
        ("low_priority_task", MessagePriority.LOW),
        ("critical_task", MessagePriority.CRITICAL),
        ("normal_task", MessagePriority.NORMAL),
        ("high_priority_task", MessagePriority.HIGH),
        ("background_task", MessagePriority.BACKGROUND),
    ]

    for msg, priority in messages:
        await queue.async_put(msg, priority)
        logger.info(f"放入消息: {msg} (优先级: {priority.name})")

    logger.info(f"队列大小: {queue.size()}")

    # 按优先级获取消息
    logger.info("按优先级获取消息:")
    for _ in range(len(messages)):
        msg = await queue.async_get()
        logger.info(f"  -> {msg}")
        await queue.task_done()

    # 等待所有任务完成
    await queue.join()
    logger.info("所有消息已处理")

    await queue.close()
    logger.info("队列已关闭\n")


async def main():
    """运行所有示例"""
    print("\n" + "="*60)
    print("AsyncSynapticQueue 增强功能演示")
    print("="*60)

    try:
        await example_basic_usage()
        await example_clear_queue()
        await example_expired_messages()
        await example_multiple_workers()
        await example_priority_with_enhancements()

        print("\n" + "="*60)
        print("所有示例运行完成！")
        print("="*60)

    except Exception as e:
        logger.error(f"示例运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())

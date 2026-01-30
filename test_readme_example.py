"""
测试 README.md 中的快速开始示例（增强版）
"""
import asyncio
import logging
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.async_hooks import AsyncBaseHook, AsyncHookType
from aethelum_core_lite.core.message import NeuralImpulse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 定义处理 Hook（带日志）
class HandlerHook(AsyncBaseHook):
    async def process_async(self, impulse, source_queue):
        logger.info(f"[Hook] 处理消息: {impulse.message_id}")
        content = impulse.get_text_content()
        logger.info(f"[Hook] 原始内容: {content}")
        impulse.set_text_content(f"已处理: {content}")
        logger.info(f"[Hook] 处理完成，新内容: {impulse.get_text_content()}")
        return impulse

async def main():
    logger.info("=" * 60)
    logger.info("AethelumCoreLite 快速开始示例")
    logger.info("=" * 60)

    # 1. 创建路由器
    logger.info("\n[1/10] 创建路由器...")
    router = AsyncNeuralSomaRouter("my_router")
    logger.info(f"✓ 路由器创建成功: {router.router_id}")

    # 2. 创建队列（启用 WAL 持久化）
    logger.info("\n[2/10] 创建队列（启用 WAL 持久化）...")
    queue = AsyncSynapticQueue("input_queue", enable_wal=True)
    logger.info(f"✓ 队列创建成功: {queue.queue_id}")
    logger.info(f"  - 最大大小: {queue.max_size}")
    logger.info(f"  - 启用 WAL: {queue.enable_wal}")

    # 3. 创建工作器
    logger.info("\n[3/10] 创建工作器...")
    worker = AsyncAxonWorker("worker_1", input_queue=queue)
    logger.info(f"✓ 工作器创建成功: {worker.name}")
    logger.info(f"  - Worker ID: {worker.worker_id}")

    # 4. 注册组件
    logger.info("\n[4/10] 注册组件到路由器...")
    router.register_queue(queue)
    router.register_worker(worker)
    logger.info("✓ 组件注册成功")
    logger.info(f"  - 队列数: {len(router._queues)}")
    logger.info(f"  - 工作器数: {len(router._workers)}")

    # 5. 注册处理 Hook（通过 Router）
    logger.info("\n[5/10] 注册处理 Hook...")
    await router.register_hook(
        queue_name="input_queue",
        hook_function=HandlerHook("handler"),
        hook_type=AsyncHookType.PRE_PROCESS
    )
    logger.info("✓ Hook 注册成功")
    logger.info(f"  - 队列: input_queue")
    logger.info(f"  - 类型: PRE_PROCESS")

    # 6. 启动系统
    logger.info("\n[6/10] 启动系统...")
    await router.start()
    logger.info("✓ 系统启动成功")

    # 7. 发送消息
    logger.info("\n[7/10] 发送消息...")
    impulse = NeuralImpulse(content="Hello AethelumCore!")
    logger.info(f"创建消息:")
    logger.info(f"  - Message ID: {impulse.message_id}")
    logger.info(f"  - Session ID: {impulse.session_id}")
    logger.info(f"  - 内容: {impulse.get_text_content()}")

    await queue.async_put(impulse)
    logger.info(f"✓ 消息已发送到队列")

    # 显示队列状态
    queue_metrics = await queue.get_metrics()
    logger.info(f"队列状态:")
    logger.info(f"  - 当前大小: {queue_metrics.size}")
    logger.info(f"  - 总消息数: {queue_metrics.total_messages}")

    # 8. 等待处理
    logger.info("\n[8/10] 等待消息处理...")
    await asyncio.sleep(2)

    # 9. 获取统计信息
    logger.info("\n[9/10] 获取处理统计:")
    metrics = await router.get_metrics()

    logger.info(f"路由器指标:")
    logger.info(f"  - 总消息路由: {metrics['router']['total_messages_routed']}")

    if 'workers' in metrics:
        for worker_id, worker_metrics in metrics['workers'].items():
            logger.info(f"工作器 {worker_metrics['worker_name']}:")
            logger.info(f"  - 处理消息: {worker_metrics['processed_messages']}")
            logger.info(f"  - 健康分数: {worker_metrics['health_score']:.1f}%")

    # 10. 停止系统
    logger.info("\n[10/10] 停止系统...")
    await router.stop()
    logger.info("✓ 系统已停止")

    logger.info("\n" + "=" * 60)
    logger.info("✅ 快速开始示例运行成功！")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

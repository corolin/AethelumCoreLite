"""
AsyncIO系统使用示例

演示如何使用新的AsyncIO架构、配置管理和监控功能。
"""

import asyncio
from aethelum_core_lite.config import ConfigLoader
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue, MessagePriority
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter


async def main():
    """主函数"""
    print("=" * 60)
    print("AethelumCoreLite AsyncIO 示例")
    print("=" * 60)

    # 1. 加载配置
    print("\n[1] 加载配置...")
    config = ConfigLoader.load_from_file("config.toml")
    monitoring_config = ConfigLoader.get_monitoring_config(config)
    system_config = ConfigLoader.get_system_config(config)

    print(f"   Worker模式: {system_config.worker_mode}")
    print(f"   最大Workers: {system_config.max_workers}")
    print(f"   Prometheus启用: {monitoring_config.enable_prometheus}")
    print(f"   追踪启用: {monitoring_config.enable_tracing}")

    # 2. 创建Router
    print("\n[2] 创建Router...")
    router = AsyncNeuralSomaRouter("example_router")
    print(f"   Router ID: {router.router_id}")

    # 3. 创建队列
    print("\n[3] 创建队列...")
    queue1 = AsyncSynapticQueue("input_queue", max_size=100)
    queue2 = AsyncSynapticQueue("output_queue", max_size=100)

    router.register_queue(queue1)
    router.register_queue(queue2)
    print(f"   队列1: {queue1.queue_id} (容量: {queue1.max_size})")
    print(f"   队列2: {queue2.queue_id} (容量: {queue2.max_size})")

    # 4. 添加路由规则
    print("\n[4] 添加路由规则...")
    router.add_routing_rule("pattern_a", "input_queue")
    router.add_routing_rule("pattern_b", "output_queue")
    print("   路由规则已添加")

    # 5. 创建Worker
    print("\n[5] 创建Worker...")
    worker1 = AsyncAxonWorker("worker_1", input_queue=queue1)
    worker2 = AsyncAxonWorker("worker_2", input_queue=queue2)

    router.register_worker(worker1)
    router.register_worker(worker2)
    print(f"   Worker1: {worker1.name} (ID: {worker1.worker_id})")
    print(f"   Worker2: {worker2.name} (ID: {worker2.worker_id})")

    # 6. 启动系统
    print("\n[6] 启动系统...")
    await router.start()
    print("   系统已启动")

    # 7. 发送消息
    print("\n[7] 发送测试消息...")
    await router.route_message({"task": "test_1"}, "pattern_a")
    await router.route_message({"task": "test_2"}, "pattern_a")
    await router.route_message({"task": "test_3"}, "pattern_b")
    print("   消息已发送")

    # 8. 等待处理
    print("\n[8] 等待消息处理...")
    await asyncio.sleep(2)

    # 9. 查看指标
    print("\n[9] 查看指标...")
    metrics = router.get_metrics()

    print(f"   Router指标:")
    print(f"     总Workers: {metrics['router']['total_workers']}")
    print(f"     总队列: {metrics['router']['total_queues']}")
    print(f"     总消息路由: {metrics['router']['total_messages_routed']}")

    print(f"\n   队列指标:")
    for queue_id, queue_metrics in metrics['queues'].items():
        print(f"     {queue_id}:")
        print(f"       大小: {queue_metrics['size']}")
        print(f"       使用率: {queue_metrics['usage_percent']:.1f}%")

    print(f"\n   Worker指标:")
    for worker_id, worker_metrics in metrics['workers'].items():
        print(f"     {worker_metrics['worker_name']}:")
        print(f"       处理消息: {worker_metrics['processed_messages']}")
        print(f"       健康分数: {worker_metrics['health_score']}")

    # 10. 停止系统
    print("\n[10] 停止系统...")
    await router.stop()
    print("   系统已停止")

    print("\n" + "=" * 60)
    print("示例完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

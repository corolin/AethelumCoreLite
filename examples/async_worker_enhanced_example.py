"""
AsyncAxonWorker 增强功能示例

演示新增的生产级功能：
- ErrorType 枚举和错误类型映射
- RECOVERING 状态和自动恢复
- Q_AUDIT 安全验证
- 健康检查机制
- 统计信息增强
"""

import asyncio
import logging
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_worker import AsyncAxonWorker, ErrorType
from aethelum_core_lite.core.message import NeuralImpulse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_basic_worker_lifecycle():
    """示例1：Worker 生命周期管理"""
    print("\n" + "="*60)
    print("示例1：Worker 生命周期管理")
    print("="*60)

    queue = AsyncSynapticQueue("lifecycle_example")
    await queue.start()

    worker = AsyncAxonWorker(
        name="lifecycle_worker",
        input_queue=queue,
        health_check_interval=5.0
    )

    print(f"初始状态: {worker.state}")

    # 启动 Worker
    await worker.start()
    print(f"启动后状态: {worker.state}")

    # 暂停 Worker
    await worker.pause()
    print(f"暂停后状态: {worker.state}")

    # 恢复 Worker
    await worker.resume()
    print(f"恢复后状态: {worker.state}")

    # 停止 Worker
    await worker.stop()
    print(f"停止后状态: {worker.state}")

    print("示例1完成\n")


async def example_error_type_mapping():
    """示例2：错误类型映射"""
    print("\n" + "="*60)
    print("示例2：错误类型映射系统")
    print("="*60)

    queue = AsyncSynapticQueue("error_mapping_example")
    worker = AsyncAxonWorker(name="error_mapping_worker", input_queue=queue)

    # 测试各种错误类型的映射
    test_errors = [
        (ValueError("Invalid input"), ErrorType.VALIDATION_ERROR),
        (RuntimeError("Processing failed"), ErrorType.PROCESSING_ERROR),
        (KeyError("Missing key"), ErrorType.ROUTING_ERROR),
        (AttributeError("Hook not found"), ErrorType.HOOK_ERROR),
        (OSError("System error"), ErrorType.SYSTEM_ERROR),
        (asyncio.TimeoutError(), ErrorType.TIMEOUT_ERROR),
    ]

    print("\n错误类型映射结果:")
    for error, expected_type in test_errors:
        mapped_type = worker._map_exception_to_error_type(error)
        status = "✓" if mapped_type == expected_type else "✗"
        print(f"  {status} {type(error).__name__:15} -> {mapped_type.value}")

    print("示例2完成\n")


async def example_q_audit_security():
    """示例3：Q_AUDIT 安全验证"""
    print("\n" + "="*60)
    print("示例3：Q_AUDIT 安全验证")
    print("="*60)

    queue = AsyncSynapticQueue("security_example")
    worker = AsyncAxonWorker(name="security_worker", input_queue=queue)

    # 场景1：消息未经过 Q_AUDIT_OUTPUT 审查（应该失败）
    print("\n场景1：未经过审查的消息")
    unsafe_impulse = NeuralImpulse(
        content="Unsafe message",
        action_intent="Q_RESPONSE_SINK",
        source_agent="test_agent"
    )

    try:
        worker._validate_sink_security(unsafe_impulse)
        print("  ✗ 安全验证失败：应该抛出异常")
    except ValueError as e:
        print(f"  ✓ 安全验证成功：{str(e)[:60]}...")

    # 场景2：消息经过 Q_AUDIT_OUTPUT 审查（应该通过）
    print("\n场景2：经过审查的消息")
    safe_impulse = NeuralImpulse(
        content="Safe message",
        action_intent="Q_RESPONSE_SINK",
        source_agent="test_agent"
    )
    safe_impulse.routing_history.append("Q_AUDIT_OUTPUT")

    try:
        worker._validate_sink_security(safe_impulse)
        print("  ✓ 安全验证成功：消息通过验证")
    except ValueError as e:
        print(f"  ✗ 安全验证失败：{e}")

    # 场景3：非响应队列的消息（不需要验证）
    print("\n场景3：非响应队列消息")
    normal_impulse = NeuralImpulse(
        content="Normal message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    try:
        worker._validate_sink_security(normal_impulse)
        print("  ✓ 跳过验证：非响应队列消息")
    except ValueError as e:
        print(f"  ✗ 验证失败：{e}")

    print("示例3完成\n")


async def example_auto_recovery():
    """示例4：自动恢复机制"""
    print("\n" + "="*60)
    print("示例4：自动恢复机制")
    print("="*60)

    queue = AsyncSynapticQueue("recovery_example")
    worker = AsyncAxonWorker(
        name="recovery_worker",
        input_queue=queue,
        max_consecutive_failures=3,
        recovery_delay=2.0
    )

    # 模拟连续失败
    print("\n模拟连续失败:")
    for i in range(3):
        async with worker._stats_lock:
            worker._stats.consecutive_failures += 1
        print(f"  第 {i+1} 次失败，当前连续失败次数: {worker._stats.consecutive_failures}")

    # 获取恢复前的状态
    stats_before = await worker.get_stats()
    print(f"\n恢复前状态:")
    print(f"  连续失败次数: {stats_before.consecutive_failures}")
    print(f"  恢复尝试次数: {stats_before.recovery_attempts}")

    # 进入恢复模式
    print("\n进入恢复模式...")
    await worker._enter_recovery_mode()

    # 获取恢复后的状态
    stats_after = await worker.get_stats()
    print(f"\n恢复后状态:")
    print(f"  连续失败次数: {stats_after.consecutive_failures}")
    print(f"  恢复尝试次数: {stats_after.recovery_attempts}")
    print(f"  Worker状态: {worker.state}")

    print("示例4完成\n")


async def example_health_monitoring():
    """示例5：健康监控"""
    print("\n" + "="*60)
    print("示例5：健康监控")
    print("="*60)

    queue = AsyncSynapticQueue("health_example")
    worker = AsyncAxonWorker(
        name="health_worker",
        input_queue=queue,
        health_check_interval=1.0
    )

    # 启动 Worker（包括健康检查）
    await worker.start()

    print("\n初始健康状态:")
    stats = await worker.get_stats()
    print(f"  健康分数: {stats.health_score:.1f}/100")
    print(f"  处理消息数: {stats.processed_messages}")
    print(f"  失败消息数: {stats.failed_messages}")
    print(f"  成功率: {stats.success_rate:.1f}%")

    # 模拟处理一些消息
    print("\n模拟处理消息...")
    async with worker._stats_lock:
        worker._stats.processed_messages = 80
        worker._stats.failed_messages = 20

    # 重新计算健康分数
    await worker._calculate_health_score()

    print("\n处理消息后的健康状态:")
    stats = await worker.get_stats()
    print(f"  健康分数: {stats.health_score:.1f}/100")
    print(f"  处理消息数: {stats.processed_messages}")
    print(f"  失败消息数: {stats.failed_messages}")
    print(f"  成功率: {stats.success_rate:.1f}%")

    # 等待健康检查运行
    print("\n等待健康检查运行...")
    await asyncio.sleep(1.5)

    # 停止 Worker
    await worker.stop()

    print("示例5完成\n")


async def example_enhanced_statistics():
    """示例6：增强的统计信息"""
    print("\n" + "="*60)
    print("示例6：增强的统计信息")
    print("="*60)

    queue = AsyncSynapticQueue("stats_example")
    worker = AsyncAxonWorker(
        name="stats_worker",
        input_queue=queue,
        recovery_delay=5.0,
        health_check_interval=10.0
    )

    # 获取初始统计信息
    stats = await worker.get_stats()

    print("\n新增的统计字段:")
    print(f"  Worker ID: {stats.worker_id}")
    print(f"  Worker 名称: {stats.name}")
    print(f"  状态: {stats.state}")
    print(f"  健康分数: {stats.health_score:.1f}")
    print(f"  运行时间: {stats.uptime:.2f}秒")
    print(f"  恢复尝试次数: {stats.recovery_attempts}")
    print(f"  连续失败次数: {stats.consecutive_failures}")
    print(f"  最后错误: {stats.last_error or 'None'}")
    print(f"  最后错误时间: {stats.last_error_time or 'None'}")
    print(f"  错误计数: {stats.error_counts}")

    print("\n标签 (Labels):")
    for key, value in stats.labels.items():
        print(f"  {key}: {value}")

    print("\n指标 (Metrics):")
    for key, value in stats.metrics.items():
        print(f"  {key}: {value}")

    print("示例6完成\n")


async def example_worker_with_message_processing():
    """示例7：完整的消息处理流程"""
    print("\n" + "="*60)
    print("示例7：完整的消息处理流程")
    print("="*60)

    queue = AsyncSynapticQueue("processing_example")
    worker = AsyncAxonWorker(
        name="processing_worker",
        input_queue=queue,
        max_consecutive_failures=3,
        recovery_delay=1.0,
        health_check_interval=5.0
    )

    await queue.start()
    await worker.start()

    # 创建安全的消息（经过 Q_AUDIT_OUTPUT）
    impulse = NeuralImpulse(
        content="Hello, World!",
        action_intent="Q_PROCESS_INPUT",
        source_agent="example_agent"
    )
    impulse.routing_history.append("Q_AUDIT_OUTPUT")

    # 放入消息
    await queue.async_put(impulse)
    print(f"\n已放入消息: {impulse.get_text_content()}")

    # 等待处理
    await asyncio.sleep(0.5)

    # 获取统计信息
    stats = await worker.get_stats()
    print(f"\n处理统计:")
    print(f"  处理消息数: {stats.processed_messages}")
    print(f"  健康分数: {stats.health_score:.1f}")
    print(f"  状态: {stats.state}")

    # 清理
    await worker.stop()
    await queue.stop()

    print("示例7完成\n")


async def main():
    """运行所有示例"""
    print("\n" + "="*60)
    print("AsyncAxonWorker 增强功能演示")
    print("="*60)

    try:
        await example_basic_worker_lifecycle()
        await example_error_type_mapping()
        await example_q_audit_security()
        await example_auto_recovery()
        await example_health_monitoring()
        await example_enhanced_statistics()
        await example_worker_with_message_processing()

        print("\n" + "="*60)
        print("所有示例运行完成！")
        print("="*60)

    except Exception as e:
        logger.error(f"示例运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())

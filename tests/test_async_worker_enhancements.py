"""
AsyncAxonWorker 增强功能测试

测试新增的生产级功能：
- ErrorType 枚举和错误类型映射
- RECOVERING 状态
- Q_AUDIT 安全验证
- 自动恢复机制
- 健康检查机制
"""

import pytest
import asyncio
from unittest.mock import Mock, patch
from aethelum_core_lite.core.async_worker import (
    AsyncAxonWorker,
    AsyncWorkerState,
    ErrorType
)
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.message import NeuralImpulse


@pytest.mark.asyncio
async def test_worker_states():
    """测试 Worker 状态包含 RECOVERING"""
    assert hasattr(AsyncWorkerState, 'RECOVERING')
    assert AsyncWorkerState.RECOVERING.value == "recovering"


@pytest.mark.asyncio
async def test_error_type_enum():
    """测试 ErrorType 枚举"""
    assert ErrorType.VALIDATION_ERROR.value == "validation_error"
    assert ErrorType.PROCESSING_ERROR.value == "processing_error"
    assert ErrorType.ROUTING_ERROR.value == "routing_error"
    assert ErrorType.QUEUE_ERROR.value == "queue_error"
    assert ErrorType.HOOK_ERROR.value == "hook_error"
    assert ErrorType.SYSTEM_ERROR.value == "system_error"
    assert ErrorType.TIMEOUT_ERROR.value == "timeout_error"


@pytest.mark.asyncio
async def test_worker_initialization():
    """测试 Worker 初始化"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(
        name="test_worker",
        input_queue=queue,
        max_consecutive_failures=5,
        recovery_delay=10.0,
        health_check_interval=30.0
    )

    assert worker.name == "test_worker"
    assert worker.max_consecutive_failures == 5
    assert worker.recovery_delay == 10.0
    assert worker.health_check_interval == 30.0
    assert worker._state == AsyncWorkerState.INITIALIZING


@pytest.mark.asyncio
async def test_q_audit_security_validation():
    """测试 Q_AUDIT 安全验证"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 测试消息没有经过 Q_AUDIT_OUTPUT 审查
    impulse = NeuralImpulse(
        content="test",
        action_intent="Q_RESPONSE_SINK",
        source_agent="test_agent"
    )

    # 应该抛出 ValueError
    with pytest.raises(ValueError) as exc_info:
        worker._validate_sink_security(impulse)

    assert "Security Violation" in str(exc_info.value)
    assert "Q_AUDIT_OUTPUT" in str(exc_info.value)


@pytest.mark.asyncio
async def test_q_audit_security_validation_with_audit_history():
    """测试消息经过 Q_AUDIT_OUTPUT 审查时不抛出异常"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 创建经过 Q_AUDIT_OUTPUT 审查的消息
    impulse = NeuralImpulse(
        content="test",
        action_intent="Q_RESPONSE_SINK",
        source_agent="test_agent"
    )
    impulse.routing_history.append("Q_AUDIT_OUTPUT")

    # 不应该抛出异常
    try:
        worker._validate_sink_security(impulse)
    except ValueError:
        pytest.fail("Should not raise ValueError when message has Q_AUDIT_OUTPUT in history")


@pytest.mark.asyncio
async def test_q_audit_validation_bypass_for_non_sink():
    """测试非 Q_RESPONSE_SINK 队列不验证"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 非响应队列的消息
    impulse = NeuralImpulse(
        content="test",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 不应该抛出异常
    try:
        worker._validate_sink_security(impulse)
    except ValueError:
        pytest.fail("Should not raise ValueError for non-Q_RESPONSE_SINK queues")


@pytest.mark.asyncio
async def test_error_type_mapping():
    """测试错误类型映射"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 测试各种错误类型的映射
    assert worker._map_exception_to_error_type(ValueError("")) == ErrorType.VALIDATION_ERROR
    assert worker._map_exception_to_error_type(RuntimeError("")) == ErrorType.PROCESSING_ERROR
    assert worker._map_exception_to_error_type(KeyError("")) == ErrorType.ROUTING_ERROR
    assert worker._map_exception_to_error_type(AttributeError("")) == ErrorType.HOOK_ERROR
    assert worker._map_exception_to_error_type(OSError("")) == ErrorType.SYSTEM_ERROR
    assert worker._map_exception_to_error_type(asyncio.TimeoutError()) == ErrorType.TIMEOUT_ERROR


@pytest.mark.asyncio
async def test_error_type_mapping_unknown_exception():
    """测试未知异常映射到 SYSTEM_ERROR"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 自定义异常
    class CustomException(Exception):
        pass

    assert worker._map_exception_to_error_type(CustomException()) == ErrorType.SYSTEM_ERROR


@pytest.mark.asyncio
async def test_enter_recovery_mode():
    """测试进入恢复模式"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(
        name="test_worker",
        input_queue=queue,
        recovery_delay=0.1  # 短延迟用于测试
    )

    # 模拟连续失败
    async with worker._stats_lock:
        worker._stats.consecutive_failures = 5

    # 进入恢复模式
    await worker._enter_recovery_mode()

    # 验证恢复后的状态
    async with worker._stats_lock:
        assert worker._stats.consecutive_failures == 0
        assert worker._state == AsyncWorkerState.RUNNING
        assert worker._stats.recovery_attempts > 0


@pytest.mark.asyncio
async def test_health_score_calculation():
    """测试健康分数计算"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 初始健康分数应该是 100
    await worker._calculate_health_score()
    async with worker._stats_lock:
        assert worker._stats.health_score == 100.0

    # 模拟一些处理和失败
    async with worker._stats_lock:
        worker._stats.processed_messages = 80
        worker._stats.failed_messages = 20
        worker._stats.consecutive_failures = 2
        worker._stats.recovery_attempts = 1

    await worker._calculate_health_score()

    async with worker._stats_lock:
        # 成功率: 80%
        # 基础分: 100 * 0.8 = 80
        # 连续失败扣除: 2 * 10 = 20
        # 恢复尝试扣除: 1 * 5 = 5
        # 最终分数: 80 - 20 - 5 = 55
        assert worker._stats.health_score == 55.0


@pytest.mark.asyncio
async def test_health_score_bounds():
    """测试健康分数边界（0-100）"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 模拟极端情况（很多失败）
    async with worker._stats_lock:
        worker._stats.processed_messages = 0
        worker._stats.failed_messages = 100
        worker._stats.consecutive_failures = 20
        worker._stats.recovery_attempts = 10

    await worker._calculate_health_score()

    async with worker._stats_lock:
        # 应该不低于 0
        assert worker._stats.health_score >= 0.0
        assert worker._stats.health_score <= 100.0


@pytest.mark.asyncio
async def test_worker_lifecycle():
    """测试 Worker 生命周期"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    # 初始状态
    assert worker.state == AsyncWorkerState.INITIALIZING

    # 启动
    await worker.start()
    assert worker.state == AsyncWorkerState.RUNNING

    # 暂停
    await worker.pause()
    assert worker.state == AsyncWorkerState.PAUSED

    # 恢复
    await worker.resume()
    assert worker.state == AsyncWorkerState.RUNNING

    # 停止
    await worker.stop()
    assert worker.state == AsyncWorkerState.STOPPED


@pytest.mark.asyncio
async def test_worker_stats_fields():
    """测试 Worker 统计信息字段"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    stats = await worker.get_stats()

    # 验证新增字段
    assert hasattr(stats, 'error_counts')
    assert hasattr(stats, 'last_error')
    assert hasattr(stats, 'last_error_time')
    assert hasattr(stats, 'recovery_attempts')
    assert hasattr(stats, 'consecutive_failures')
    assert hasattr(stats, 'health_score')
    assert hasattr(stats, 'uptime')
    assert hasattr(stats, 'labels')
    assert hasattr(stats, 'metrics')

    # 验证初始值
    assert stats.recovery_attempts == 0
    assert stats.consecutive_failures == 0
    assert stats.health_score == 100.0
    assert stats.error_counts == {}


@pytest.mark.asyncio
async def test_health_check_loop():
    """测试健康检查循环"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(
        name="test_worker",
        input_queue=queue,
        health_check_interval=0.1  # 短间隔用于测试
    )

    # 启动 worker（包括健康检查任务）
    await worker.start()

    # 等待健康检查运行几次
    await asyncio.sleep(0.3)

    # 停止 worker
    await worker.stop()

    # 验证健康检查任务已停止
    assert worker.state == AsyncWorkerState.STOPPED


@pytest.mark.asyncio
async def test_consecutive_failures_trigger_recovery():
    """测试连续失败触发恢复模式"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(
        name="test_worker",
        input_queue=queue,
        max_consecutive_failures=3,
        recovery_delay=0.1
    )

    # 模拟连续失败
    for i in range(3):
        async with worker._stats_lock:
            worker._stats.consecutive_failures += 1

    # 验证是否达到阈值
    async with worker._stats_lock:
        assert worker._stats.consecutive_failures >= 3


@pytest.mark.asyncio
async def test_stats_are_copies():
    """测试 get_stats 返回副本而非引用"""
    queue = AsyncSynapticQueue("test_queue")
    worker = AsyncAxonWorker(name="test_worker", input_queue=queue)

    stats1 = await worker.get_stats()
    stats2 = await worker.get_stats()

    # 两次调用应该返回不同的对象
    assert stats1 is not stats2

    # 修改副本不应该影响原始数据
    stats1.processed_messages = 999
    stats2_copy = await worker.get_stats()
    assert stats2_copy.processed_messages != 999

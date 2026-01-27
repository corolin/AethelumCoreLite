"""
AsyncNeuralSomaRouter 增强功能测试

测试新增的安全审计功能：
- Q_AUDIT_INPUT 和 Q_RESPONSE_SINK 队列创建
- Q_AUDIT_INPUT → Q_AUDIT_OUTPUT 强制路由
- 消息流安全验证
"""

import pytest
import asyncio
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.message import NeuralImpulse
from aethelum_core_lite.core.queue import QueuePriority


@pytest.mark.asyncio
async def test_mandatory_queues_creation():
    """测试强制性队列创建"""
    router = AsyncNeuralSomaRouter("test_router")

    # 激活路由器（应该创建所有强制性队列）
    await router.activate()

    # 验证强制性队列都已创建
    assert 'Q_AUDIT_INPUT' in router._queues
    assert 'Q_AUDIT_OUTPUT' in router._queues
    assert 'Q_RESPONSE_SINK' in router._queues
    assert 'Q_DONE' in router._queues
    assert 'Q_ERROR' in router._queues

    # 验证队列优先级
    audit_input_queue = router._queues['Q_AUDIT_INPUT']
    assert audit_input_queue is not None

    print(f"✓ 强制性队列创建成功: {list(router._queues.keys())}")


@pytest.mark.asyncio
async def test_inject_input_with_audit():
    """测试带审计的消息注入"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    # 创建测试消息
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 注入消息（默认启用审计）
    success = await router.inject_input(impulse, enable_audit=True)

    # 验证消息被路由到 Q_AUDIT_INPUT
    assert 'Q_AUDIT_INPUT' in impulse.routing_history
    assert impulse.action_intent == 'Q_AUDIT_INPUT'
    assert impulse.metadata.get('original_action_intent') == 'Q_PROCESS_INPUT'

    print("✓ 消息已正确路由到 Q_AUDIT_INPUT")


@pytest.mark.asyncio
async def test_inject_input_without_audit():
    """测试不启用审计的消息注入"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    # 创建测试消息
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 注入消息（不启用审计）
    success = await router.inject_input(impulse, enable_audit=False)

    # 验证消息直接路由到目标队列（不经过审计）
    assert 'Q_AUDIT_INPUT' not in impulse.routing_history
    assert impulse.action_intent == 'Q_PROCESS_INPUT'

    print("✓ 消息已绕过审计直接路由（警告：不推荐）")


@pytest.mark.asyncio
async def test_route_from_audit_input():
    """测试从 Q_AUDIT_INPUT 路由"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    # 创建已经过 Q_AUDIT_INPUT 的消息
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_AUDIT_INPUT",
        source_agent="test_agent"
    )
    impulse.add_to_history("Q_AUDIT_INPUT")
    impulse.metadata['original_action_intent'] = 'Q_PROCESS_INPUT'

    # 从审计输入队列路由
    success = await router.route_from_audit_input(impulse)

    # 验证消息被路由到 Q_AUDIT_OUTPUT
    assert 'Q_AUDIT_INPUT' in impulse.routing_history
    assert impulse.action_intent == 'Q_AUDIT_OUTPUT'
    assert impulse.metadata.get('audit_input_passed') is True

    print("✓ 消息已从 Q_AUDIT_INPUT 路由到 Q_AUDIT_OUTPUT")


@pytest.mark.asyncio
async def test_route_from_audit_input_security_check():
    """测试 Q_AUDIT_INPUT 的安全验证"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    # 创建未经过 Q_AUDIT_INPUT 的消息（应该失败）
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 尝试路由（应该失败）
    success = await router.route_from_audit_input(impulse)

    # 验证路由失败
    assert success is False
    assert "Q_AUDIT_INPUT" not in impulse.routing_history

    print("✓ 安全验证正确拒绝了未经过 Q_AUDIT_INPUT 的消息")


@pytest.mark.asyncio
async def test_route_from_audit_output():
    """测试从 Q_AUDIT_OUTPUT 路由"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    # 创建已经过 Q_AUDIT_INPUT 和 Q_AUDIT_OUTPUT 的消息
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_AUDIT_OUTPUT",
        source_agent="test_agent"
    )
    impulse.add_to_history("Q_AUDIT_INPUT")
    impulse.add_to_history("Q_AUDIT_OUTPUT")
    impulse.metadata['original_action_intent'] = 'Q_PROCESS_INPUT'

    # 从审计输出队列路由
    success = await router.route_from_audit_output(impulse)

    # 验证消息恢复到原始目标
    assert 'Q_AUDIT_INPUT' in impulse.routing_history
    assert 'Q_AUDIT_OUTPUT' in impulse.routing_history
    assert impulse.action_intent == 'Q_PROCESS_INPUT'  # 恢复原始目标
    assert impulse.metadata.get('audit_output_passed') is True

    print("✓ 消息已从 Q_AUDIT_OUTPUT 恢复到原始目标队列")


@pytest.mark.asyncio
async def test_route_from_audit_output_security_check():
    """测试 Q_AUDIT_OUTPUT 的安全验证"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    # 创建只经过 Q_AUDIT_INPUT 但未经过 Q_AUDIT_OUTPUT 的消息
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_AUDIT_OUTPUT",
        source_agent="test_agent"
    )
    impulse.add_to_history("Q_AUDIT_INPUT")
    impulse.metadata['original_action_intent'] = 'Q_PROCESS_INPUT'

    # 尝试路由（应该失败）
    success = await router.route_from_audit_output(impulse)

    # 验证路由失败
    assert success is False
    assert "Q_AUDIT_OUTPUT" not in impulse.routing_history

    print("✓ 安全验证正确拒绝了未经过 Q_AUDIT_OUTPUT 的消息")


@pytest.mark.asyncio
async def test_audit_flow_integration():
    """测试完整的审计流程集成"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    # 创建原始消息
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 步骤1: 注入消息（应该路由到 Q_AUDIT_INPUT）
    success1 = await router.inject_input(impulse, enable_audit=True)
    assert success1 is True
    assert impulse.action_intent == 'Q_AUDIT_INPUT'
    assert 'Q_AUDIT_INPUT' in impulse.routing_history

    # 步骤2: 从 Q_AUDIT_INPUT 路由（应该路由到 Q_AUDIT_OUTPUT）
    success2 = await router.route_from_audit_input(impulse)
    assert success2 is True
    assert impulse.action_intent == 'Q_AUDIT_OUTPUT'
    assert 'Q_AUDIT_OUTPUT' in impulse.routing_history

    # 步骤3: 从 Q_AUDIT_OUTPUT 路由（应该恢复到原始目标）
    success3 = await router.route_from_audit_output(impulse)
    assert success3 is True
    assert impulse.action_intent == 'Q_PROCESS_INPUT'

    print("✓ 完整的审计流程集成测试通过")


@pytest.mark.asyncio
async def test_perform_input_audit_default():
    """测试默认输入审计逻辑（应该总是通过）"""
    router = AsyncNeuralSomaRouter("test_router")

    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 执行输入审计
    audit_passed = await router._perform_input_audit(impulse)

    # 默认实现应该总是通过
    assert audit_passed is True

    print("✓ 默认输入审计逻辑测试通过")


@pytest.mark.asyncio
async def test_perform_output_audit_default():
    """测试默认输出审计逻辑（应该总是通过）"""
    router = AsyncNeuralSomaRouter("test_router")

    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 执行输出审计
    audit_passed = await router._perform_output_audit(impulse)

    # 默认实现应该总是通过
    assert audit_passed is True

    print("✓ 默认输出审计逻辑测试通过")


@pytest.mark.asyncio
async def test_audit_metadata_preservation():
    """测试审计元数据保留"""
    router = AsyncNeuralSomaRouter("test_router")
    await router.activate()

    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    # 执行完整审计流程
    await router.inject_input(impulse, enable_audit=True)
    await router.route_from_audit_input(impulse)
    await router.route_from_audit_output(impulse)

    # 验证所有审计元数据都保留了
    assert 'original_action_intent' in impulse.metadata
    assert 'audit_input_passed' in impulse.metadata
    assert 'audit_input_timestamp' in impulse.metadata
    assert 'audit_output_passed' in impulse.metadata
    assert 'audit_output_timestamp' in impulse.metadata
    assert 'queue_timestamp' in impulse.metadata

    print("✓ 审计元数据保留测试通过")


@pytest.mark.asyncio
async def test_mandatory_queues_configuration():
    """测试强制性队列配置"""
    router = AsyncNeuralSomaRouter("test_router")

    # 验证 MANDATORY_QUEUES 配置
    assert 'Q_AUDIT_INPUT' in router.MANDATORY_QUEUES
    assert 'Q_AUDIT_OUTPUT' in router.MANDATORY_QUEUES
    assert 'Q_RESPONSE_SINK' in router.MANDATORY_QUEUES
    assert 'Q_DONE' in router.MANDATORY_QUEUES
    assert 'Q_ERROR' in router.MANDATORY_QUEUES

    # 验证优先级配置
    assert router.MANDATORY_QUEUES['Q_AUDIT_INPUT']['priority'] == QueuePriority.HIGH
    assert router.MANDATORY_QUEUES['Q_AUDIT_OUTPUT']['priority'] == QueuePriority.HIGH
    assert router.MANDATORY_QUEUES['Q_RESPONSE_SINK']['priority'] == QueuePriority.CRITICAL
    assert router.MANDATORY_QUEUES['Q_DONE']['priority'] == QueuePriority.NORMAL
    assert router.MANDATORY_QUEUES['Q_ERROR']['priority'] == QueuePriority.CRITICAL

    print("✓ 强制性队列配置测试通过")


@pytest.mark.asyncio
async def test_security_validation_for_sink():
    """测试 SINK 队列的安全验证"""
    router = AsyncNeuralSomaRouter("test_router")

    # 测试未授权的源尝试路由到 Q_AUDIT_OUTPUT
    impulse = NeuralImpulse(
        content="Test message",
        action_intent="Q_AUDIT_OUTPUT",
        source_agent="UnauthorizedAgent"
    )

    # 验证应该失败
    is_valid = await router._validate_sink_security(impulse)
    assert is_valid is False

    # 测试授权的源
    impulse.source_agent = "SecurityAuditor"
    is_valid = await router._validate_sink_security(impulse)
    assert is_valid is True

    print("✓ SINK 队列安全验证测试通过")

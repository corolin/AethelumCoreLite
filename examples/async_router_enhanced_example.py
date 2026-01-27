"""
AsyncNeuralSomaRouter 增强功能示例

演示新增的安全审计功能：
- Q_AUDIT_INPUT 和 Q_RESPONSE_SINK 队列
- Q_AUDIT_INPUT → Q_AUDIT_OUTPUT 强制审计流程
- 消息流安全验证
"""

import asyncio
import logging
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.message import NeuralImpulse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_mandatory_queues():
    """示例1：强制性队列创建"""
    print("\n" + "="*60)
    print("示例1：强制性队列创建")
    print("="*60)

    router = AsyncNeuralSomaRouter("mandatory_queues_example")

    # 激活路由器（自动创建所有强制性队列）
    await router.activate()

    print("\n强制性队列:")
    for queue_name, config in router.MANDATORY_QUEUES.items():
        priority = config['priority']
        description = config['description']
        exists = queue_name in router._queues
        status = "✓" if exists else "✗"
        print(f"  {status} {queue_name:20} - {description} (优先级: {priority.name})")

    print(f"\n总计: {len(router._queues)} 个队列已创建")


async def example_audit_flow():
    """示例2：完整的审计流程"""
    print("\n" + "="*60)
    print("示例2：完整的审计流程")
    print("="*60)

    router = AsyncNeuralSomaRouter("audit_flow_example")
    await router.activate()

    # 创建原始消息
    impulse = NeuralImpulse(
        content="Hello, World!",
        action_intent="Q_PROCESS_INPUT",
        source_agent="example_agent"
    )

    print("\n原始消息:")
    print(f"  内容: {impulse.get_text_content()}")
    print(f"  目标队列: {impulse.action_intent}")
    print(f"  路由历史: {impulse.routing_history}")

    # 步骤1: 注入消息（自动路由到 Q_AUDIT_INPUT）
    print("\n[步骤1] 注入消息到 Q_AUDIT_INPUT...")
    success1 = await router.inject_input(impulse, enable_audit=True)
    print(f"  成功: {success1}")
    print(f"  当前目标: {impulse.action_intent}")
    print(f"  路由历史: {impulse.routing_history}")
    print(f"  原始目标已保存: {impulse.metadata.get('original_action_intent')}")

    # 步骤2: 从 Q_AUDIT_INPUT 路由到 Q_AUDIT_OUTPUT
    print("\n[步骤2] 从 Q_AUDIT_INPUT 路由到 Q_AUDIT_OUTPUT...")
    success2 = await router.route_from_audit_input(impulse)
    print(f"  成功: {success2}")
    print(f"  当前目标: {impulse.action_intent}")
    print(f"  路由历史: {impulse.routing_history}")
    print(f"  输入审计通过: {impulse.metadata.get('audit_input_passed')}")

    # 步骤3: 从 Q_AUDIT_OUTPUT 恢复到原始目标
    print("\n[步骤3] 从 Q_AUDIT_OUTPUT 恢复到原始目标...")
    success3 = await router.route_from_audit_output(impulse)
    print(f"  成功: {success3}")
    print(f"  最终目标: {impulse.action_intent}")
    print(f"  完整路由历史: {impulse.routing_history}")
    print(f"  输出审计通过: {impulse.metadata.get('audit_output_passed')}")

    print("\n审计元数据:")
    for key, value in impulse.metadata.items():
        if 'audit' in key or 'timestamp' in key or 'original' in key:
            print(f"  {key}: {value}")


async def example_security_validation():
    """示例3：安全验证"""
    print("\n" + "="*60)
    print("示例3：安全验证")
    print("="*60)

    router = AsyncNeuralSomaRouter("security_example")
    await router.activate()

    # 场景1: 未授权的 Agent 尝试路由到 Q_AUDIT_OUTPUT
    print("\n场景1: 未授权访问 Q_AUDIT_OUTPUT")
    impulse1 = NeuralImpulse(
        content="Unauthorized message",
        action_intent="Q_AUDIT_OUTPUT",
        source_agent="MaliciousAgent"
    )

    is_valid1 = await router._validate_sink_security(impulse1)
    print(f"  Agent: {impulse1.source_agent}")
    print(f"  目标队列: {impulse1.action_intent}")
    print(f"  验证结果: {'通过 ✓' if is_valid1 else '拒绝 ✗'}")

    # 场景2: 授权的 Agent 路由到 Q_AUDIT_OUTPUT
    print("\n场景2: 授权访问 Q_AUDIT_OUTPUT")
    impulse2 = NeuralImpulse(
        content="Authorized message",
        action_intent="Q_AUDIT_OUTPUT",
        source_agent="SecurityAuditor"
    )

    is_valid2 = await router._validate_sink_security(impulse2)
    print(f"  Agent: {impulse2.source_agent}")
    print(f"  目标队列: {impulse2.action_intent}")
    print(f"  验证结果: {'通过 ✓' if is_valid2 else '拒绝 ✗'}")

    # 场景3: 尝试绕过 Q_AUDIT_INPUT 直接路由
    print("\n场景3: 尝试绕过输入审计")
    impulse3 = NeuralImpulse(
        content="Bypass attempt",
        action_intent="Q_AUDIT_OUTPUT",
        source_agent="test_agent"
    )

    success3 = await router.route_from_audit_input(impulse3)
    print(f"  消息是否经过 Q_AUDIT_INPUT: {'Q_AUDIT_INPUT' in impulse3.routing_history}")
    print(f"  路由结果: {'成功 ✓' if success3 else '失败 ✗'}")


async def example_audit_bypass():
    """示例4：审计绕过（不推荐）"""
    print("\n" + "="*60)
    print("示例4：审计绕过（不推荐，仅用于演示）")
    print("="*60)

    router = AsyncNeuralSomaRouter("bypass_example")
    await router.activate()

    impulse = NeuralImpulse(
        content="Direct message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    print("\n警告: 绕过审计违反安全设计！")
    print("生产环境应该始终启用审计 (enable_audit=True)")

    # 不启用审计
    success = await router.inject_input(impulse, enable_audit=False)

    print(f"\n消息已绕过 Q_AUDIT_INPUT")
    print(f"  目标队列: {impulse.action_intent}")
    print(f"  路由历史: {impulse.routing_history}")
    print(f"  结果: {'成功' if success else '失败'}")
    print("\n⚠️  警告: 这种做法不推荐，可能带来安全风险！")


async def example_custom_audit_logic():
    """示例5：自定义审计逻辑"""
    print("\n" + "="*60)
    print("示例5：自定义审计逻辑")
    print("="*60)

    # 创建自定义 Router 子类
    class CustomAuditRouter(AsyncNeuralSomaRouter):
        """自定义审计逻辑的路由器"""

        async def _perform_input_audit(self, impulse):
            """自定义输入审计：检测敏感词"""
            content = impulse.get_text_content().lower()

            # 检测敏感词
            sensitive_words = ['secret', 'password', 'confidential']
            if any(word in content for word in sensitive_words):
                print(f"  [输入审计] 检测到敏感词，拒绝消息")
                return False

            print(f"  [输入审计] 消息通过检查")
            return True

        async def _perform_output_audit(self, impulse):
            """自定义输出审计：检测个人信息"""
            content = impulse.get_text_content().lower()

            # 检测个人信息
            personal_info_patterns = ['ssn', 'credit card', 'social security']
            if any(pattern in content for word in personal_info_patterns for pattern in [word]):
                print(f"  [输出审计] 检测到个人信息，拒绝消息")
                return False

            print(f"  [输出审计] 消息通过检查")
            return True

    router = CustomAuditRouter("custom_audit_example")
    await router.activate()

    # 测试1: 正常消息
    print("\n测试1: 正常消息")
    impulse1 = NeuralImpulse(
        content="Hello, how are you?",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )
    audit_result1 = await router._perform_input_audit(impulse1)
    print(f"  输入审计结果: {'通过 ✓' if audit_result1 else '拒绝 ✗'}")

    # 测试2: 包含敏感词的消息
    print("\n测试2: 包含敏感词的消息")
    impulse2 = NeuralImpulse(
        content="This is a secret message",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )
    audit_result2 = await router._perform_input_audit(impulse2)
    print(f"  输入审计结果: {'通过 ✓' if audit_result2 else '拒绝 ✗'}")

    # 测试3: 包含个人信息
    impulse3 = NeuralImpulse(
        content="My SSN is 123-45-6789",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )
    audit_result3 = await router._perform_output_audit(impulse3)
    print(f"  输出审计结果: {'通过 ✓' if audit_result3 else '拒绝 ✗'}")


async def example_complete_workflow():
    """示例6：完整的审计工作流（模拟）"""
    print("\n" + "="*60)
    print("示例6：完整的审计工作流")
    print("="*60)

    router = AsyncNeuralSomaRouter("workflow_example")
    await router.activate()

    # 创建多个消息
    messages = [
        "Hello, World!",
        "How are you?",
        "Good morning!",
        "Have a nice day!"
    ]

    print(f"\n处理 {len(messages)} 条消息...")

    for i, content in enumerate(messages, 1):
        print(f"\n--- 消息 {i} ---")

        impulse = NeuralImpulse(
            content=content,
            action_intent="Q_PROCESS_INPUT",
            source_agent=f"agent_{i}"
        )

        print(f"原始消息: {content}")

        # 步骤1: 注入到审计系统
        await router.inject_input(impulse, enable_audit=True)
        print(f"  → Q_AUDIT_INPUT")

        # 步骤2: 输入审计
        await router.route_from_audit_input(impulse)
        print(f"  → Q_AUDIT_OUTPUT (输入审计: {'通过' if impulse.metadata.get('audit_input_passed') else '失败'})")

        # 步骤3: 输出审计并路由到最终目标
        await router.route_from_audit_output(impulse)
        print(f"  → {impulse.action_intent} (输出审计: {'通过' if impulse.metadata.get('audit_output_passed') else '失败'})")

        print(f"  完整路由: {' → '.join(impulse.routing_history)}")

    print("\n✓ 所有消息处理完成")


async def example_router_with_workers():
    """示例7：Router 与 Worker 集成"""
    print("\n" + "="*60)
    print("示例7：Router 与 Worker 集成")
    print("="*60)

    router = AsyncNeuralSomaRouter("integration_example")

    # 激活路由器
    await router.activate()

    # 创建审计队列的 Worker
    audit_input_queue = router._queues['Q_AUDIT_INPUT']
    audit_output_queue = router._queues['Q_AUDIT_OUTPUT']

    # 创建审计 Worker
    async def audit_input_handler(impulse, source_queue):
        """输入审计处理器"""
        print(f"  [审计输入] 处理消息: {impulse.get_text_content()[:30]}...")
        # 调用路由器的审计方法
        return await router.route_from_audit_input(impulse)

    async def audit_output_handler(impulse, source_queue):
        """输出审计处理器"""
        print(f"  [审计输出] 处理消息: {impulse.get_text_content()[:30]}...")
        # 调用路由器的审计方法
        return await router.route_from_audit_output(impulse)

    # 注册处理器
    router.register_hook("Q_AUDIT_INPUT", audit_input_handler)
    router.register_hook("Q_AUDIT_OUTPUT", audit_output_handler)

    print("\n已创建和配置:")
    print(f"  队列: {len(router._queues)} 个")
    print(f"  审计输入处理器: ✓")
    print(f"  审计输出处理器: ✓")

    # 注入测试消息
    impulse = NeuralImpulse(
        content="Test message for worker integration",
        action_intent="Q_PROCESS_INPUT",
        source_agent="test_agent"
    )

    print("\n注入测试消息...")
    await router.inject_input(impulse, enable_audit=True)

    print(f"\n消息路由状态:")
    print(f"  当前目标: {impulse.action_intent}")
    print(f"  路由历史: {' → '.join(impulse.routing_history)}")


async def main():
    """运行所有示例"""
    print("\n" + "="*60)
    print("AsyncNeuralSomaRouter 增强功能演示")
    print("="*60)

    try:
        await example_mandatory_queues()
        await example_audit_flow()
        await example_security_validation()
        await example_audit_bypass()
        await example_custom_audit_logic()
        await example_complete_workflow()
        await example_router_with_workers()

        print("\n" + "="*60)
        print("所有示例运行完成！")
        print("="*60)

    except Exception as e:
        logger.error(f"示例运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())

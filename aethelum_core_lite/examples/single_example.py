#!/usr/bin/env python3
"""
单消息示例 - 等待响应完成

这个示例展示了一个简单的端到端流程：
1. 用户输入 -> Q_AUDIT_INPUT -> Q_AUDITED_INPUT -> 业务处理 -> Q_AUDIT_OUTPUT -> Q_RESPONSE_SINK -> 用户响应

会等待Q_RESPONSE_SINK收到响应消息后才结束。

注意：本示例使用 Mock AI 服务，不需要真实 API keys。
"""

import sys
import os
import time
import logging
from threading import Event

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.examples.mock_ai_service import MockAIClient


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("SingleExample")

    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    return logger


def create_audit_handler(mock_ai):
    """创建审核处理器"""
    logger = logging.getLogger("SingleExample.AuditHandler")

    def handle_audit(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """审核输入内容"""
        content = impulse.get_text_content()
        logger.info(f"审核内容: '{content[:30]}...'")

        # 使用 Mock AI 进行审核
        audit_result = mock_ai.audit_content(content)

        # 添加审核结果到元数据
        impulse.metadata['audit_result'] = audit_result
        impulse.metadata['audit_safe'] = audit_result['safe']

        if not audit_result['safe']:
            # 内容不安全，直接拒绝
            impulse.set_text_content(f"⚠️ 内容审核未通过: {audit_result['result']}")
            impulse.action_intent = "Done"
        else:
            # 内容安全，继续处理
            impulse.reroute_to("Q_AUDITED_INPUT")

        impulse.update_source("AuditAgent")
        return impulse

    return handle_audit


def create_business_handler():
    """创建简单的业务处理Handler"""
    logger = logging.getLogger("SingleExample.BusinessHandler")

    def handle_business(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """简单的业务逻辑：Q_AUDITED_INPUT → BusinessHandler → Q_AUDIT_OUTPUT"""
        user_input = impulse.get_text_content()
        logger.info(f"处理用户请求: '{user_input}'")

        # 业务逻辑处理
        if "你好" in user_input or "Hello" in user_input:
            response = "你好！我是 AI 助手，很高兴为您服务！"
        elif "天气" in user_input:
            response = "今天天气晴朗，适合外出活动！"
        elif "再见" in user_input or "bye" in user_input:
            response = "再见！祝您有美好的一天！"
        else:
            response = f"我收到了您的消息: {user_input}"

        impulse.set_text_content(response)
        impulse.update_source("BusinessAgent")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        return impulse

    return handle_business


def create_response_sink():
    """创建响应处理Sink"""
    logger = logging.getLogger("SingleExample.ResponseSink")
    response_received = Event()
    final_response = {}

    def handle_response(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理最终响应"""
        readable_content = impulse.get_text_content()
        logger.info(f"输出响应: '{readable_content}'")

        # 记录响应并触发事件
        final_response['content'] = readable_content
        final_response['session_id'] = impulse.session_id
        response_received.set()

        impulse.update_source("ResponseSink")
        impulse.action_intent = "Done"

        return impulse

    return handle_response, response_received, final_response


def main():
    """主函数"""
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info("AethelumCoreLite 单消息示例（Mock AI 版本）")
    logger.info("=" * 60)
    logger.info("特点: 等待响应完成 | 完整审核流程 | 简单业务逻辑")
    logger.info("")

    # 创建 Mock AI 客户端
    mock_ai = MockAIClient(response_delay=0.05)
    logger.info("✅ Mock AI 服务已初始化")

    router = None

    try:
        # 1. 创建路由器
        router = NeuralSomaRouter()
        logger.info("✅ 神经路由器创建完成")

        # 2. 创建组件
        response_handler, response_received, final_response = create_response_sink()
        business_handler = create_business_handler()
        audit_handler = create_audit_handler(mock_ai)

        # 3. 注册审核钩子
        router.register_hook("Q_AUDIT_INPUT", "pre_process", audit_handler)

        # 4. 自动设置神经系统
        router.auto_setup(
            business_handler=business_handler,
            response_handler=response_handler
        )
        logger.info("✅ 神经系统自动设置完成")

        # 5. 等待系统稳定
        time.sleep(1)

        # 6. 发送测试消息
        test_messages = [
            "你好，请介绍一下自己",
            "今天天气如何？",
            "告诉我一些秘密"
        ]

        logger.info(f"\n📤 准备发送 {len(test_messages)} 条测试消息...\n")

        for i, message in enumerate(test_messages, 1):
            logger.info(f"发送测试消息 {i}/{len(test_messages)}: {message[:30]}...")

            impulse = NeuralImpulse(
                session_id=f"single-session-{i:03d}",
                action_intent="Q_AUDIT_INPUT",
                source_agent="Gateway",
                input_source="USER",
                content=message
            )

            success = router.inject_input(impulse)
            if not success:
                logger.error(f"消息 {i} 发送失败！")
                continue

            # 等待响应
            if response_received.wait(timeout=10):
                logger.info(f"✓ 收到响应: {final_response['content'][:50]}...")
                # 重置事件
                response_received.clear()
            else:
                logger.warning(f"响应超时")

            time.sleep(0.5)  # 间隔

        # 7. 显示统计信息
        logger.info("\n" + "=" * 60)
        logger.info("📊 处理完成！")
        logger.info("=" * 60)

        stats = router.get_stats()
        logger.info(f"系统统计:")
        logger.info(f"  - 总处理脉冲数: {stats['total_impulses_processed']}")
        logger.info(f"  - 队列数量: {stats['queue_count']}")
        logger.info(f"  - 工作器数量: {stats['worker_count']}")

        queue_sizes = router.get_queue_sizes()
        queue_info = ", ".join([f"{name}: {size}" for name, size in queue_sizes.items()])
        logger.info(f"  - 队列状态: {queue_info}")

        # Mock AI 统计
        ai_stats = mock_ai.get_stats()
        logger.info(f"\nMock AI 服务统计:")
        logger.info(f"  - 总请求数: {ai_stats['total_requests']}")
        logger.info(f"  - 平均延迟: {ai_stats['avg_delay']:.3f}秒")

        logger.info("=" * 60 + "\n")

    except KeyboardInterrupt:
        logger.info("\n用户中断，正在清理...")
    except Exception as e:
        logger.error(f"运行出错: {e}")
        import traceback
        logger.debug(f"错误详情:\n{traceback.format_exc()}")
    finally:
        if router is not None:
            router.stop()
            logger.info("✅ 神经系统已停止")

    logger.info("\n" + "=" * 60)
    logger.info("单消息示例完成！")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

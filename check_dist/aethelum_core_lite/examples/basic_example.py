#!/usr/bin/env python3
"""
基础示例 - AethelumCoreLite 核心功能演示

本示例展示框架的核心功能，使用 Mock AI 服务，无需配置真实 API keys。

演示功能：
1. 神经脉冲消息传递
2. 队列管理和 Worker 处理
3. 并发消息处理
4. 自动响应收集
5. 线程安全的数据访问

注意：本示例使用模拟 AI 服务，开箱即用，不需要真实 API keys。
"""

import sys
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.examples.mock_ai_service import MockAIClient


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("BasicExample")

    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    return logger


def create_business_handler(mock_ai):
    """
    创建业务处理 Handler

    使用 Mock AI 服务进行内容审核和处理。

    Args:
        mock_ai: MockAIClient 实例

    Returns:
        处理函数
    """
    logger = logging.getLogger("BasicExample.BusinessHandler")

    def handle_business(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """业务逻辑：审核后的输入 → 业务处理 → 输出"""
        user_input = impulse.get_text_content()
        logger.info(f"处理用户请求: '{user_input}'")

        # 使用 Mock AI 进行内容审核
        audit_result = mock_ai.audit_content(user_input)
        logger.info(f"审核结果: {audit_result['result']} (安全: {audit_result['safe']})")

        # 如果内容不安全，返回警告
        if not audit_result['safe']:
            response = f"⚠️ 内容审核未通过：{audit_result['result']}"
        else:
            # 内容安全，进行业务处理
            process_result = mock_ai.process_content(user_input)

            # 根据用户输入生成响应
            if "你好" in user_input or "Hello" in user_input:
                response = "你好！我是 AI 助手，很高兴为您服务！"
            elif "天气" in user_input:
                response = "今天天气晴朗，适合外出活动！"
            elif "功能" in user_input or "help" in user_input.lower():
                response = "我可以帮您进行内容审核、信息处理和智能对话。"
            elif "再见" in user_input or "bye" in user_input:
                response = "再见！祝您有美好的一天！"
            else:
                # 使用 Mock AI 的处理结果
                response = process_result['result']

        # 设置响应内容
        impulse.set_text_content(response)
        impulse.update_source("BusinessAgent")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        return impulse

    return handle_business


def create_response_sink():
    """
    创建响应处理 Sink（线程安全）

    Returns:
        (handler, events, responses) 元组
    """
    logger = logging.getLogger("BasicExample.ResponseSink")

    # 使用锁保护共享数据
    response_lock = threading.Lock()
    response_events = {}
    collected_responses = {}

    def handle_response(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理最终响应 - 线程安全收集"""
        readable_content = impulse.get_text_content()
        logger.info(f"收集响应: '{readable_content}' (会话ID: {impulse.session_id})")

        # 使用锁保护响应收集
        response_data = {
            'content': readable_content,
            'session_id': impulse.session_id,
            'timestamp': time.time()
        }

        with response_lock:
            collected_responses[impulse.session_id] = response_data

        # 触发对应的 Event
        if impulse.session_id in response_events:
            response_events[impulse.session_id].set()

        # 终止消息流
        impulse.action_intent = "Done"

        return impulse

    def get_collected_responses():
        """获取已收集的响应（线程安全）"""
        with response_lock:
            return collected_responses.copy()

    return handle_response, response_events, collected_responses, get_collected_responses


def main():
    """主函数"""
    logger = setup_logging()

    logger.info("=" * 60)
    logger.info("AethelumCoreLite 基础示例（Mock AI 版本）")
    logger.info("=" * 60)
    logger.info("特点: 开箱即用 | 无需 API keys | 线程安全 | 并发处理")

    # 创建 Mock AI 客户端
    mock_ai = MockAIClient(response_delay=0.05)
    logger.info("✅ Mock AI 服务已初始化")

    router = None

    try:
        # 1. 创建路由器
        router = NeuralSomaRouter()
        logger.info("✅ 神经路由器创建完成")

        # 2. 创建业务组件
        response_handler, response_events, _, get_responses = create_response_sink()
        business_handler = create_business_handler(mock_ai)

        # 3. 自动设置神经系统
        router.auto_setup(
            business_handler=business_handler,
            response_handler=response_handler
        )
        logger.info("✅ 神经系统自动设置完成")

        # 4. 等待系统稳定
        time.sleep(1)

        # 5. 准备测试消息
        test_messages = [
            "你好",
            "今天天气如何？",
            "请介绍一下你的功能",
            "再见"
        ]

        logger.info(f"\n📤 开始并发发送 {len(test_messages)} 条测试消息...\n")

        # 为每个 session 创建 Event 对象
        for i, message in enumerate(test_messages, 1):
            session_id = f"basic-session-{i:03d}"
            response_events[session_id] = threading.Event()

        # 记录发送时间
        send_start_time = time.time()

        # 使用 ThreadPoolExecutor 并发发送消息
        def send_message(message_data):
            """发送消息的函数"""
            index, message = message_data
            session_id = f"basic-session-{index:03d}"

            logger.info(f"[{index}/{len(test_messages)}] 发送: {message}")

            # 创建神经脉冲
            impulse = NeuralImpulse(
                session_id=session_id,
                action_intent="Q_AUDIT_INPUT",
                source_agent="Gateway",
                input_source="USER",
                content=message
            )

            success = router.inject_input(impulse)
            if success:
                logger.info(f"✓ 消息 {index} 发送成功")
            else:
                logger.error(f"✗ 消息 {index} 发送失败！")
            return success

        # 并发发送所有消息
        with ThreadPoolExecutor(max_workers=4) as executor:
            message_data = [(i, msg) for i, msg in enumerate(test_messages, 1)]
            futures = [executor.submit(send_message, data) for data in message_data]
            send_results = [future.result() for future in as_completed(futures)]

        successful_sends = sum(send_results)
        logger.info(f"\n消息发送完成: {successful_sends}/{len(test_messages)} 成功\n")

        # 6. 等待所有消息处理完成
        logger.info("⏳ 等待所有消息处理完成...")

        timeout = 30  # 30秒超时
        start_wait_time = time.time()

        while len(get_responses()) < successful_sends and (time.time() - start_wait_time) < timeout:
            time.sleep(0.1)

        end_time = time.time()
        total_time = end_time - send_start_time

        # 7. 显示处理结果
        logger.info("\n" + "=" * 60)
        logger.info(f"📊 处理完成！总耗时: {total_time:.2f}秒 | 平均每条: {total_time/successful_sends:.2f}秒")
        logger.info("=" * 60 + "\n")

        # 显示所有响应
        responses = get_responses()
        sorted_responses = sorted(responses.items(), key=lambda x: x[0])

        for session_id, response_data in sorted_responses:
            logger.info(f"📨 {session_id}: '{response_data['content']}'")

        # 8. 显示系统统计
        logger.info("\n" + "-" * 60)
        stats = router.get_stats()
        logger.info(f"系统统计:")
        logger.info(f"  - 总处理脉冲数: {stats['total_impulses_processed']}")
        logger.info(f"  - 队列数量: {stats['queue_count']}")
        logger.info(f"  - 工作器数量: {stats['worker_count']}")

        queue_sizes = router.get_queue_sizes()
        queue_info = ", ".join([f"{name}: {size}" for name, size in queue_sizes.items()])
        logger.info(f"  - 队列状态: {queue_info}")

        # 显示 Mock AI 统计
        ai_stats = mock_ai.get_stats()
        logger.info(f"\nMock AI 服务统计:")
        logger.info(f"  - 总请求数: {ai_stats['total_requests']}")
        logger.info(f"  - 平均延迟: {ai_stats['avg_delay']:.3f}秒")
        logger.info(f"  - 预估总时间: {ai_stats['estimated_total_time']:.2f}秒")
        logger.info("-" * 60 + "\n")

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
    logger.info("基础示例完成！")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

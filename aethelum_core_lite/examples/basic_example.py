#!/usr/bin/env python3
"""
基础示例 - 多线程并发处理演示

基于single_example.py模板改造的多线程版本，展示：
1. 并发消息处理能力
2. 多线程业务逻辑
3. 自动响应收集机制
4. 完整的内容安全审查流程
"""

import sys
import os
import time
import logging
from threading import Event
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("BasicExample")

    # 避免重复设置handler
    if not logger.handlers:
        # 默认使用INFO级别日志，减少输出信息
        # 如需查看更详细的调试信息，请将level修改为logging.DEBUG
        logging.basicConfig(
            level=logging.INFO,  # 使用INFO级别日志
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    return logger


def create_business_handler():
    """创建多线程业务处理Handler"""
    logger = logging.getLogger("BasicExample.BusinessHandler")

    def handle_business(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """多线程业务逻辑：Q_AUDITED_INPUT → BusinessHandler → Q_AUDIT_OUTPUT"""
        # 提取用户输入 - 使用简化的get_text_content
        user_input = impulse.get_text_content()
        logger.info(f"多线程处理用户请求: '{user_input}'")

        # 模拟一些处理时间（在实际应用中可能是LLM调用、数据库查询等）
        time.sleep(0.1)

        # 业务逻辑处理
        if "你好" in user_input or "Hello" in user_input:
            response = "你好！我是多线程AI助理，很高兴为您服务！"
        elif "天气" in user_input:
            response = "今天天气晴朗，适合外出活动！"
        elif "再见" in user_input or "bye" in user_input:
            response = "再见！祝您有美好的一天！"
        else:
            response = f"我收到了您的消息: {user_input}"

        # 设置响应并路由到输出审计
        # 直接设置response_content
        try:
            from aethelum_core_lite.core.protobuf_schema_pb2 import RequestContent
            request_content = impulse.get_protobuf_content(RequestContent)
            if isinstance(request_content, RequestContent):
                request_content.response_content = response
                logger.debug(f"多线程直接设置RequestContent.response_content: '{response}'")
            else:
                impulse.set_text_content(response)
        except Exception as e:
            logger.debug(f"无法直接设置RequestContent，使用set_text_content: {e}")
            impulse.set_text_content(response)

        impulse.update_source("BusinessAgent")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        return impulse

    return handle_business


def create_response_sink():
    """创建多线程响应处理Sink"""
    logger = logging.getLogger("BasicExample.ResponseSink")
    response_events = {}  # 存储每个session的Event对象
    collected_responses = {}  # 收集所有响应

    def handle_response(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理最终响应 - 多线程收集"""
        # 获取响应内容
        readable_content = impulse.get_text_content()
        logger.info(f"多线程收集响应: '{readable_content}' (会话ID: {impulse.session_id})")

        # 收集响应
        collected_responses[impulse.session_id] = {
            'content': readable_content,
            'session_id': impulse.session_id,
            'timestamp': time.time()
        }

        # 如果有对应的Event，触发它
        if impulse.session_id in response_events:
            response_events[impulse.session_id].set()

        # 终止消息流 - 设置为 Done
        impulse.action_intent = "Done"

        return impulse

    return handle_response, response_events, collected_responses


def main():
    """主函数"""
    logger = setup_logging()

    logger.info("🚀 启动基础示例 - 多线程版")
    logger.info("特点: 简化的多队列工作流 | 自动审计 | 多线程业务逻辑 | 自动响应收集")

    try:
        # 1. 获取配置并创建路由器
        try:
            from aethelum_core_lite.examples.config import OPENAI_CONFIG

            # 一键创建完整的神经系统（路由器会自动管理所有组件）
            router = NeuralSomaRouter(openai_config=OPENAI_CONFIG)
            logger.info(f"神经路由器创建完成 - 模型: {OPENAI_CONFIG.model}")
        except Exception as e:
            logger.error(f"路由器初始化失败: {e} - 请检查配置文件")
            return

        # 2. 创建多线程业务组件
        response_handler, response_events, collected_responses = create_response_sink()
        business_handler = create_business_handler()

        # 3. 一键自动设置整个神经系统（路由器已自动管理所有基础设施，包括内置Done处理器）
        router.auto_setup(
            business_handler=business_handler,
            response_handler=response_handler
        )
        logger.info("✅ 神经系统自动设置完成")

        # 4. 等待系统稳定
        time.sleep(1)

        # 5. 发送多条测试消息（多线程并发）
        test_messages = [
            "你好",
            "今天天气如何？",
            "请介绍一下自己",
            "再见"
        ]

        logger.info(f"开始并发发送 {len(test_messages)} 条测试消息...")

        # 为每个session创建Event对象
        for i, message in enumerate(test_messages, 1):
            session_id = f"basic-session-{i:03d}"
            response_events[session_id] = Event()

        # 记录发送时间
        send_start_time = time.time()

        # 使用ThreadPoolExecutor并发发送消息
        def send_message(message_data):
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
                logger.info(f"消息 {index} 发送成功")
            else:
                logger.error(f"消息 {index} 发送失败！")
            return success

        # 并发发送所有消息
        with ThreadPoolExecutor(max_workers=4) as executor:
            message_data = [(i, msg) for i, msg in enumerate(test_messages, 1)]
            futures = [executor.submit(send_message, data) for data in message_data]

            # 等待所有消息发送完成
            send_results = [future.result() for future in as_completed(futures)]

        successful_sends = sum(send_results)
        logger.info(f"消息发送完成: {successful_sends}/{len(test_messages)} 成功")

        # 6. 等待所有消息处理完成（多线程并发处理）
        logger.info("所有消息已发送，等待多线程处理完成...")

        # 等待所有响应被收集
        timeout = 30  # 30秒超时
        start_wait_time = time.time()

        while len(collected_responses) < successful_sends and (time.time() - start_wait_time) < timeout:
            time.sleep(0.1)  # 短暂等待

        end_time = time.time()
        total_time = end_time - send_start_time

        # 7. 显示处理结果
        logger.info(f"📊 处理完成！总耗时: {total_time:.2f}秒 | 平均每条消息: {total_time/successful_sends:.2f}秒")

        # 按会话ID排序显示响应
        sorted_responses = sorted(collected_responses.items(), key=lambda x: x[0])

        for session_id, response_data in sorted_responses:
            logger.info(f"响应 {session_id}: '{response_data['content']}'")

        # 8. 显示统计信息
        stats = router.get_stats()
        logger.info(f"系统统计 - 总处理脉冲数: {stats['total_impulses_processed']}, 队列数量: {stats['queue_count']}, 工作器数量: {stats['worker_count']}")

        queue_sizes = router.get_queue_sizes()
        queue_info = ", ".join([f"{name}: {size}" for name, size in queue_sizes.items()])
        logger.info(f"队列状态: {queue_info}")

    except KeyboardInterrupt:
        logger.info("用户中断，正在清理...")
    except Exception as e:
        logger.error(f"运行出错: {e}")
        import traceback
        logger.debug(f"错误详情: {traceback.format_exc()}")
    finally:
        if 'router' in locals():
            router.stop()
            logger.info("神经系统已停止")

    logger.info("基础示例完成！")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
批量处理示例 - AethelumCoreLite 批量消息处理演示

本示例展示如何高效处理大量消息，使用 Mock AI 服务。

演示功能：
1. 批量消息发送
2. 批量内容审核
3. 并发处理优化
4. 进度跟踪
5. 结果汇总

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
    logger = logging.getLogger("BatchExample")

    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    return logger


def create_batch_processor(mock_ai: MockAIClient, batch_size: int = 10):
    """
    创建批量处理器

    Args:
        mock_ai: Mock AI 客户端
        batch_size: 批量大小
    """
    logger = logging.getLogger("BatchProcessor")

    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """批量处理逻辑"""
        content = impulse.get_text_content()
        logger.info(f"处理: {content}")

        # 模拟批量处理
        audit_result = mock_ai.audit_content(content)

        response = f"✓ 已处理: {content} | 审核结果: {audit_result['result']}"

        impulse.set_text_content(response)
        impulse.update_source("BatchProcessor")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        return impulse

    return handle


def create_response_sink():
    """创建响应处理 Sink"""
    logger = logging.getLogger("ResponseSink")

    response_lock = threading.Lock()
    response_events = {}
    collected_responses = {}

    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理响应"""
        content = impulse.get_text_content()
        logger.debug(f"收集: {content}")

        response_data = {
            'content': content,
            'session_id': impulse.session_id,
            'timestamp': time.time()
        }

        with response_lock:
            collected_responses[impulse.session_id] = response_data

        if impulse.session_id in response_events:
            response_events[impulse.session_id].set()

        impulse.action_intent = "Done"
        return impulse

    def get_collected_responses():
        """获取已收集的响应"""
        with response_lock:
            return collected_responses.copy()

    return handle, response_events, collected_responses, get_collected_responses


def generate_test_messages(count: int) -> list:
    """生成测试消息"""
    templates = [
        "消息 {}: 请审核这段内容",
        "测试内容 {} 需要处理",
        "任务 {}：数据验证",
        "批量项 {} 等待处理",
        "请求 {} 需要响应"
    ]

    messages = []
    for i in range(1, count + 1):
        template = templates[i % len(templates)]
        messages.append(template.format(i))

    return messages


def main():
    """主函数"""
    logger = setup_logging()

    logger.info("=" * 70)
    logger.info("AethelumCoreLite 批量处理示例")
    logger.info("=" * 70)
    logger.info("批量处理特性:")
    logger.info("  • 高效批量消息发送")
    logger.info("  • 并发处理优化")
    logger.info("  • 实时进度跟踪")
    logger.info("  • 结果汇总统计")
    logger.info("=" * 70)

    # 配置
    BATCH_SIZE = 50
    CONCURRENT_WORKERS = 8

    mock_ai = MockAIClient(response_delay=0.02)
    logger.info(f"✅ Mock AI 服务已初始化 (批量处理: {BATCH_SIZE} 条消息)")

    router = None

    try:
        # 1. 创建路由器
        router = NeuralSomaRouter()
        logger.info("✅ 神经路由器创建完成")

        # 2. 创建处理器
        batch_processor = create_batch_processor(mock_ai)
        response_handler, response_events, _, get_responses = create_response_sink()

        # 3. 设置系统
        router.auto_setup(
            business_handler=batch_processor,
            response_handler=response_handler
        )

        # 调整 worker 数量
        router.adjust_workers("Q_AUDIT_INPUT", target_count=4)
        router.adjust_workers("Q_PROCESS_INPUT", target_count=4)

        logger.info(f"✅ 神经系统设置完成 (Worker数: {CONCURRENT_WORKERS})")

        # 4. 等待系统稳定
        time.sleep(1)

        # 5. 生成测试消息
        test_messages = generate_test_messages(BATCH_SIZE)

        logger.info(f"\n📤 准备批量发送 {len(test_messages)} 条消息...\n")

        # 为每个 session 创建 Event
        for i in range(len(test_messages)):
            session_id = f"batch-session-{i:04d}"
            response_events[session_id] = threading.Event()

        send_start_time = time.time()

        # 6. 批量并发发送
        processed_count = [0]
        error_count = [0]
        progress_lock = threading.Lock()

        def send_message(message_data):
            """发送单条消息"""
            index, message = message_data
            session_id = f"batch-session-{index:04d}"

            try:
                impulse = NeuralImpulse(
                    session_id=session_id,
                    action_intent="Q_AUDIT_INPUT",
                    source_agent="BatchGateway",
                    input_source="BATCH",
                    content=message
                )

                success = router.inject_input(impulse)

                with progress_lock:
                    if success:
                        processed_count[0] += 1
                        # 每 10 条打印一次进度
                        if processed_count[0] % 10 == 0:
                            logger.info(f"进度: {processed_count[0]}/{BATCH_SIZE} ({processed_count[0]*100//BATCH_SIZE}%)")
                    else:
                        error_count[0] += 1

                return success
            except Exception as e:
                logger.error(f"发送失败: {e}")
                with progress_lock:
                    error_count[0] += 1
                return False

        # 使用线程池并发发送
        with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
            message_data = [(i, msg) for i, msg in enumerate(test_messages, 1)]
            futures = [executor.submit(send_message, data) for data in message_data]
            results = [future.result() for future in as_completed(futures)]

        successful_sends = sum(results)
        total_time = time.time() - send_start_time

        logger.info(f"\n发送完成: {successful_sends}/{BATCH_SIZE} 成功 | 失败: {error_count[0]}")

        # 7. 等待所有消息处理完成
        logger.info("⏳ 等待批量处理完成...")
        timeout = 60  # 60秒超时
        start_wait_time = time.time()

        while len(get_responses()) < successful_sends and (time.time() - start_wait_time) < timeout:
            time.sleep(0.1)

        processing_time = time.time() - send_start_time

        # 8. 显示结果
        logger.info("\n" + "=" * 70)
        logger.info(f"📊 批量处理完成！")
        logger.info("=" * 70)
        logger.info(f"  总消息数: {BATCH_SIZE}")
        logger.info(f"  成功处理: {successful_sends}")
        logger.info(f"  失败数: {error_count[0]}")
        logger.info(f"  总耗时: {processing_time:.2f}秒")
        logger.info(f"  平均耗时: {processing_time/BATCH_SIZE:.3f}秒/条")
        logger.info(f"  吞吐量: {BATCH_SIZE/processing_time:.2f} 条/秒")
        logger.info("=" * 70 + "\n")

        # 显示部分响应（前5条和后5条）
        responses = get_responses()
        sorted_responses = sorted(responses.items(), key=lambda x: x[0])

        logger.info("响应示例（前5条）:")
        for session_id, response_data in sorted_responses[:5]:
            logger.info(f"  {session_id}: {response_data['content']}")

        if len(sorted_responses) > 5:
            logger.info(f"  ... (中间省略 {len(sorted_responses) - 10} 条) ...")

            logger.info("响应示例（后5条）:")
            for session_id, response_data in sorted_responses[-5:]:
                logger.info(f"  {session_id}: {response_data['content']}")

        # 系统统计
        stats = router.get_stats()
        logger.info(f"\n系统统计:")
        logger.info(f"  - 总处理脉冲数: {stats['total_impulses_processed']}")
        logger.info(f"  - 队列数: {stats['queue_count']}")
        logger.info(f"  - 工作器数: {stats['worker_count']}")

        # Mock AI 统计
        ai_stats = mock_ai.get_stats()
        logger.info(f"\nMock AI 服务统计:")
        logger.info(f"  - 总请求数: {ai_stats['total_requests']}")
        logger.info(f"  - 平均延迟: {ai_stats['avg_delay']:.3f}秒")
        logger.info(f"  - 预估总时间: {ai_stats['estimated_total_time']:.2f}秒")

        logger.info("\n" + "=" * 70)
        logger.info("✅ 批量处理示例完成！")
        logger.info("=" * 70)

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


if __name__ == "__main__":
    main()

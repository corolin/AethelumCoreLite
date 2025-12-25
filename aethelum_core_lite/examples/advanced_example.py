#!/usr/bin/env python3
"""
高级示例 - 多线程高级功能演示

基于single_example.py模板改造的高级多线程版本，展示：
1. 多个业务Agent协同工作
2. 并发LLM处理模拟
3. 性能监控和指标收集
4. RAG增强处理
5. 自动响应收集和排序
6. 高级并发特性
"""

import sys
import os
import time
import random
import logging
from threading import Event
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("AdvancedExample")

    # 避免重复设置handler
    if not logger.handlers:
        # 默认使用INFO级别日志，减少输出信息
        # 如需查看更详细的调试信息，请将level修改为logging.DEBUG
        logging.basicConfig(
            level=logging.INFO,  # 使用INFO级别日志
            format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] %(message)s'
        )

    return logger


class PerformanceMetrics:
    """性能指标收集器"""

    def __init__(self):
        self.metrics = {
            'total_processed': 0,
            'processing_times': [],
            'content_lengths': [],
            'llm_response_times': [],
            'rag_enhancements': 0
        }
        import threading
        self._lock = threading.Lock()

    def record_processing(self, processing_time: float, content_length: int, llm_time: float = 0):
        """记录处理指标"""
        with self._lock:
            self.metrics['total_processed'] += 1
            self.metrics['processing_times'].append(processing_time)
            self.metrics['content_lengths'].append(content_length)
            if llm_time > 0:
                self.metrics['llm_response_times'].append(llm_time)

    def record_rag_enhancement(self):
        """记录RAG增强"""
        with self._lock:
            self.metrics['rag_enhancements'] += 1

    def get_summary(self):
        """获取指标摘要"""
        with self._lock:
            if self.metrics['total_processed'] == 0:
                return {"total_processed": 0}

            return {
                'total_processed': self.metrics['total_processed'],
                'avg_processing_time': sum(self.metrics['processing_times']) / len(self.metrics['processing_times']),
                'avg_content_length': sum(self.metrics['content_lengths']) / len(self.metrics['content_lengths']),
                'avg_llm_time': sum(self.metrics['llm_response_times']) / len(self.metrics['llm_response_times']) if self.metrics['llm_response_times'] else 0,
                'rag_enhancements': self.metrics['rag_enhancements']
            }


def create_advanced_business_handler(metrics: PerformanceMetrics):
    """创建高级多线程业务处理Handler"""
    logger = logging.getLogger("AdvancedExample.BusinessHandler")

    def handle_business(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """高级多线程业务逻辑：Q_AUDITED_INPUT → BusinessHandler → Q_AUDIT_OUTPUT"""
        start_time = time.time()

        # 提取用户输入
        user_input = impulse.get_text_content()
        logger.info(f"高级多线程处理: '{user_input}'")

        # 模拟复杂处理时间（在实际应用中可能是LLM调用、数据库查询、RAG检索等）
        processing_delay = random.uniform(0.1, 0.5)
        time.sleep(processing_delay)

        # 随机RAG增强（30%概率）
        rag_enhanced = False
        if random.random() < 0.3:
            rag_enhanced = True
            metrics.record_rag_enhancement()
            # 模拟RAG增强内容
            knowledge = "[RAG增强: 基于知识库检索的相关信息]"
            user_input = f"{knowledge}\n\n用户输入: {user_input}"

        # 高级业务逻辑处理
        response_categories = {
            "问候": ["你好！我是高级AI助理，具备RAG增强能力！", "您好！很高兴为您提供智能服务！"],
            "技术问题": ["这是一个很好的技术问题。让我为您详细分析...", "根据我的知识库，我理解您的技术需求..."],
            "咨询": ["我已检索相关知识库，为您提供准确信息...", "基于我的分析，我建议如下方案..."],
            "默认": ["我理解您的需求，正在为您提供最佳回应...", "感谢您的提问，让我为您详细解答..."]
        }

        # 智能分类
        if any(word in user_input for word in ["你好", "hello", "hi", "您好"]):
            category = "问候"
        elif any(word in user_input for word in ["什么", "如何", "为什么", "技术", "问题"]):
            category = "技术问题"
        elif any(word in user_input for word in ["请", "帮", "咨询", "建议"]):
            category = "咨询"
        else:
            category = "默认"

        response = random.choice(response_categories[category])

        # 如果有RAG增强，添加标识
        if rag_enhanced:
            response += " [RAG增强]"

        # 设置响应
        try:
            from aethelum_core_lite.core.protobuf_schema_pb2 import RequestContent
            request_content = impulse.get_protobuf_content(RequestContent)
            if isinstance(request_content, RequestContent):
                request_content.response_content = response
                logger.debug(f"高级直接设置RequestContent.response_content: '{response}'")
            else:
                impulse.set_text_content(response)
        except Exception as e:
            logger.debug(f"无法直接设置RequestContent，使用set_text_content: {e}")
            impulse.set_text_content(response)

        # 添加高级元数据
        impulse.update_source("AdvancedBusinessAgent")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        # 记录处理指标
        processing_time = time.time() - start_time
        content_length = len(user_input)
        metrics.record_processing(processing_time, content_length, processing_delay)

        logger.debug(f"高级处理完成 - 类别: {category}, RAG: {rag_enhanced}, 耗时: {processing_time:.3f}s")

        return impulse

    return handle_business


def create_response_sink():
    """创建高级多线程响应处理Sink"""
    logger = logging.getLogger("AdvancedExample.ResponseSink")
    response_events = {}
    collected_responses = {}

    def handle_response(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理最终响应 - 高级多线程收集"""
        start_time = time.time()

        # 获取响应内容
        readable_content = impulse.get_text_content()
        logger.info(f"高级多线程收集响应: '{readable_content}' (会话ID: {impulse.session_id})")

        # 收集响应，包含详细元数据
        collected_responses[impulse.session_id] = {
            'content': readable_content,
            'session_id': impulse.session_id,
            'timestamp': time.time(),
            'processing_time': time.time() - start_time,
            'source_agent': impulse.source_agent,
            'metadata': impulse.metadata.copy()
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
    import threading

    logger.info("🚀 启动高级示例 - 多线程高级版")
    logger.info("特点: 多Agent协同 | RAG增强 | 性能监控 | 自动响应收集 | 高级并发特性")

    try:
        # 1. 获取配置并创建路由器
        try:
            from aethelum_core_lite.examples.config import ZHIPU_CONFIG

            # 一键创建完整的神经系统
            router = NeuralSomaRouter()
            logger.info("神经路由器创建完成 - 使用智谱AI客户端")
        except Exception as e:
            logger.error(f"路由器初始化失败: {e} - 请检查配置文件")
            return

        # 2. 创建性能指标收集器
        metrics = PerformanceMetrics()

        # 3. 创建高级业务组件
        response_handler, response_events, collected_responses = create_response_sink()
        business_handler = create_advanced_business_handler(metrics)

        # 4. 一键自动设置整个神经系统
        router.auto_setup(
            business_handler=business_handler,
            response_handler=response_handler
        )
        logger.info("✅ 神经系统自动设置完成")

        # 5. 等待系统稳定
        time.sleep(1)

        # 6. 准备高级测试消息（包含不同类型）
        test_messages = [
            "你好，我想了解一下AI助理的能力",
            "什么是AethelumCoreLite系统架构？",
            "请帮我分析一下这个技术问题",
            "给我一些建议，如何提高开发效率",
            "RAG技术在AI系统中的作用是什么？",
            "多线程并发处理的优势有哪些？",
            "再见，谢谢您的帮助"
        ]

        logger.info(f"开始高级并发测试 - {len(test_messages)} 条多样化消息")

        # 为每个session创建Event对象
        for i, message in enumerate(test_messages, 1):
            session_id = f"advanced-session-{i:03d}"
            response_events[session_id] = Event()

        # 记录测试开始时间
        test_start_time = time.time()

        # 高级并发发送函数 - 使用不同的worker池大小来模拟不同场景
        def send_message_concurrent(message_data):
            index, message = message_data
            session_id = f"advanced-session-{index:03d}"

            # 模拟用户发送间隔
            time.sleep(random.uniform(0.01, 0.1))

            logger.info(f"[{index}/{len(test_messages)}] 高级发送: {message[:30]}...")

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
                logger.debug(f"高级消息 {index} 发送成功")
            else:
                logger.error(f"高级消息 {index} 发送失败！")
            return success

        # 使用更大的线程池模拟高并发场景
        max_workers = min(8, len(test_messages))  # 动态调整工作线程数
        logger.info(f"使用 {max_workers} 个并发工作线程")

        # 高级并发发送所有消息
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            message_data = [(i, msg) for i, msg in enumerate(test_messages, 1)]
            futures = [executor.submit(send_message_concurrent, data) for data in message_data]

            # 等待所有消息发送完成
            send_results = [future.result() for future in as_completed(futures)]

        successful_sends = sum(send_results)
        logger.info(f"高级消息发送完成: {successful_sends}/{len(test_messages)} 成功")

        # 7. 等待所有消息处理完成（高级多线程并发处理）
        logger.info("所有消息已发送，等待高级多线程处理完成...")

        # 等待所有响应被收集，设置更长的超时时间
        timeout = 45  # 45秒超时（考虑RAG等复杂处理）
        start_wait_time = time.time()

        while len(collected_responses) < successful_sends and (time.time() - start_wait_time) < timeout:
            time.sleep(0.1)  # 短暂等待

        end_time = time.time()
        total_time = end_time - test_start_time

        # 8. 显示高级处理结果
        logger.info(f"📊 高级处理完成！总耗时: {total_time:.2f}秒 | 平均每条消息: {total_time/successful_sends:.2f}秒")
        logger.info(f"🚀 并发吞吐量: {successful_sends/total_time:.2f} 消息/秒")

        # 按会话ID排序显示响应
        sorted_responses = sorted(collected_responses.items(), key=lambda x: x[0])

        for session_id, response_data in sorted_responses:
            content = response_data['content']
            processing_time = response_data.get('processing_time', 0)
            source_agent = response_data.get('source_agent', 'Unknown')

            # 检测RAG增强
            rag_indicator = " [RAG]" if "[RAG增强]" in content else ""
            logger.info(f"高级响应 {session_id} ({source_agent}){rag_indicator}: '{content}'")

        # 9. 显示高级性能指标
        performance_summary = metrics.get_summary()
        logger.info(f"🎯 高级性能指标:")
        logger.info(f"  处理总数: {performance_summary['total_processed']}")
        logger.info(f"  平均处理时间: {performance_summary.get('avg_processing_time', 0):.3f}秒")
        logger.info(f"  平均内容长度: {performance_summary.get('avg_content_length', 0):.1f}字符")
        logger.info(f"  RAG增强次数: {performance_summary.get('rag_enhancements', 0)}")
        logger.info(f"  RAG增强率: {performance_summary.get('rag_enhancements', 0)/max(1, performance_summary['total_processed'])*100:.1f}%")

        # 10. 显示系统统计信息
        stats = router.get_stats()
        logger.info(f"系统统计 - 总处理脉冲数: {stats['total_impulses_processed']}, 队列数量: {stats['queue_count']}, 工作器数量: {stats['worker_count']}")

        queue_sizes = router.get_queue_sizes()
        queue_info = ", ".join([f"{name}: {size}" for name, size in queue_sizes.items()])
        logger.info(f"队列状态: {queue_info}")

        # 11. 高级特性展示
        logger.info("✨ 高级特性展示:")
        logger.info(f"  ✓ 多线程并发处理 ({max_workers} 工作线程)")
        logger.info(f"  ✓ RAG知识增强 ({performance_summary.get('rag_enhancements', 0)} 次)")
        logger.info(f"  ✓ 智能响应分类")
        logger.info(f"  ✓ 性能指标收集")
        logger.info(f"  ✓ 自动响应收集和排序")

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

    logger.info("高级示例完成！")


if __name__ == "__main__":
    main()
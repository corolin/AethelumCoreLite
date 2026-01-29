#!/usr/bin/env python3
"""
高级示例 - AethelumCoreLite 高级功能演示

本示例展示框架的高级特性，使用 Mock AI 服务。

演示功能：
1. 多个业务 Agent 协同工作
2. 优先级队列处理
3. 自定义 Hook 机制
4. 性能监控和指标收集
5. 错误处理和重试机制
6. 批量消息处理
7. 流式响应模拟

注意：本示例使用模拟 AI 服务，开箱即用，不需要真实 API keys。
"""

import sys
import os
import time
import random
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List
from enum import Enum

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.examples.mock_ai_service import MockAIClient


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("AdvancedExample")

    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] %(message)s'
        )

    return logger


class PerformanceMetrics:
    """性能指标收集器（线程安全）"""

    def __init__(self):
        self.metrics = {
            'total_processed': 0,
            'processing_times': [],
            'content_lengths': [],
            'agent_stats': {},
            'priority_stats': {1: 0, 5: 0, 9: 0}  # 高、中、低优先级
        }
        self._lock = threading.Lock()

    def record_processing(self, processing_time: float, content_length: int,
                         agent_name: str, priority: int):
        """记录处理指标"""
        with self._lock:
            self.metrics['total_processed'] += 1
            self.metrics['processing_times'].append(processing_time)
            self.metrics['content_lengths'].append(content_length)

            # Agent 统计
            if agent_name not in self.metrics['agent_stats']:
                self.metrics['agent_stats'][agent_name] = 0
            self.metrics['agent_stats'][agent_name] += 1

            # 优先级统计
            if priority in self.metrics['priority_stats']:
                self.metrics['priority_stats'][priority] += 1

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        with self._lock:
            if self.metrics['total_processed'] == 0:
                return {"total_processed": 0}

            return {
                'total_processed': self.metrics['total_processed'],
                'avg_processing_time': sum(self.metrics['processing_times']) / len(self.metrics['processing_times']),
                'min_processing_time': min(self.metrics['processing_times']),
                'max_processing_time': max(self.metrics['processing_times']),
                'avg_content_length': sum(self.metrics['content_lengths']) / len(self.metrics['content_lengths']),
                'agent_stats': self.metrics['agent_stats'].copy(),
                'priority_stats': self.metrics['priority_stats'].copy()
            }


# ==================== 自定义 Hook ====================

class TimingHook:
    """计时 Hook - 记录消息处理时间"""

    def __init__(self, metrics: PerformanceMetrics):
        self.metrics = metrics
        self.logger = logging.getLogger("TimingHook")
        self.start_times = {}
        self._lock = threading.Lock()

    def before_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理前记录时间"""
        with self._lock:
            self.start_times[impulse.session_id] = time.time()
        return impulse

    def after_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理后记录指标"""
        session_id = impulse.session_id

        with self._lock:
            if session_id in self.start_times:
                processing_time = time.time() - self.start_times[session_id]
                content_length = len(impulse.get_text_content())
                priority = impulse.metadata.get('priority', 5)

                # 从 metadata 中获取 agent 名称
                agent_name = impulse.metadata.get('processed_by', 'Unknown')

                self.metrics.record_processing(
                    processing_time, content_length, agent_name, priority
                )

                self.logger.debug(f"处理时间: {processing_time:.3f}s, Agent: {agent_name}")

                del self.start_times[session_id]

        return impulse


class AuditHook:
    """审核 Hook - 添加审核标记"""

    def __init__(self, mock_ai: MockAIClient):
        self.mock_ai = mock_ai
        self.logger = logging.getLogger("AuditHook")

    def before_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理前进行审核"""
        content = impulse.get_text_content()

        # 快速审核（模拟）
        audit_result = self.mock_ai.audit_content(content)

        # 添加审核元数据
        impulse.metadata['audit_result'] = audit_result
        impulse.metadata['audit_safe'] = audit_result['safe']

        self.logger.info(f"审核完成: {audit_result['safe']} - {audit_result['result']}")

        return impulse


# ==================== 业务 Agent ====================

def create_auditor_agent(mock_ai: MockAIClient):
    """创建审核 Agent"""
    logger = logging.getLogger("Agent.Auditor")

    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理审核"""
        content = impulse.get_text_content()
        logger.info(f"🔍 审核Agent处理: '{content[:30]}...'")

        # 进行审核
        audit_result = mock_ai.audit_content(content)

        # 记录元数据
        impulse.metadata['processed_by'] = 'AuditorAgent'
        impulse.metadata['audit_id'] = audit_result['request_id']
        impulse.metadata['audit_confidence'] = audit_result['confidence']

        # 如果不安全，直接返回警告
        if not audit_result['safe']:
            impulse.set_text_content(f"⚠️ 内容审核未通过: {audit_result['result']}")
            impulse.action_intent = "Done"  # 终止流程
        else:
            impulse.update_source("AuditorAgent")
            impulse.reroute_to("Q_PROCESS_INPUT")

        return impulse

    return handle


def create_processor_agent(mock_ai: MockAIClient):
    """创建处理 Agent"""
    logger = logging.getLogger("Agent.Processor")

    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理业务逻辑"""
        content = impulse.get_text_content()
        logger.info(f"⚙️ 处理Agent处理: '{content[:30]}...'")

        # 进行处理
        process_result = mock_ai.process_content(content)

        # 记录元数据
        impulse.metadata['processed_by'] = 'ProcessorAgent'
        impulse.metadata['process_id'] = process_result['request_id']

        # 更新内容
        impulse.set_text_content(process_result['result'])
        impulse.update_source("ProcessorAgent")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        return impulse

    return handle


def create_specialist_agent(agent_type: str, mock_ai: MockAIClient):
    """创建专业处理 Agent"""
    logger = logging.getLogger(f"Agent.{agent_type}")

    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """专业处理"""
        content = impulse.get_text_content()

        if agent_type == "Translation":
            logger.info(f"🌐 翻译Agent处理")
            response = f"[翻译] {content} → Translated: {content}"
        elif agent_type == "Summary":
            logger.info(f"📝 摘要Agent处理")
            response = f"[摘要] 原文: {content[:20]}... 摘要: 这是一个关于{content[:10]}的讨论"
        else:
            logger.info(f"🔧 {agent_type}Agent处理")
            response = f"[{agent_type}] 已处理: {content}"

        impulse.set_text_content(response)
        impulse.metadata['processed_by'] = f'{agent_type}Agent'
        impulse.update_source(f"{agent_type}Agent")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        return impulse

    return handle


# ==================== 响应 Sink ====================

def create_response_sink():
    """创建响应处理 Sink（线程安全）"""
    logger = logging.getLogger("ResponseSink")

    response_lock = threading.Lock()
    response_events = {}
    collected_responses = {}

    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理响应"""
        content = impulse.get_text_content()
        logger.info(f"✅ 收集响应: '{content[:50]}...'")

        response_data = {
            'content': content,
            'session_id': impulse.session_id,
            'timestamp': time.time(),
            'metadata': impulse.metadata.copy()
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


# ==================== 主函数 ====================

def main():
    """主函数"""
    logger = setup_logging()

    logger.info("=" * 70)
    logger.info("AethelumCoreLite 高级示例（Mock AI 版本）")
    logger.info("=" * 70)
    logger.info("高级特性:")
    logger.info("  • 多个业务 Agent 协同")
    logger.info("  • 优先级队列处理")
    logger.info("  • 自定义 Hook 机制")
    logger.info("  • 性能监控")
    logger.info("  • 错误处理")
    logger.info("=" * 70)

    # 创建 Mock AI 客户端
    mock_ai = MockAIClient(response_delay=0.03)
    logger.info("✅ Mock AI 服务已初始化")

    # 创建性能监控
    metrics = PerformanceMetrics()

    router = None

    try:
        # 1. 创建路由器
        router = NeuralSomaRouter()
        logger.info("✅ 神经路由器创建完成")

        # 2. 创建自定义 Hook
        timing_hook = TimingHook(metrics)
        audit_hook = AuditHook(mock_ai)

        # 3. 创建多个 Agent
        auditor_agent = create_auditor_agent(mock_ai)
        processor_agent = create_processor_agent(mock_ai)
        translation_agent = create_specialist_agent("Translation", mock_ai)
        summary_agent = create_specialist_agent("Summary", mock_ai)

        logger.info("✅ 业务 Agent 已创建")

        # 4. 创建响应 Sink
        response_handler, response_events, _, get_responses = create_response_sink()

        # 5. 设置路由器和 Hook
        # 注册 Hook
        router.register_hook("Q_AUDIT_INPUT", "pre_process", audit_hook.before_process)
        router.register_hook("Q_AUDIT_INPUT", "post_process", audit_hook.after_process)
        router.register_hook("Q_PROCESS_INPUT", "pre_process", timing_hook.before_process)
        router.register_hook("Q_PROCESS_INPUT", "post_process", timing_hook.after_process)

        # 自动设置（简化版）
        router.auto_setup(
            business_handler=processor_agent,
            response_handler=response_handler
        )

        logger.info("✅ 神经系统设置完成")

        # 6. 等待系统稳定
        time.sleep(1)

        # 7. 准备测试消息（不同优先级）
        test_cases = [
            # (消息, 优先级, 描述)
            ("紧急：系统故障，需要立即处理", 1, "高优先级-系统故障"),
            ("你好，请介绍一下你的功能", 5, "中优先级-功能咨询"),
            ("请帮我翻译这段文本", 5, "中优先级-翻译请求"),
            ("总结以下内容：...", 9, "低优先级-摘要任务"),
            ("普通消息1", 5, "中优先级-普通消息"),
            ("普通消息2", 5, "中优先级-普通消息"),
            ("批量处理任务A", 9, "低优先级-批量任务"),
            ("批量处理任务B", 9, "低优先级-批量任务"),
        ]

        logger.info(f"\n📤 准备发送 {len(test_cases)} 条测试消息（包含不同优先级）...\n")

        # 为每个 session 创建 Event
        for i, (_, priority, desc) in enumerate(test_cases, 1):
            session_id = f"adv-session-{i:03d}"
            response_events[session_id] = threading.Event()

        send_start_time = time.time()

        # 并发发送消息
        def send_message(test_data):
            """发送消息"""
            index, (message, priority, desc) = test_data
            session_id = f"adv-session-{index:03d}"

            logger.info(f"[{index}/{len(test_cases)}] 发送: {desc} (优先级: {priority})")

            impulse = NeuralImpulse(
                session_id=session_id,
                action_intent="Q_AUDIT_INPUT",
                source_agent="Gateway",
                input_source="USER",
                content=message
            )

            # 设置优先级
            impulse.metadata['priority'] = priority

            success = router.inject_input(impulse)
            return success, session_id

        with ThreadPoolExecutor(max_workers=4) as executor:
            test_data = [(i, tc) for i, tc in enumerate(test_cases, 1)]
            futures = [executor.submit(send_message, data) for data in test_data]
            results = [future.result() for future in as_completed(futures)]

        successful_sends = sum(1 for success, _ in results if success)
        logger.info(f"\n消息发送完成: {successful_sends}/{len(test_cases)} 成功\n")

        # 8. 等待处理完成
        logger.info("⏳ 等待所有消息处理完成...")
        timeout = 30
        start_wait_time = time.time()

        while len(get_responses()) < successful_sends and (time.time() - start_wait_time) < timeout:
            time.sleep(0.1)

        total_time = time.time() - send_start_time

        # 9. 显示结果
        logger.info("\n" + "=" * 70)
        logger.info(f"📊 处理完成！总耗时: {total_time:.2f}秒")
        logger.info("=" * 70 + "\n")

        # 显示响应
        responses = get_responses()
        sorted_responses = sorted(responses.items(), key=lambda x: x[0])

        for session_id, response_data in sorted_responses:
            priority = response_data['metadata'].get('priority', 5)
            priority_label = {1: "高", 5: "中", 9: "低"}.get(priority, "未知")
            logger.info(f"📨 {session_id} [优先级:{priority_label}]: '{response_data['content']}'")

        # 10. 显示性能统计
        logger.info("\n" + "-" * 70)
        logger.info("📈 性能指标统计:")
        logger.info("-" * 70)

        summary = metrics.get_summary()
        logger.info(f"  总处理数: {summary['total_processed']}")
        logger.info(f"  平均处理时间: {summary['avg_processing_time']:.3f}秒")
        logger.info(f"  最快处理: {summary['min_processing_time']:.3f}秒")
        logger.info(f"  最慢处理: {summary['max_processing_time']:.3f}秒")
        logger.info(f"  平均内容长度: {summary['avg_content_length']:.0f}字符")

        logger.info(f"\n  Agent 处理统计:")
        for agent, count in summary['agent_stats'].items():
            logger.info(f"    - {agent}: {count} 条")

        logger.info(f"\n  优先级处理统计:")
        for priority, count in summary['priority_stats'].items():
            priority_label = {1: "高", 5: "中", 9: "低"}.get(priority, str(priority))
            logger.info(f"    - {priority_label}优先级: {count} 条")

        # 系统统计
        stats = router.get_stats()
        logger.info(f"\n  系统统计:")
        logger.info(f"    - 总脉冲数: {stats['total_impulses_processed']}")
        logger.info(f"    - 队列数: {stats['queue_count']}")
        logger.info(f"    - 工作器数: {stats['worker_count']}")

        # Mock AI 统计
        ai_stats = mock_ai.get_stats()
        logger.info(f"\n  Mock AI 服务:")
        logger.info(f"    - 总请求数: {ai_stats['total_requests']}")
        logger.info(f"    - 平均延迟: {ai_stats['avg_delay']:.3f}秒")

        logger.info("-" * 70 + "\n")

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

    logger.info("\n" + "=" * 70)
    logger.info("高级示例完成！")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

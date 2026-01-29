#!/usr/bin/env python3
"""
内容安全审查示例 - 完整的审核流程实现

这是一个展示如何在AethelumCoreLite框架基础上实现自定义审核流程的完整示例。

演示功能：
1. 完整的审核流程实现（输入审核和输出审核）
2. 使用 Mock AI 进行内容安全审查
3. 自定义路由器类，实现审核钩子的设置
4. 审核队列(Q_AUDIT_INPUT、Q_AUDITED_INPUT、Q_AUDIT_OUTPUT等)的消息路由
5. 多线程并发审查处理
6. 智能违规类型识别和分类
7. 自动拒绝回复生成
8. 审查统计和性能分析
9. 测试用例，包括正常内容和违规内容的处理

注意：本示例使用 Mock AI 服务，不需要真实 API keys。
"""

import sys
import os
import time
import logging
import threading
from threading import Event
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.examples.mock_ai_service import MockAIClient


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("MoralAuditExample")

    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    return logger


class AuditStatistics:
    """多线程安全审查统计"""

    def __init__(self):
        self.stats = {
            'total_processed': 0,
            'normal_responses': 0,
            'input_rejections': 0,
            'output_rejections': 0,
            'violation_types': {},
            'processing_times': []
        }
        self._lock = threading.Lock()

    def record_normal_response(self, processing_time: float):
        """记录正常响应"""
        with self._lock:
            self.stats['total_processed'] += 1
            self.stats['normal_responses'] += 1
            self.stats['processing_times'].append(processing_time)

    def record_input_rejection(self, violation_type: str, processing_time: float):
        """记录输入拒绝"""
        with self._lock:
            self.stats['total_processed'] += 1
            self.stats['input_rejections'] += 1
            self.stats['processing_times'].append(processing_time)
            if violation_type not in self.stats['violation_types']:
                self.stats['violation_types'][violation_type] = {'input': 0, 'output': 0}
            self.stats['violation_types'][violation_type]['input'] += 1

    def record_output_rejection(self, violation_type: str, processing_time: float):
        """记录输出拒绝"""
        with self._lock:
            self.stats['total_processed'] += 1
            self.stats['output_rejections'] += 1
            self.stats['processing_times'].append(processing_time)
            if violation_type not in self.stats['violation_types']:
                self.stats['violation_types'][violation_type] = {'input': 0, 'output': 0}
            self.stats['violation_types'][violation_type]['output'] += 1

    def get_summary(self):
        """获取统计摘要"""
        with self._lock:
            if self.stats['total_processed'] == 0:
                return {"total_processed": 0}

            avg_processing_time = sum(self.stats['processing_times']) / len(self.stats['processing_times'])

            return {
                'total_processed': self.stats['total_processed'],
                'normal_responses': self.stats['normal_responses'],
                'input_rejections': self.stats['input_rejections'],
                'output_rejections': self.stats['output_rejections'],
                'avg_processing_time': avg_processing_time,
                'violation_types': self.stats['violation_types'],
                'rejection_rate': (self.stats['input_rejections'] + self.stats['output_rejections']) / self.stats['total_processed'] * 100
            }


def create_audit_handler(mock_ai, stats: AuditStatistics):
    """创建审核处理器"""
    logger = logging.getLogger("MoralAuditExample.AuditHandler")

    def handle_audit(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """审核内容"""
        start_time = time.time()
        content = impulse.get_text_content()

        # 判断是输入审核还是输出审核
        audit_type = "input" if source_queue == "Q_AUDIT_INPUT" else "output"

        # 使用 Mock AI 进行审核
        audit_result = mock_ai.audit_content(content)

        processing_time = time.time() - start_time

        # 记录审核结果
        if not audit_result['safe']:
            impulse.metadata['audit_failed'] = True
            impulse.metadata['audit_violation_type'] = audit_result['result']

            if audit_type == "input":
                impulse.metadata['audit_failed_at_input'] = True
                impulse.set_text_content(f"⚠️ 输入内容未通过审核: {audit_result['result']}")
                stats.record_input_rejection(audit_result['result'], processing_time)
            else:
                impulse.metadata['audit_failed_at_output'] = True
                impulse.set_text_content(f"⚠️ 输出内容未通过审核: {audit_result['result']}")
                stats.record_output_rejection(audit_result['result'], processing_time)

            # 终止流程
            impulse.action_intent = "Done"
        else:
            impulse.metadata['audit_passed'] = True
            impulse.metadata['audit_confidence'] = audit_result['confidence']

            # 继续到下一个队列
            if source_queue == "Q_AUDIT_INPUT":
                impulse.reroute_to("Q_AUDITED_INPUT")
            # 如果是 Q_AUDIT_OUTPUT，保持不变，继续到响应sink

        impulse.update_source("AuditAgent")
        return impulse

    return handle_audit


def create_business_handler(stats: AuditStatistics):
    """创建业务处理Handler"""
    logger = logging.getLogger("MoralAuditExample.BusinessHandler")

    def handle_business(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """业务逻辑处理"""
        start_time = time.time()
        user_input = impulse.get_text_content()

        logger.info(f"处理用户请求: '{user_input[:50]}...'")

        # 业务逻辑处理
        if "你好" in user_input or "Hello" in user_input:
            response = "你好！我是 AI 助手，很高兴为您服务！"
        elif "天气" in user_input:
            response = "今天天气晴朗，适合外出活动！"
        elif "帮助" in user_input:
            response = "我可以帮助您解答问题、提供建议和进行对话交流。"
        elif "AI" in user_input or "ai" in user_input:
            response = "AI是人工智能的简称，我在这里为您提供智能服务。"
        else:
            response = f"我收到了您的消息: {user_input}。让我为您提供帮助。"

        impulse.set_text_content(response)
        impulse.update_source("BusinessAgent")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        # 记录统计
        processing_time = time.time() - start_time
        stats.record_normal_response(processing_time)

        return impulse

    return handle_business


def create_response_sink(stats: AuditStatistics):
    """创建响应处理Sink"""
    logger = logging.getLogger("MoralAuditExample.ResponseSink")
    response_events = {}
    collected_responses = {}
    response_lock = threading.Lock()

    def handle_response(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理最终响应"""
        start_time = time.time()

        readable_content = impulse.get_text_content()
        logger.info(f"收集响应: '{readable_content[:50]}...' (会话ID: {impulse.session_id})")

        # 分析响应类型
        response_type = "正常"
        violation_type = None
        audit_source = None

        if impulse.metadata.get('audit_failed_at_input'):
            response_type = "输入拒绝"
            violation_type = impulse.metadata.get('audit_violation_type', 'Unknown')
            audit_source = "input_audit"
            stats.record_input_rejection(violation_type, time.time() - start_time)
        elif impulse.metadata.get('audit_failed_at_output'):
            response_type = "输出拒绝"
            violation_type = impulse.metadata.get('audit_violation_type', 'Unknown')
            audit_source = "output_audit"
            stats.record_output_rejection(violation_type, time.time() - start_time)

        # 线程安全地收集响应
        response_data = {
            'content': readable_content,
            'session_id': impulse.session_id,
            'response_type': response_type,
            'violation_type': violation_type,
            'audit_source': audit_source,
            'timestamp': time.time(),
            'source_agent': impulse.source_agent,
            'metadata': impulse.metadata.copy()
        }

        with response_lock:
            collected_responses[impulse.session_id] = response_data

        # 触发事件
        if impulse.session_id in response_events:
            response_events[impulse.session_id].set()

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

    logger.info("=" * 70)
    logger.info("AethelumCoreLite 内容安全审查示例（Mock AI 版本）")
    logger.info("=" * 70)
    logger.info("特点: 完整审核流程 | 自定义路由器 | 智能违规识别")
    logger.info("")

    # 创建 Mock AI 客户端
    mock_ai = MockAIClient(response_delay=0.03)
    logger.info("✅ Mock AI 服务已初始化")

    router = None

    try:
        # 1. 创建路由器
        router = NeuralSomaRouter()
        logger.info("✅ 神经路由器创建完成")

        # 2. 创建统计器和组件
        audit_stats = AuditStatistics()
        response_handler, response_events, _, get_responses = create_response_sink(audit_stats)
        business_handler = create_business_handler(audit_stats)
        audit_handler = create_audit_handler(mock_ai, audit_stats)

        # 3. 注册审核钩子
        router.register_hook("Q_AUDIT_INPUT", "pre_process", audit_handler)
        router.register_hook("Q_AUDIT_OUTPUT", "pre_process", audit_handler)
        logger.info("✅ 审核钩子已注册")

        # 4. 自动设置神经系统
        router.auto_setup(
            business_handler=business_handler,
            response_handler=response_handler
        )
        logger.info("✅ 神经系统自动设置完成")

        # 5. 等待系统稳定
        time.sleep(1)

        # 6. 准备测试用例
        test_cases = [
            # 正常测试用例
            {"content": "你好，我想了解一下AI的能力", "expected": "正常通过", "type": "normal"},
            {"content": "今天天气怎么样？", "expected": "正常通过", "type": "normal"},
            {"content": "请帮我介绍一下机器学习", "expected": "正常通过", "type": "normal"},
            {"content": "AI如何帮助人类发展？", "expected": "正常通过", "type": "normal"},

            # 模拟违规内容（通过长内容触发Mock AI的拒绝）
            {"content": "x" * 1001, "expected": "被拒绝", "type": "long_content"},
            {"content": "y" * 1500, "expected": "被拒绝", "type": "long_content"},
        ]

        logger.info(f"\n📤 准备发送 {len(test_cases)} 个测试用例...\n")

        # 为每个session创建Event对象
        for i, test_case in enumerate(test_cases, 1):
            session_id = f"audit-session-{i:03d}"
            response_events[session_id] = Event()

        test_start_time = time.time()

        # 并发发送测试用例
        def send_test(test_data):
            index, test_case = test_data
            session_id = f"audit-session-{index:03d}"

            test_type = test_case['type']
            content_preview = str(test_case['content'])[:30]

            logger.info(f"[{index}/{len(test_cases)}] [{test_type}] 测试: {content_preview}...")

            impulse = NeuralImpulse(
                session_id=session_id,
                action_intent="Q_AUDIT_INPUT",
                source_agent="Gateway",
                input_source="USER",
                content=test_case['content']
            )

            success = router.inject_input(impulse)
            if success:
                logger.info(f"[{index}/{len(test_cases)}] ✓ 发送成功")
            else:
                logger.error(f"[{index}/{len(test_cases)}] ✗ 发送失败")
            return success

        # 使用线程池并发发送
        with ThreadPoolExecutor(max_workers=4) as executor:
            test_data = [(i, case) for i, case in enumerate(test_cases, 1)]
            futures = [executor.submit(send_test, data) for data in test_data]
            send_results = [future.result() for future in as_completed(futures)]

        successful_sends = sum(send_results)
        logger.info(f"\n测试用例发送完成: {successful_sends}/{len(test_cases)} 成功\n")

        # 7. 等待处理完成
        logger.info("⏳ 等待审核处理完成...")
        timeout = 30
        start_wait_time = time.time()

        while len(get_responses()) < successful_sends and (time.time() - start_wait_time) < timeout:
            time.sleep(0.1)

        total_time = time.time() - test_start_time

        # 8. 显示结果
        logger.info("\n" + "=" * 70)
        logger.info(f"📊 审核处理完成！总耗时: {total_time:.2f}秒")
        logger.info("=" * 70 + "\n")

        responses = get_responses()
        sorted_responses = sorted(responses.items(), key=lambda x: x[0])

        normal_responses = []
        rejected_responses = []

        for session_id, response_data in sorted_responses:
            content = response_data['content']
            response_type = response_data.get('response_type', '未知')
            violation_type = response_data.get('violation_type')

            if response_type == "正常":
                normal_responses.append((session_id, content))
            else:
                rejected_responses.append((session_id, content, violation_type))

        # 显示正常响应
        if normal_responses:
            logger.info(f"✅ 正常通过响应 ({len(normal_responses)} 个):")
            for session_id, content in normal_responses:
                logger.info(f"  {session_id}: '{content[:60]}...'")

        # 显示拒绝响应
        if rejected_responses:
            logger.info(f"\n🚫 安全拒绝响应 ({len(rejected_responses)} 个):")
            for session_id, content, violation_type in rejected_responses:
                logger.info(f"  {session_id} [{violation_type}]: '{content[:60]}...'")

        # 9. 显示统计
        logger.info("\n" + "-" * 70)
        logger.info("📊 审核统计:")
        logger.info("-" * 70)

        audit_summary = audit_stats.get_summary()
        logger.info(f"  总处理数: {audit_summary['total_processed']}")
        logger.info(f"  正常响应: {audit_summary['normal_responses']}")
        logger.info(f"  输入拒绝: {audit_summary['input_rejections']}")
        logger.info(f"  输出拒绝: {audit_summary['output_rejections']}")
        logger.info(f"  拒绝率: {audit_summary.get('rejection_rate', 0):.1f}%")
        logger.info(f"  平均处理时间: {audit_summary.get('avg_processing_time', 0):.3f}秒")

        # 违规类型统计
        if audit_summary.get('violation_types'):
            logger.info(f"\n违规类型统计:")
            for violation_type, counts in audit_summary['violation_types'].items():
                total = counts['input'] + counts['output']
                logger.info(f"  {violation_type}: {total} 次 (输入:{counts['input']}, 输出:{counts['output']})")

        # 系统统计
        stats = router.get_stats()
        logger.info(f"\n系统统计:")
        logger.info(f"  - 总处理脉冲数: {stats['total_impulses_processed']}")
        logger.info(f"  - 队列数量: {stats['queue_count']}")
        logger.info(f"  - 工作器数量: {stats['worker_count']}")

        # Mock AI 统计
        ai_stats = mock_ai.get_stats()
        logger.info(f"\nMock AI 服务:")
        logger.info(f"  - 总请求数: {ai_stats['total_requests']}")
        logger.info(f"  - 平均延迟: {ai_stats['avg_delay']:.3f}秒")

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

    logger.info("=" * 70)
    logger.info("内容安全审查示例完成！")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
性能演示 - AethelumCoreLite 性能基准测试

本示例展示框架的性能特性，使用 Mock AI 服务。

演示功能：
1. 吞吐量测试
2. 延迟测试
3. 并发性能测试
4. 优先级队列性能测试
5. 持久化性能对比

注意：本示例使用模拟 AI 服务，开箱即用，不需要真实 API keys。
"""

import sys
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List
from dataclasses import dataclass

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.examples.mock_ai_service import MockAIClient


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("PerformanceDemo")

    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    return logger


@dataclass
class PerformanceResult:
    """性能测试结果"""
    test_name: str
    total_messages: int
    successful: int
    failed: int
    total_time: float
    throughput: float  # 消息/秒
    avg_latency: float  # 平均延迟
    min_latency: float
    max_latency: float
    p95_latency: float
    p99_latency: float


def create_simple_handler(mock_ai: MockAIClient):
    """创建简单处理器"""
    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        content = impulse.get_text_content()
        result = mock_ai.process_content(content)

        impulse.set_text_content(result['result'])
        impulse.update_source("Processor")
        impulse.reroute_to("Q_AUDIT_OUTPUT")

        return impulse

    return handle


def create_response_sink():
    """创建响应处理器"""
    response_lock = threading.Lock()
    response_events = {}
    collected_responses = {}
    latencies = []

    def handle(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        # 计算延迟
        if 'send_time' in impulse.metadata:
            latency = time.time() - impulse.metadata['send_time']
            with response_lock:
                latencies.append(latency)

        response_events[impulse.session_id].set()

        impulse.action_intent = "Done"
        return impulse

    def get_metrics():
        """获取指标"""
        with response_lock:
            return {
                'collected': len(collected_responses),
                'latencies': list(latencies)
            }

    return handle, response_events, get_metrics


def run_throughput_test(router: NeuralSomaRouter, mock_ai: MockAIClient,
                        message_count: int = 100, workers: int = 4) -> PerformanceResult:
    """运行吞吐量测试"""
    logger = logging.getLogger("ThroughputTest")

    logger.info(f"\n{'='*70}")
    logger.info(f"吞吐量测试 - {message_count} 条消息, {workers} 个 Worker")
    logger.info(f"{'='*70}\n")

    # 设置响应处理器
    response_handler, response_events, get_metrics = create_response_sink()
    business_handler = create_simple_handler(mock_ai)

    router.auto_setup(business_handler=business_handler, response_handler=response_handler)
    router.adjust_workers("Q_PROCESS_INPUT", target_count=workers)

    time.sleep(1)

    # 准备消息
    messages = [f"测试消息 {i}" for i in range(message_count)]

    # 发送并计时
    start_time = time.time()

    for i, message in enumerate(messages):
        session_id = f"throughput-{i:04d}"
        response_events[session_id] = threading.Event()

        impulse = NeuralImpulse(
            session_id=session_id,
            action_intent="Q_AUDIT_INPUT",
            source_agent="Test",
            content=message
        )

        impulse.metadata['send_time'] = time.time()
        router.inject_input(impulse)

    # 等待处理完成
    timeout = 60
    while get_metrics()['collected'] < message_count and (time.time() - start_time) < timeout:
        time.sleep(0.01)

    total_time = time.time() - start_time
    metrics = get_metrics()

    # 计算统计数据
    successful = metrics['collected']
    failed = message_count - successful
    throughput = message_count / total_time

    latencies = sorted(metrics['latencies'])
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = latencies[0]
        max_latency = latencies[-1]
        p95_latency = latencies[int(len(latencies) * 0.95)] if len(latencies) > 20 else max_latency
        p99_latency = latencies[int(len(latencies) * 0.99)] if len(latencies) > 20 else max_latency
    else:
        avg_latency = min_latency = max_latency = p95_latency = p99_latency = 0

    # 打印结果
    logger.info(f"✅ 测试完成！")
    logger.info(f"  总消息数: {message_count}")
    logger.info(f"  成功: {successful}")
    logger.info(f"  失败: {failed}")
    logger.info(f"  总耗时: {total_time:.2f}秒")
    logger.info(f"  吞吐量: {throughput:.2f} 消息/秒")
    logger.info(f"  平均延迟: {avg_latency*1000:.2f}ms")
    logger.info(f"  最小延迟: {min_latency*1000:.2f}ms")
    logger.info(f"  最大延迟: {max_latency*1000:.2f}ms")
    logger.info(f"  P95延迟: {p95_latency*1000:.2f}ms")
    logger.info(f"  P99延迟: {p99_latency*1000:.2f}ms")

    return PerformanceResult(
        test_name="吞吐量测试",
        total_messages=message_count,
        successful=successful,
        failed=failed,
        total_time=total_time,
        throughput=throughput,
        avg_latency=avg_latency,
        min_latency=min_latency,
        max_latency=max_latency,
        p95_latency=p95_latency,
        p99_latency=p99_latency
    )


def run_concurrent_test(router: NeuralSomaRouter, mock_ai: MockAIClient,
                         message_count: int = 100, max_workers: int = 8) -> PerformanceResult:
    """运行并发测试"""
    logger = logging.getLogger("ConcurrentTest")

    logger.info(f"\n{'='*70}")
    logger.info(f"并发测试 - {message_count} 条消息, {max_workers} 个并发线程")
    logger.info(f"{'='*70}\n")

    # 设置处理器
    response_handler, response_events, get_metrics = create_response_sink()
    business_handler = create_simple_handler(mock_ai)

    router.auto_setup(business_handler=business_handler, response_handler=response_handler)
    router.adjust_workers("Q_PROCESS_INPUT", target_count=max_workers)

    time.sleep(1)

    # 准备消息
    messages = [f"并发测试消息 {i}" for i in range(message_count)]

    start_time = time.time()

    def send_message(msg_data):
        index, message = msg_data
        session_id = f"concurrent-{i:04d}"
        response_events[session_id] = threading.Event()

        impulse = NeuralImpulse(
            session_id=session_id,
            action_intent="Q_AUDIT_INPUT",
            source_agent="Test",
            content=message
        )

        impulse.metadata['send_time'] = time.time()

        return router.inject_input(impulse)

    # 并发发送
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        msg_data = [(i, msg) for i, msg in enumerate(messages)]
        futures = [executor.submit(send_message, data) for data in msg_data]
        results = [f.result() for f in as_completed(futures)]

    successful = sum(results)
    failed = message_count - successful

    # 等待处理完成
    while get_metrics()['collected'] < successful and (time.time() - start_time) < 60:
        time.sleep(0.01)

    total_time = time.time() - start_time
    metrics = get_metrics()

    throughput = successful / total_time
    latencies = sorted(metrics['latencies'])
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    logger.info(f"✅ 测试完成！")
    logger.info(f"  总消息数: {message_count}")
    logger.info(f"  成功: {successful}")
    logger.info(f"  失败: {failed}")
    logger.info(f"  总耗时: {total_time:.2f}秒")
    logger.info(f"  吞吐量: {throughput:.2f} 消息/秒")
    logger.info(f"  平均延迟: {avg_latency*1000:.2f}ms")

    return PerformanceResult(
        test_name="并发测试",
        total_messages=message_count,
        successful=successful,
        failed=failed,
        total_time=total_time,
        throughput=throughput,
        avg_latency=avg_latency,
        min_latency=latencies[0] if latencies else 0,
        max_latency=latencies[-1] if latencies else 0,
        p95_latency=0,
        p99_latency=0
    )


def main():
    """主函数"""
    logger = setup_logging()

    logger.info("=" * 70)
    logger.info("AethelumCoreLite 性能演示")
    logger.info("=" * 70)
    logger.info("性能测试:")
    logger.info("  • 吞吐量测试")
    logger.info("  • 并发性能测试")
    logger.info("  • 延迟分析")
    logger.info("=" * 70)

    mock_ai = MockAIClient(response_delay=0.01)  # 更快的响应
    logger.info("✅ Mock AI 服务已初始化")

    router = None
    results = []

    try:
        # 1. 创建路由器
        router = NeuralSomaRouter()
        logger.info("✅ 神经路由器创建完成")

        # 2. 运行测试
        result1 = run_throughput_test(router, mock_ai, message_count=100, workers=4)
        results.append(result1)

        time.sleep(2)  # 冷却时间

        result2 = run_concurrent_test(router, mock_ai, message_count=100, max_workers=8)
        results.append(result2)

        # 3. 汇总结果
        logger.info(f"\n{'='*70}")
        logger.info("📊 性能测试汇总")
        logger.info(f"{'='*70}\n")

        for result in results:
            logger.info(f"{result.test_name}:")
            logger.info(f"  吞吐量: {result.throughput:.2f} 消息/秒")
            logger.info(f"  成功率: {result.successful/result.total_messages*100:.1f}%")
            logger.info(f"  平均延迟: {result.avg_latency*1000:.2f}ms")

        # Mock AI 统计
        ai_stats = mock_ai.get_stats()
        logger.info(f"\nMock AI 服务:")
        logger.info(f"  - 总请求数: {ai_stats['total_requests']}")
        logger.info(f"  - 平均延迟: {ai_stats['avg_delay']:.3f}秒")

        logger.info(f"\n{'='*70}")
        logger.info("✅ 性能演示完成！")
        logger.info(f"{'='*70}")

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

#!/usr/bin/env python3
"""
Aethelum Core Lite - 端到端性能压测

模拟真实场景：持续输入 + 持续消费 + 后台持久化
"""

import sys
import time
import threading
import statistics
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, '/opt/dev/aethelum-core-lite')

from aethelum_core_lite import NeuralImpulse, SynapticQueue


@dataclass
class E2EBenchmarkResult:
    """端到端测试结果"""
    test_name: str
    duration_seconds: float
    total_produced: int = 0
    total_consumed: int = 0
    throughput_produced: float = 0.0
    throughput_consumed: float = 0.0
    avg_queue_size: float = 0.0
    max_queue_size: int = 0
    persistence_count: int = 0
    avg_persistence_time_ms: float = 0.0
    producer_errors: int = 0
    consumer_errors: int = 0


class EndToEndBenchmark:
    """端到端性能压测"""

    def print_header(self, title: str):
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)

    def benchmark_continuous_flow(self,
                                duration_seconds: int = 10,
                                producers: int = 5,
                                consumers: int = 5,
                                messages_per_second: int = 1000,
                                enable_persistence: bool = True,
                                persistence_interval: float = 5.0) -> E2EBenchmarkResult:
        """
        持续输入+持续消费测试（最真实的场景）

        Args:
            duration_seconds: 测试持续时间
            producers: 生产者线程数
            consumers: 消费者线程数
            messages_per_second: 目标生产速率
            enable_persistence: 是否启用持久化
            persistence_interval: 持久化间隔（秒）

        Returns:
            E2EBenchmarkResult: 测试结果
        """
        self.print_header(f"🔄 端到端测试（{duration_seconds}秒，{producers}生产者，{consumers}消费者）")
        print(f"目标速率: {messages_per_second} msg/s")
        print(f"持久化: {'启用' if enable_persistence else '禁用'}")
        if enable_persistence:
            print(f"持久化间隔: {persistence_interval}秒")

        import os
        # 清理旧文件
        if enable_persistence and os.path.exists("/tmp/e2e_queue.json"):
            os.remove("/tmp/e2e_queue.json")

        queue = SynapticQueue(
            queue_id="e2e_benchmark",
            max_size=0,
            enable_persistence=enable_persistence,
            persistence_path="/tmp/e2e_queue.json",
            persistence_interval=persistence_interval
        )

        # 统计信息
        stats = {
            'produced': 0,
            'consumed': 0,
            'producer_errors': 0,
            'consumer_errors': 0,
            'queue_sizes': [],
            'persistence_times': [],
            'stop_event': threading.Event()
        }

        # 生产者线程
        def producer(worker_id: int):
            """生产者线程"""
            try:
                while not stats['stop_event'].is_set():
                    impulse = NeuralImpulse(
                        content=f"Worker {worker_id} - Message at {time.time()}",
                        action_intent="Q_PROCESS_INPUT"
                    )
                    success = queue.put(impulse, priority=5, block=True, timeout=1.0)
                    if success:
                        stats['produced'] += 1
                    else:
                        stats['producer_errors'] += 1
                        time.sleep(0.001)  # 短暂休眠后重试
            except Exception as e:
                stats['producer_errors'] += 1

        # 消费者线程
        def consumer(worker_id: int):
            """消费者线程"""
            try:
                while not stats['stop_event'].is_set():
                    impulse = queue.get(block=True, timeout=1.0)
                    if impulse is None:
                        continue

                    # 模拟处理消息（1ms 处理时间）
                    time.sleep(0.001)
                    stats['consumed'] += 1
            except Exception as e:
                stats['consumer_errors'] += 1

        # 启动生产者和消费者
        start_time = time.time()

        producer_threads = []
        for i in range(producers):
            t = threading.Thread(target=producer, args=(i,), daemon=True)
            t.start()
            producer_threads.append(t)

        consumer_threads = []
        for i in range(consumers):
            t = threading.Thread(target=consumer, args=(i,), daemon=True)
            t.start()
            consumer_threads.append(t)

        # 监控线程 - 定期打印状态
        def monitor():
            last_print_time = start_time
            while not stats['stop_event'].is_set():
                time.sleep(1.0)
                elapsed = time.time() - start_time
                current_queue_size = queue.size()

                stats['queue_sizes'].append(current_queue_size)

                if elapsed - last_print_time >= 2.0:  # 每2秒打印一次
                    produced_rate = stats['produced'] / elapsed
                    consumed_rate = stats['consumed'] / elapsed
                    print(f"[{elapsed:.1f}s] "
                          f"队列大小: {current_queue_size:,} | "
                          f"生产: {stats['produced']:,} ({produced_rate:,.1f} msg/s) | "
                          f"消费: {stats['consumed']:,} ({consumed_rate:,.1f} msg/s) | "
                          f"错误: P{stats['producer_errors']}+C{stats['consumer_errors']}")
                    last_print_time = elapsed

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

        # 运行指定时长
        print(f"\n开始测试，运行 {duration_seconds} 秒...")
        time.sleep(duration_seconds)

        # 停止所有线程
        stats['stop_event'].set()
        end_time = time.time()
        duration = end_time - start_time

        # 等待队列清空或超时
        print("\n等待队列清空（最多5秒）...")
        for _ in range(50):
            if queue.size() == 0:
                break
            time.sleep(0.1)

        # 关闭队列（触发最终持久化）
        if enable_persistence:
            print("\n触发最终持久化...")
            close_start = time.time()
            queue.close()
            close_end = time.time()
            close_time = close_end - close_start
            print(f"最终持久化耗时: {close_time*1000:.2f} ms")

            # 检查持久化文件
            if os.path.exists("/tmp/e2e_queue.json"):
                file_size = os.path.getsize("/tmp/e2e_queue.json")
                print(f"持久化文件大小: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")

        # 计算统计信息
        avg_queue_size = statistics.mean(stats['queue_sizes']) if stats['queue_sizes'] else 0
        max_queue_size = max(stats['queue_sizes']) if stats['queue_sizes'] else 0

        result = E2EBenchmarkResult(
            test_name=f"端到端测试（{duration_seconds}秒，{producers}生产者，{consumers}消费者）",
            duration_seconds=duration,
            total_produced=stats['produced'],
            total_consumed=stats['consumed'],
            throughput_produced=stats['produced'] / duration,
            throughput_consumed=stats['consumed'] / duration,
            avg_queue_size=avg_queue_size,
            max_queue_size=max_queue_size,
            persistence_count=0,
            avg_persistence_time_ms=0,
            producer_errors=stats['producer_errors'],
            consumer_errors=stats['consumer_errors'],
        )

        # 打印结果
        print(f"\n📊 测试结果")
        print("-" * 80)
        print(f"测试时长:           {duration:.2f} 秒")
        print(f"总生产数:           {stats['produced']:,}")
        print(f"总消费数:           {stats['consumed']:,}")
        print(f"生产吞吐量:         {result.throughput_produced:,.2f} msg/s")
        print(f"消费吞吐量:         {result.throughput_consumed:,.2f} msg/s")
        print(f"\n队列统计:")
        print(f"平均队列大小:       {result.avg_queue_size:.1f}")
        print(f"最大队列大小:       {result.max_queue_size:,}")
        print(f"\n错误统计:")
        print(f"生产者错误:         {result.producer_errors}")
        print(f"消费者错误:         {result.consumer_errors}")

        return result

    def benchmark_persistence_impact(self,
                                     duration_seconds: int = 15,
                                     persistence_interval: float = 5.0) -> Dict[str, Any]:
        """
        专门测试持久化对性能的影响

        Args:
            duration_seconds: 测试时长
            persistence_interval: 持久化间隔（秒）

        Returns:
            Dict: 详细的影响分析
        """
        self.print_header(f"💾 持久化影响深度分析（{duration_seconds}秒，间隔{persistence_interval}秒）")

        # 测试1: 不启用持久化
        print("\n【测试1】不启用持久化的基线性能...")
        result_no_persistence = self.benchmark_continuous_flow(
            duration_seconds=duration_seconds,
            producers=5,
            consumers=5,
            messages_per_second=5000,
            enable_persistence=False
        )

        # 测试2: 启用持久化
        print("\n【测试2】启用持久化的性能...")
        time.sleep(2)  # 短暂休息
        result_with_persistence = self.benchmark_continuous_flow(
            duration_seconds=duration_seconds,
            producers=5,
            consumers=5,
            messages_per_second=5000,
            enable_persistence=True,
            persistence_interval=persistence_interval
        )

        # 对比分析
        self.print_header("📊 持久化影响对比分析")

        print(f"\n{'指标':<20} {'无持久化':<15} {'有持久化':<15} {'影响':<10}")
        print("-" * 80)

        throughput_diff = result_no_persistence.throughput_produced - result_with_persistence.throughput_produced
        throughput_pct = (throughput_diff / result_no_persistence.throughput_produced) * 100

        print(f"{'生产吞吐量':<20} {result_no_persistence.throughput_produced:>13,.2f} msg/s "
              f"{result_with_persistence.throughput_produced:>13,.2f} msg/s "
              f"{'📉' if throughput_diff > 0 else '📈'} {abs(throughput_pct):.1f}%")

        print(f"\n{'消费吞吐量':<20} {result_no_persistence.throughput_consumed:>13,.2f} msg/s "
              f"{result_with_persistence.throughput_consumed:>13,.2f} msg/s "
              f"{'📉' if throughput_diff > 0 else '📈'} {abs(throughput_pct):.1f}%")

        print(f"\n{'平均队列大小':<20} {result_no_persistence.avg_queue_size:>13.1f} "
              f"{result_with_persistence.avg_queue_size:>13.1f} "
              f"{'=' if abs(result_no_persistence.avg_queue_size - result_with_persistence.avg_queue_size) < 1 else '≠'}")

        return {
            'no_persistence': result_no_persistence,
            'with_persistence': result_with_persistence,
            'throughput_diff': throughput_diff,
            'throughput_pct': throughput_pct
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Aethelum Core Lite - 端到端性能压测')
    parser.add_argument('--duration', type=int, default=10,
                       help='测试时长（秒）')
    parser.add_argument('--producers', type=int, default=5,
                       help='生产者线程数')
    parser.add_argument('--consumers', type=int, default=5,
                       help='消费者线程数')
    parser.add_argument('--rate', type=int, default=5000,
                       help='目标生产速率（msg/s）')
    parser.add_argument('--persistence-interval', type=float, default=5.0,
                       help='持久化间隔（秒）')
    parser.add_argument('--no-persistence', action='store_true',
                       help='禁用持久化测试')

    args = parser.parse_args()

    benchmark = EndToEndBenchmark()

    if args.no_persistence:
        # 只运行不启用持久化的测试
        benchmark.benchmark_continuous_flow(
            duration_seconds=args.duration,
            producers=args.producers,
            consumers=args.consumers,
            messages_per_second=args.rate,
            enable_persistence=False
        )
    else:
        # 运行完整的对比测试
        benchmark.benchmark_persistence_impact(
            duration_seconds=args.duration,
            persistence_interval=args.persistence_interval
        )


if __name__ == "__main__":
    main()

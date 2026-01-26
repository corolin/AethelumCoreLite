#!/usr/bin/env python3
"""
Aethelum Core Lite 性能压测脚本

用于测试和验证修复后的性能提升，包括：
- 基本吞吐量测试
- 持久化性能测试
- 延迟测试
- 并发测试
"""

import sys
import time
import threading
import statistics
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

# 添加项目路径
sys.path.insert(0, '/opt/dev/aethelum-core-lite')

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse, SynapticQueue


@dataclass
class BenchmarkResult:
    """测试结果"""
    test_name: str
    total_messages: int = 0
    duration_seconds: float = 0.0
    throughput_msg_per_sec: float = 0.0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    errors: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


class PerformanceBenchmark:
    """性能压测工具"""

    def __init__(self):
        self.results: List[BenchmarkResult] = []

    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)

    def print_result(self, result: BenchmarkResult):
        """打印测试结果"""
        print(f"\n📊 {result.test_name}")
        print("-" * 80)
        print(f"总消息数:     {result.total_messages:,}")
        print(f"耗时:         {result.duration_seconds:.2f} 秒")
        print(f"吞吐量:       {result.throughput_msg_per_sec:,.2f} msg/s")
        print(f"\n延迟统计:")
        print(f"  平均延迟:   {result.avg_latency_ms:.3f} ms")
        print(f"  最小延迟:   {result.min_latency_ms:.3f} ms")
        print(f"  最大延迟:   {result.max_latency_ms:.3f} ms")
        print(f"  P95 延迟:    {result.p95_latency_ms:.3f} ms")
        print(f"  P99 延迟:    {result.p99_latency_ms:.3f} ms")
        if result.errors > 0:
            print(f"错误数:       {result.errors}")
        if result.details:
            print(f"\n详细信息:")
            for key, value in result.details.items():
                print(f"  {key}: {value}")

    def benchmark_basic_throughput(self, num_messages: int = 10000) -> BenchmarkResult:
        """
        基本吞吐量测试（不启用持久化）

        Args:
            num_messages: 测试消息数量

        Returns:
            BenchmarkResult: 测试结果
        """
        self.print_header("🚀 基本吞吐量测试（不启用持久化）")

        queue = SynapticQueue(
            queue_id="benchmark",
            max_size=0,
            enable_persistence=False  # 不启用持久化
        )

        latencies = []
        errors = 0
        start_time = time.time()

        for i in range(num_messages):
            try:
                # 创建消息
                impulse = NeuralImpulse(
                    content=f"Test message {i}",
                    action_intent="Q_PROCESS_INPUT"
                )

                # 测量 put 延迟
                put_start = time.time()
                success = queue.put(impulse, priority=5, block=False)
                put_end = time.time()

                if success:
                    latencies.append((put_end - put_start) * 1000)  # 转换为毫秒
                else:
                    errors += 1

                # 每 1000 条消息打印进度
                if (i + 1) % 1000 == 0:
                    elapsed = time.time() - start_time
                    throughput = (i + 1) / elapsed
                    print(f"进度: {i+1:,}/{num_messages:,} ({(i+1)/num_messages*100:.1f}%) | "
                          f"当前吞吐量: {throughput:,.2f} msg/s")

            except Exception as e:
                errors += 1
                print(f"错误: {e}")

        end_time = time.time()
        duration = end_time - start_time

        # 计算统计数据
        result = BenchmarkResult(
            test_name="基本吞吐量测试（不启用持久化）",
            total_messages=num_messages,
            duration_seconds=duration,
            throughput_msg_per_sec=num_messages / duration,
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            p95_latency_ms=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
            p99_latency_ms=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
            errors=errors,
            details={
                "队列大小": queue.size(),
                "持久化": "关闭"
            }
        )

        self.results.append(result)
        self.print_result(result)
        return result

    def benchmark_persistence_throughput(self, num_messages: int = 10000,
                                         persistence_interval: float = 30.0) -> BenchmarkResult:
        """
        持久化吞吐量测试（启用持久化）

        Args:
            num_messages: 测试消息数量
            persistence_interval: 持久化间隔（秒）

        Returns:
            BenchmarkResult: 测试结果
        """
        self.print_header(f"💾 持久化吞吐量测试（间隔: {persistence_interval}秒）")

        queue = SynapticQueue(
            queue_id="benchmark_persistence",
            max_size=0,
            enable_persistence=True,
            persistence_path="/tmp/benchmark_queue.json",
            persistence_interval=persistence_interval
        )

        latencies = []
        errors = 0
        start_time = time.time()

        for i in range(num_messages):
            try:
                # 创建消息
                impulse = NeuralImpulse(
                    content=f"Test message {i}",
                    action_intent="Q_PROCESS_INPUT"
                )

                # 测量 put 延迟
                put_start = time.time()
                success = queue.put(impulse, priority=5, block=False)
                put_end = time.time()

                if success:
                    latencies.append((put_end - put_start) * 1000)
                else:
                    errors += 1

                # 每 1000 条消息打印进度
                if (i + 1) % 1000 == 0:
                    elapsed = time.time() - start_time
                    throughput = (i + 1) / elapsed
                    print(f"进度: {i+1:,}/{num_messages:,} ({(i+1)/num_messages*100:.1f}%) | "
                          f"当前吞吐量: {throughput:,.2f} msg/s")

            except Exception as e:
                errors += 1
                print(f"错误: {e}")

        end_time = time.time()
        duration = end_time - start_time

        # 关闭队列（触发最终持久化）
        queue.close()

        # 计算统计数据
        result = BenchmarkResult(
            test_name=f"持久化吞吐量测试（间隔: {persistence_interval}秒）",
            total_messages=num_messages,
            duration_seconds=duration,
            throughput_msg_per_sec=num_messages / duration,
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            p95_latency_ms=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
            p99_latency_ms=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
            errors=errors,
            details={
                "队列大小": queue.size(),
                "持久化间隔": f"{persistence_interval}秒"
            }
        )

        self.results.append(result)
        self.print_result(result)
        return result

    def benchmark_concurrent_producers(self, num_producers: int = 10,
                                       messages_per_producer: int = 1000) -> BenchmarkResult:
        """
        并发生产者测试

        Args:
            num_producers: 生产者线程数量
            messages_per_producer: 每个生产者发送的消息数

        Returns:
            BenchmarkResult: 测试结果
        """
        self.print_header(f"🔄 并发测试（{num_producers} 个生产者）")

        queue = SynapticQueue(
            queue_id="concurrent_benchmark",
            max_size=0,
            enable_persistence=False
        )

        errors = [0]
        latencies = []
        lock = threading.Lock()

        def producer(worker_id: int):
            """生产者线程"""
            worker_latencies = []
            for i in range(messages_per_producer):
                try:
                    impulse = NeuralImpulse(
                        content=f"Producer {worker_id} - Message {i}",
                        action_intent="Q_PROCESS_INPUT"
                    )

                    put_start = time.time()
                    success = queue.put(impulse, priority=5, block=True, timeout=5.0)
                    put_end = time.time()

                    if success:
                        worker_latencies.append((put_end - put_start) * 1000)
                    else:
                        errors[0] += 1

                except Exception as e:
                    errors[0] += 1

            with lock:
                latencies.extend(worker_latencies)

        # 创建并启动生产者线程
        start_time = time.time()
        threads = []
        for i in range(num_producers):
            t = threading.Thread(target=producer, args=(i,))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        end_time = time.time()
        duration = end_time - start_time
        total_messages = num_producers * messages_per_producer

        # 计算统计数据
        result = BenchmarkResult(
            test_name=f"并发测试（{num_producers} 个生产者）",
            total_messages=total_messages,
            duration_seconds=duration,
            throughput_msg_per_sec=total_messages / duration,
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            p95_latency_ms=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
            p99_latency_ms=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
            errors=errors[0],
            details={
                "生产者数量": num_producers,
                "每生产者消息数": messages_per_producer,
                "最终队列大小": queue.size()
            }
        )

        self.results.append(result)
        self.print_result(result)
        return result

    def benchmark_priority_queue(self, num_messages: int = 5000) -> BenchmarkResult:
        """
        优先级队列测试

        Args:
            num_messages: 测试消息数量

        Returns:
            BenchmarkResult: 测试结果
        """
        self.print_header("🎯 优先级队列测试")

        queue = SynapticQueue(
            queue_id="priority_benchmark",
            max_size=0,
            enable_persistence=False
        )

        errors = 0
        priorities = [1, 3, 5, 7, 9]  # 不同优先级
        start_time = time.time()

        # 发送不同优先级的消息
        for i in range(num_messages):
            try:
                priority = priorities[i % len(priorities)]
                impulse = NeuralImpulse(
                    content=f"Priority {priority} - Message {i}",
                    action_intent="Q_PROCESS_INPUT"
                )
                queue.put(impulse, priority=priority, block=False)

                if (i + 1) % 500 == 0:
                    print(f"进度: {i+1:,}/{num_messages:,}")

            except Exception as e:
                errors += 1

        end_time = time.time()
        duration = end_time - start_time

        # 验证优先级顺序
        retrieved_priorities = []
        while not queue.empty():
            try:
                impulse = queue.get(block=False, timeout=0.1)
                if impulse:
                    retrieved_priorities.append(impulse.metadata.get("priority", 5))
            except:
                break

        # 检查是否按优先级排序
        is_sorted = retrieved_priorities == sorted(retrieved_priorities)

        result = BenchmarkResult(
            test_name="优先级队列测试",
            total_messages=num_messages,
            duration_seconds=duration,
            throughput_msg_per_sec=num_messages / duration,
            avg_latency_ms=0,  # 不测量延迟
            min_latency_ms=0,
            max_latency_ms=0,
            p95_latency_ms=0,
            p99_latency_ms=0,
            errors=errors,
            details={
                "优先级排序正确": is_sorted,
                "检索消息数": len(retrieved_priorities),
                "优先级分布": {
                    1: retrieved_priorities.count(1),
                    3: retrieved_priorities.count(3),
                    5: retrieved_priorities.count(5),
                    7: retrieved_priorities.count(7),
                    9: retrieved_priorities.count(9)
                }
            }
        )

        self.results.append(result)
        self.print_result(result)
        return result

    def compare_before_after(self) -> None:
        """对比修复前后的性能"""
        self.print_header("📊 性能对比分析")

        print("\n预期性能提升：")
        print("-" * 80)
        print("指标                    修复前           修复后           提升")
        print("-" * 80)
        print("put() 延迟              50-200ms         <0.01ms         5,000-20,000x")
        print("吞吐量                  <100 msg/s       >10,000 msg/s    100x")
        print("CPU 占用                 100%             <5%             20x")
        print("\n实际测试结果：")
        print("-" * 80)

        # 显示之前测试的结果对比
        basic_results = [r for r in self.results if "基本" in r.test_name]
        persistence_results = [r for r in self.results if "持久化" in r.test_name]

        if basic_results and persistence_results:
            basic = basic_results[0]
            persistence = persistence_results[0]

            print(f"\n基本吞吐量:     {basic.throughput_msg_per_sec:,.2f} msg/s")
            print(f"持久化吞吐量:   {persistence.throughput_msg_per_sec:,.2f} msg/s")
            print(f"\n基本延迟:       {basic.avg_latency_ms:.3f} ms")
            print(f"持久化延迟:     {persistence.avg_latency_ms:.3f} ms")

            # 计算性能损失
            throughput_loss = (1 - persistence.throughput_msg_per_sec / basic.throughput_msg_per_sec) * 100
            print(f"\n持久化性能损失:  {throughput_loss:.2f}%")

    def generate_report(self) -> str:
        """生成测试报告"""
        report = []
        report.append("=" * 80)
        report.append("Aethelum Core Lite - 性能压测报告")
        report.append("=" * 80)
        report.append(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Python版本: {sys.version}")
        report.append("")

        for result in self.results:
            report.append(f"\n{result.test_name}")
            report.append("-" * 80)
            report.append(f"总消息数:       {result.total_messages:,}")
            report.append(f"耗时:           {result.duration_seconds:.2f} 秒")
            report.append(f"吞吐量:         {result.throughput_msg_per_sec:,.2f} msg/s")
            if result.avg_latency_ms > 0:
                report.append(f"平均延迟:       {result.avg_latency_ms:.3f} ms")
                report.append(f"P95 延迟:        {result.p95_latency_ms:.3f} ms")
                report.append(f"P99 延迟:        {result.p99_latency_ms:.3f} ms")
            if result.errors > 0:
                report.append(f"错误数:         {result.errors}")

        return "\n".join(report)

    def run_full_benchmark(self) -> None:
        """运行完整的性能测试套件"""
        print("\n" + "🎯" * 40)
        print("  Aethelum Core Lite - 性能压测套件")
        print("🎯" * 40)

        # 1. 基本吞吐量测试
        self.benchmark_basic_throughput(num_messages=10000)

        # 2. 持久化吞吐量测试
        self.benchmark_persistence_throughput(num_messages=10000, persistence_interval=30.0)

        # 3. 并发测试
        self.benchmark_concurrent_producers(num_producers=10, messages_per_producer=1000)

        # 4. 优先级队列测试
        self.benchmark_priority_queue(num_messages=5000)

        # 5. 性能对比
        self.compare_before_after()

        # 6. 生成报告
        report = self.generate_report()

        # 保存报告到文件
        report_path = "/opt/dev/aethelum-core-lite/performance_report.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"\n\n✅ 测试完成！报告已保存到: {report_path}")
        print("\n" + "=" * 80)
        print("🎉 性能压测套件执行完毕！")
        print("=" * 80)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Aethelum Core Lite 性能压测工具')
    parser.add_argument('--basic', action='store_true', help='仅运行基本吞吐量测试')
    parser.add_argument('--persistence', action='store_true', help='仅运行持久化测试')
    parser.add_argument('--concurrent', action='store_true', help='仅运行并发测试')
    parser.add_argument('--priority', action='store_true', help='仅运行优先级队列测试')
    parser.add_argument('--full', action='store_true', help='运行完整测试套件（默认）')

    args = parser.parse_args()

    benchmark = PerformanceBenchmark()

    if args.basic:
        benchmark.benchmark_basic_throughput()
    elif args.persistence:
        benchmark.benchmark_persistence_throughput()
    elif args.concurrent:
        benchmark.benchmark_concurrent_producers()
    elif args.priority:
        benchmark.benchmark_priority_queue()
    else:
        # 默认运行完整测试
        benchmark.run_full_benchmark()


if __name__ == "__main__":
    main()

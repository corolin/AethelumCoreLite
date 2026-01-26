"""
性能基准测试
测试并发安全修复前后的性能对比
"""
import time
import threading
import statistics
from aethelum_core_lite.core.queue import SynapticQueue
from aethelum_core_lite.core.worker import AxonWorker
from aethelum_core_lite.core.message import NeuralImpulse, MessagePriority


def create_text_impulse(content: str, priority: int = 1) -> NeuralImpulse:
    """辅助函数：创建文本类型的神经脉冲"""
    return NeuralImpulse(
        session_id=f"test-{time.time()}",
        action_intent="TEST",
        source_agent="Test",
        content=content,
        priority=MessagePriority.NORMAL if priority == 1 else MessagePriority.HIGH
    )


class TestPerformanceBenchmark:
    """性能基准测试"""

    def test_queue_throughput(self):
        """测试队列吞吐量：消息/秒"""
        queue = SynapticQueue(queue_id="test_queue", max_size=10000)
        num_messages = 10000

        # 测试 put 性能
        start_time = time.time()
        for i in range(num_messages):
            impulse = create_text_impulse(
                content=f"message-{i}",
                priority=1
            )
            queue.put(impulse, block=False)
        put_time = time.time() - start_time
        put_throughput = num_messages / put_time

        print(f"\nPut 性能:")
        print(f"  消息数量: {num_messages}")
        print(f"  耗时: {put_time:.3f} 秒")
        print(f"  吞吐量: {put_throughput:.0f} 消息/秒")

        # 测试 get 性能
        start_time = time.time()
        for _ in range(num_messages):
            impulse = queue.get(block=False, timeout=0.1)
        get_time = time.time() - start_time
        get_throughput = num_messages / get_time

        print(f"\nGet 性能:")
        print(f"  消息数量: {num_messages}")
        print(f"  耗时: {get_time:.3f} 秒")
        print(f"  吞吐量: {get_throughput:.0f} 消息/秒")

        # 性能基准：应该在 10000+ 消息/秒
        assert put_throughput > 5000, f"Put 吞吐量过低: {put_throughput:.0f}"
        assert get_throughput > 5000, f"Get 吞吐量过低: {get_throughput:.0f}"

    def test_concurrent_queue_performance(self):
        """测试并发队列性能"""
        queue = SynapticQueue(queue_id="test_queue", max_size=10000)
        num_producers = 10
        num_consumers = 10
        messages_per_producer = 1000

        put_times = []
        get_times = []

        def producer(worker_id):
            start = time.time()
            for i in range(messages_per_producer):
                impulse = create_text_impulse(
                    content=f"message-{worker_id}-{i}",
                    priority=1
                )
                queue.put(impulse, block=True)
            elapsed = time.time() - start
            put_times.append(elapsed)

        def consumer():
            start = time.time()
            received = 0
            while received < messages_per_producer:
                try:
                    impulse = queue.get(block=False, timeout=0.1)
                    if impulse:
                        received += 1
                except:
                    pass
            elapsed = time.time() - start
            get_times.append(elapsed)

        # 启动生产者和消费者
        start_time = time.time()

        producers = []
        for i in range(num_producers):
            t = threading.Thread(target=producer, args=(i,))
            producers.append(t)
            t.start()

        consumers = []
        for i in range(num_consumers):
            t = threading.Thread(target=consumer)
            consumers.append(t)
            t.start()

        # 等待完成
        for t in producers:
            t.join()
        for t in consumers:
            t.join()

        total_time = time.time() - start_time
        total_messages = num_producers * messages_per_producer

        print(f"\n并发队列性能:")
        print(f"  生产者: {num_producers}, 消费者: {num_consumers}")
        print(f"  总消息数: {total_messages}")
        print(f"  总耗时: {total_time:.3f} 秒")
        print(f"  平均 put 耗时: {statistics.mean(put_times):.3f} 秒")
        print(f"  平均 get 耗时: {statistics.mean(get_times):.3f} 秒")
        print(f"  整体吞吐量: {total_messages / total_time:.0f} 消息/秒")

        # 性能基准
        assert total_messages / total_time > 1000, "并发吞吐量过低"

    def test_worker_processing_performance(self):
        """测试 Worker 处理性能"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)

        worker = AxonWorker(
            worker_id="test_worker",
            queue=queue,
            processing_time=0.001  # 1ms 处理时间
        )
        worker.start()

        # 添加消息
        num_messages = 1000
        for i in range(num_messages):
            impulse = create_text_impulse(
                content=f"message-{i}",
                priority=1
            )
            queue.put(impulse, block=True)

        # 等待处理完成
        start_time = time.time()
        while queue.get_stats().queue_size > 0:
            time.sleep(0.01)
            if time.time() - start_time > 10:
                break

        processing_time = time.time() - start_time

        print(f"\nWorker 处理性能:")
        print(f"  消息数量: {num_messages}")
        print(f"  处理时间: {processing_time:.3f} 秒")
        print(f"  处理速率: {num_messages / processing_time:.0f} 消息/秒")

        stats = worker.get_stats()
        print(f"  成功处理: {stats.processed_messages}")
        print(f"  失败处理: {stats.failed_messages}")

        worker.stop()

        # 验证处理正确性
        assert stats.processed_messages > 0

    def test_lock_contention_overhead(self):
        """测试锁竞争开销"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)
        num_iterations = 1000

        # 测试单线程性能（无竞争）
        start_time = time.time()
        for i in range(num_iterations):
            impulse = create_text_impulse(
                content=f"message-{i}",
                priority=1
            )
            queue.put(impulse, block=False)
            queue.get(block=False, timeout=0.1)
        single_thread_time = time.time() - start_time

        # 测试多线程性能（有竞争）
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)
        num_threads = 10
        iterations_per_thread = 100

        def worker():
            for i in range(iterations_per_thread):
                impulse = create_text_impulse(
                    content=f"message-{i}",
                    priority=1
                )
                queue.put(impulse, block=True)
                try:
                    queue.get(block=False, timeout=0.1)
                except:
                    pass

        start_time = time.time()
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()
        multi_thread_time = time.time() - start_time

        print(f"\n锁竞争开销分析:")
        print(f"  单线程时间: {single_thread_time:.3f} 秒")
        print(f"  多线程时间: {multi_thread_time:.3f} 秒")
        print(f"  操作数量: 单线程 {num_iterations}, 多线程 {num_threads * iterations_per_thread * 2}")
        print(f"  单线程吞吐量: {num_iterations / single_thread_time:.0f} ops/秒")
        print(f"  多线程吞吐量: {(num_threads * iterations_per_thread * 2) / multi_thread_time:.0f} ops/秒")

        # 计算开销（多线程应该比单线程快，但由于锁竞争可能不会线性扩展）
        efficiency = (multi_thread_time / (num_threads * single_thread_time)) * 100
        print(f"  并行效率: {efficiency:.1f}%")

    def test_stats_access_overhead(self):
        """测试统计访问开销"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)

        # 添加一些消息
        for i in range(100):
            impulse = create_text_impulse(
                content=f"message-{i}",
                priority=1
            )
            queue.put(impulse, block=False)

        # 测试 get_stats 性能
        num_accesses = 10000
        start_time = time.time()
        for _ in range(num_accesses):
            stats = queue.get_stats()
        elapsed = time.time() - start_time

        print(f"\n统计访问开销:")
        print(f"  访问次数: {num_accesses}")
        print(f"  总耗时: {elapsed:.3f} 秒")
        print(f"  平均耗时: {elapsed / num_accesses * 1000:.3f} ms")
        print(f"  访问速率: {num_accesses / elapsed:.0f} 次/秒")

        # 性能基准：每次访问应该 < 1ms
        assert elapsed / num_accesses < 0.001, f"统计访问过慢: {elapsed / num_accesses * 1000:.3f} ms"

    def test_memory_overhead(self):
        """测试内存开销"""
        import sys

        # 测试队列内存占用
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)

        # 添加消息
        num_messages = 1000
        for i in range(num_messages):
            impulse = create_text_impulse(
                content=f"message-{i}",
                priority=1
            )
            queue.put(impulse, block=False)

        # 获取 stats 对象大小
        stats = queue.get_stats()
        stats_size = sys.getsizeof(stats)

        print(f"\n内存开销:")
        print(f"  消息数量: {num_messages}")
        print(f"  Stats 对象大小: {stats_size} bytes")
        print(f"  平均每条消息的 stats 开销: {stats_size / num_messages:.2f} bytes")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])

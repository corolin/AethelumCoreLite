"""
基础并发安全测试
快速验证核心并发安全性
"""
import threading
import time
import pytest
from aethelum_core_lite.core.queue import SynapticQueue
from aethelum_core_lite.core.worker import AxonWorker
from aethelum_core_lite.core.worker_monitor import WorkerMonitor
from aethelum_core_lite.core.worker_scheduler import WorkerScheduler
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


class TestBasicConcurrency:
    """基础并发安全测试"""

    def test_queue_concurrent_put(self):
        """测试队列并发 put 操作"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)
        num_threads = 5
        puts_per_thread = 20

        def put_worker(worker_id):
            for i in range(puts_per_thread):
                impulse = create_text_impulse(f"message-{worker_id}-{i}")
                queue.put(impulse, block=True)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=put_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        stats = queue.get_stats()
        expected = num_threads * puts_per_thread
        assert stats.total_messages == expected, f"Expected {expected} messages, got {stats.total_messages}"
        print(f"✓ 并发 put 测试通过: {stats.total_messages} 条消息")

    def test_queue_concurrent_get(self):
        """测试队列并发 get 操作"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)

        # 先添加消息
        num_messages = 100
        for i in range(num_messages):
            impulse = create_text_impulse(f"message-{i}")
            queue.put(impulse, block=True)

        received = [0]
        num_threads = 5

        def get_worker():
            for _ in range(num_messages // num_threads):
                try:
                    impulse = queue.get(block=False, timeout=0.5)
                    if impulse:
                        received[0] += 1
                except:
                    pass

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=get_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert received[0] == num_messages, f"Expected {num_messages}, got {received[0]}"
        print(f"✓ 并发 get 测试通过: {received[0]} 条消息")

    def test_queue_stats_thread_safety(self):
        """测试队列统计的线程安全性"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)
        num_threads = 10
        ops_per_thread = 20

        def worker(worker_id):
            for i in range(ops_per_thread):
                impulse = create_text_impulse(f"message-{worker_id}-{i}")
                queue.put(impulse, block=False)
                # 并发访问统计信息
                stats = queue.get_stats()
                assert stats is not None

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        print(f"✓ 统计线程安全测试通过")

    def test_worker_stats_locking(self):
        """测试 Worker 统计的锁保护"""
        queue = SynapticQueue(queue_id="test_queue", max_size=100)
        worker = AxonWorker(
            worker_id="test_worker",
            queue=queue,
            processing_time=0.001
        )
        worker.start()

        # 并发访问统计
        num_threads = 10
        def stats_worker():
            for _ in range(5):
                stats = worker.get_stats()
                assert stats is not None
                time.sleep(0.01)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=stats_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        worker.stop()
        print(f"✓ Worker 统计锁测试通过")

    def test_monitor_metrics_locking(self):
        """测试 Monitor 指标的锁保护"""
        monitor = WorkerMonitor(check_interval=0.1)
        monitor.start()

        num_threads = 5
        metrics_per_thread = 10

        def metrics_worker(worker_id):
            for i in range(metrics_per_thread):
                monitor._record_metric(
                    worker_id=f"worker-{worker_id}",
                    metric_name="test_metric",
                    value=i,
                    metric_type="gauge"
                )

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=metrics_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        monitor.stop()
        assert len(monitor._current_metrics) == num_threads
        print(f"✓ Monitor 指标锁测试通过: {len(monitor._current_metrics)} 个 worker")

    def test_scheduler_round_robin_thread_safety(self):
        """测试调度器的轮询索引线程安全"""
        queue = SynapticQueue(queue_id="test_queue", max_size=100)

        workers = []
        for i in range(3):
            worker = AxonWorker(
                worker_id=f"worker-{i}",
                queue=queue,
                processing_time=0.001
            )
            workers.append(worker)
            worker.start()

        scheduler = WorkerScheduler(workers=workers, strategy="round_robin")

        # 并发选择 worker
        selected = []
        num_threads = 5

        def select_worker():
            for _ in range(20):
                try:
                    worker_id = scheduler._select_worker_round_robin()
                    selected.append(worker_id)
                except:
                    pass

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=select_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        for worker in workers:
            worker.stop()

        # 验证选择了多个 worker（不只是某一个）
        unique_workers = set(selected)
        assert len(unique_workers) > 1, f"Should select multiple workers, got: {unique_workers}"
        print(f"✓ 调度器线程安全测试通过: 选择了 {len(unique_workers)} 个不同 worker")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

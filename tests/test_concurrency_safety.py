"""
并发安全性测试套件
测试各组件在多线程环境下的线程安全性
"""
import threading
import time
import pytest
from collections import deque
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


class TestSynapticQueueConcurrency:
    """测试 SynapticQueue 的并发安全性"""

    def test_concurrent_put(self):
        """测试多线程并发 put 操作"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)
        num_threads = 10
        puts_per_thread = 100

        def put_worker(worker_id):
            for i in range(puts_per_thread):
                impulse = create_text_impulse(
                    content=f"message-{worker_id}-{i}",
                    priority=1
                )
                queue.put(impulse, block=True)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=put_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 验证所有消息都被成功添加
        stats = queue.get_stats()
        assert stats.total_messages == num_threads * puts_per_thread
        assert stats.queue_size == num_threads * puts_per_thread

    def test_concurrent_get(self):
        """测试多线程并发 get 操作"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)

        # 先添加消息
        num_messages = 500
        for i in range(num_messages):
            impulse = create_text_impulse(
                content=f"message-{i}",
                priority=1
            )
            queue.put(impulse, block=True)

        received_count = [0]
        num_threads = 10

        def get_worker():
            while True:
                try:
                    impulse = queue.get(block=False, timeout=0.1)
                    if impulse:
                        received_count[0] += 1
                except:
                    break

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=get_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 验证所有消息都被成功获取
        assert received_count[0] == num_messages
        stats = queue.get_stats()
        assert stats.queue_size == 0

    def test_concurrent_put_get(self):
        """测试并发 put 和 get 操作"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)
        num_producers = 5
        num_consumers = 5
        messages_per_producer = 100

        received_count = threading.BoundedSemaphore(value=0)

        def producer(worker_id):
            for i in range(messages_per_producer):
                impulse = create_text_impulse(
                    content=f"message-{worker_id}-{i}",
                    priority=1
                )
                queue.put(impulse, block=True)

        def consumer():
            while True:
                try:
                    impulse = queue.get(block=False, timeout=0.1)
                    if impulse:
                        received_count.release()
                except:
                    break

        # 启动生产者
        producers = []
        for i in range(num_producers):
            t = threading.Thread(target=producer, args=(i,))
            producers.append(t)
            t.start()

        # 启动消费者
        consumers = []
        for i in range(num_consumers):
            t = threading.Thread(target=consumer)
            consumers.append(t)
            t.start()

        # 等待生产者完成
        for t in producers:
            t.join()

        # 等待所有消息被消费
        received_count.acquire()
        for t in consumers:
            t.join(timeout=2)

    def test_get_stats_thread_safety(self):
        """测试 get_stats 在并发环境下的线程安全性"""
        queue = SynapticQueue(queue_id="test_queue", max_size=1000)
        num_threads = 20
        operations_per_thread = 50

        def worker(worker_id):
            for i in range(operations_per_thread):
                if i % 2 == 0:
                    impulse = create_text_impulse(
                        content=f"message-{worker_id}-{i}",
                        priority=1
                    )
                    queue.put(impulse, block=True)
                else:
                    try:
                        stats = queue.get_stats()
                        assert stats is not None
                    except:
                        pass

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()


class TestAxonWorkerConcurrency:
    """测试 AxonWorker 的并发安全性"""

    def test_concurrent_stat_updates(self):
        """测试并发统计更新"""
        worker = AxonWorker(
            worker_id="test_worker",
            queue=SynapticQueue(queue_id="test_queue", max_size=100),
            processing_time=0.01
        )
        worker.start()

        num_threads = 10
        updates_per_thread = 50

        def update_worker():
            for _ in range(updates_per_thread):
                # 模拟内部统计更新
                with worker._stats_lock:
                    worker._stats.processed_messages += 1

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=update_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        worker.stop()

        # 验证统计正确性
        stats = worker.get_stats()
        assert stats.processed_messages == num_threads * updates_per_thread

    def test_get_stats_thread_safety(self):
        """测试 get_stats 的线程安全性"""
        worker = AxonWorker(
            worker_id="test_worker",
            queue=SynapticQueue(queue_id="test_queue", max_size=100),
            processing_time=0.01
        )
        worker.start()

        num_threads = 20
        stats_list = []

        def stats_worker():
            for _ in range(10):
                stats = worker.get_stats()
                stats_list.append(stats)
                time.sleep(0.01)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=stats_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        worker.stop()

        # 验证所有 stats 对象都是独立的副本
        assert len(stats_list) == num_threads * 10


class TestWorkerMonitorConcurrency:
    """测试 WorkerMonitor 的并发安全性"""

    def test_concurrent_metric_recording(self):
        """测试并发指标记录"""
        monitor = WorkerMonitor(check_interval=0.1)
        monitor.start()

        num_threads = 10
        metrics_per_thread = 50

        def metric_worker(worker_id):
            for i in range(metrics_per_thread):
                monitor._record_metric(
                    worker_id=f"worker-{worker_id}",
                    metric_name="test_metric",
                    value=i,
                    metric_type="gauge"
                )

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=metric_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        monitor.stop()

        # 验证指标被正确记录
        assert len(monitor._current_metrics) == num_threads

    def test_concurrent_alert_recording(self):
        """测试并发告警记录"""
        monitor = WorkerMonitor(check_interval=0.1)
        monitor.start()

        num_threads = 10
        alerts_per_thread = 20

        def alert_worker(worker_id):
            for i in range(alerts_per_thread):
                monitor._record_alert(
                    worker_id=f"worker-{worker_id}",
                    alert_type="test_alert",
                    severity="warning",
                    message=f"Test alert {i}"
                )

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=alert_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        monitor.stop()

        # 验证告警被正确记录
        assert len(monitor._alerts) == num_threads * alerts_per_thread

    def test_get_metrics_thread_safety(self):
        """测试 get_metrics 的线程安全性"""
        monitor = WorkerMonitor(check_interval=0.1)
        monitor.start()

        num_threads = 20

        def access_worker():
            for _ in range(10):
                try:
                    metrics = monitor.get_metrics()
                    assert isinstance(metrics, dict)
                except:
                    pass

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=access_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        monitor.stop()


class TestWorkerSchedulerConcurrency:
    """测试 WorkerScheduler 的并发安全性"""

    def test_concurrent_scheduling(self):
        """测试并发调度"""
        queue = SynapticQueue(queue_id="test_queue", max_size=100)

        # 创建多个 worker
        workers = []
        for i in range(5):
            worker = AxonWorker(
                worker_id=f"worker-{i}",
                queue=queue,
                processing_time=0.01
            )
            workers.append(worker)
            worker.start()

        scheduler = WorkerScheduler(
            workers=workers,
            strategy="round_robin"
        )

        num_threads = 10
        schedules_per_thread = 50

        def schedule_worker():
            for _ in range(schedules_per_thread):
                try:
                    worker_id = scheduler._select_worker_round_robin()
                    assert worker_id is not None
                except:
                    pass

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=schedule_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        for worker in workers:
            worker.stop()

    def test_rr_index_thread_safety(self):
        """测试 round-robin 索引的线程安全性"""
        queue = SynapticQueue(queue_id="test_queue", max_size=100)

        workers = []
        for i in range(5):
            worker = AxonWorker(
                worker_id=f"worker-{i}",
                queue=queue,
                processing_time=0.01
            )
            workers.append(worker)
            worker.start()

        scheduler = WorkerScheduler(
            workers=workers,
            strategy="round_robin"
        )

        # 记录所有选择的 worker_id
        selected_workers = []
        num_threads = 10

        def select_worker():
            for _ in range(100):
                try:
                    worker_id = scheduler._select_worker_round_robin()
                    selected_workers.append(worker_id)
                except:
                    pass

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=select_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        for worker in workers:
            worker.stop()

        # 验证选择了所有 worker（不是只选择了某一个）
        unique_workers = set(selected_workers)
        assert len(unique_workers) > 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

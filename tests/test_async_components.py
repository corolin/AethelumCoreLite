"""
AsyncIO组件测试
"""

import pytest
import asyncio

from aethelum_core_lite.core.async_queue import AsyncSynapticQueue, MessagePriority
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter


@pytest.mark.asyncio
class TestAsyncSynapticQueue:
    """异步队列测试"""

    async def test_queue_creation(self):
        """测试队列创建"""
        queue = AsyncSynapticQueue("test_queue", max_size=10)
        assert queue.queue_id == "test_queue"
        assert queue.max_size == 10
        assert queue.size() == 0

    async def test_async_put_and_get(self):
        """测试异步放入和获取"""
        queue = AsyncSynapticQueue("test_queue")

        # 放入消息
        result = await queue.async_put({"data": "test"})
        assert result == True
        assert queue.size() == 1

        # 获取消息
        message = await queue.async_get()
        assert message == {"data": "test"}
        assert queue.size() == 0

    async def test_queue_priority(self):
        """测试优先级队列"""
        queue = AsyncSynapticQueue("test_queue")

        await queue.async_put("low", priority=MessagePriority.LOW)
        await queue.async_put("high", priority=MessagePriority.HIGH)
        await queue.async_put("critical", priority=MessagePriority.CRITICAL)

        # 应该按照优先级获取：CRITICAL(0) < HIGH(1) < LOW(3)
        assert await queue.async_get() == "critical"
        assert await queue.async_get() == "high"
        assert await queue.async_get() == "low"

    async def test_queue_metrics(self):
        """测试队列指标"""
        queue = AsyncSynapticQueue("test_queue", max_size=100)

        await queue.async_put({"test": 1})
        await queue.async_put({"test": 2})

        metrics = queue.get_metrics()
        assert metrics.queue_id == "test_queue"
        assert metrics.size == 2
        assert metrics.total_messages == 2
        assert "usage_percent" in metrics.metrics


@pytest.mark.asyncio
class TestAsyncAxonWorker:
    """异步Worker测试"""

    async def test_worker_creation(self):
        """测试Worker创建"""
        queue = AsyncSynapticQueue("test_queue")
        worker = AsyncAxonWorker("test_worker", input_queue=queue)

        assert worker.name == "test_worker"
        assert worker.worker_id is not None
        assert worker.input_queue == queue

    async def test_worker_start_stop(self):
        """测试Worker启动和停止"""
        queue = AsyncSynapticQueue("test_queue")
        worker = AsyncAxonWorker("test_worker", input_queue=queue)

        await worker.start()
        assert worker.state.value == "running"

        await worker.stop()
        assert worker.state.value == "stopped"

    async def test_worker_pause_resume(self):
        """测试Worker暂停和恢复"""
        queue = AsyncSynapticQueue("test_queue")
        worker = AsyncAxonWorker("test_worker", input_queue=queue)

        await worker.start()
        await worker.pause()
        assert worker.state.value == "paused"

        await worker.resume()
        assert worker.state.value == "running"

        await worker.stop()

    async def test_worker_metrics(self):
        """测试Worker指标"""
        queue = AsyncSynapticQueue("test_queue")
        worker = AsyncAxonWorker("test_worker", input_queue=queue)

        stats = worker.get_stats()
        assert stats.worker_id == worker.worker_id
        assert stats.worker_name == "test_worker"
        assert stats.processed_messages == 0
        assert "metrics" in stats.__dict__


@pytest.mark.asyncio
class TestAsyncNeuralSomaRouter:
    """异步Router测试"""

    async def test_router_creation(self):
        """测试Router创建"""
        router = AsyncNeuralSomaRouter("test_router")
        assert router.router_id == "test_router"
        assert len(router._queues) == 0
        assert len(router._workers) == 0

    async def test_router_register_components(self):
        """测试Router注册组件"""
        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue")
        worker = AsyncAxonWorker("test_worker", input_queue=queue)

        router.register_queue(queue)
        router.register_worker(worker)

        assert len(router._queues) == 1
        assert len(router._workers) == 1
        assert router._metrics.total_queues == 1
        assert router._metrics.total_workers == 1

    async def test_router_routing(self):
        """测试Router路由消息"""
        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue")

        router.register_queue(queue)
        router.add_routing_rule("test_pattern", "test_queue")

        # 路由消息
        result = await router.route_message({"test": "data"}, "test_pattern")
        assert result == True

        # 验证消息已到达队列
        assert queue.size() == 1

    async def test_router_metrics(self):
        """测试Router指标"""
        router = AsyncNeuralSomaRouter("test_router")
        queue = AsyncSynapticQueue("test_queue")

        router.register_queue(queue)
        router.add_routing_rule("test_pattern", "test_queue")

        await router.route_message({"test": "data"}, "test_pattern")

        metrics = router.get_metrics()
        assert "router" in metrics
        assert "queues" in metrics
        assert "workers" in metrics
        assert metrics["router"]["total_messages_routed"] == 1

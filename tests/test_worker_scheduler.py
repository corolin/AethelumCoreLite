import unittest
import time
import threading
from unittest.mock import Mock, MagicMock, patch
from collections import deque

from aethelum_core_lite.core.worker_scheduler import (
    WorkerScheduler, SchedulerState, SchedulingStrategy, WorkerLoadInfo, SchedulerStats
)
from aethelum_core_lite.core.worker import AxonWorker, WorkerState
from aethelum_core_lite.core.worker_manager import WorkerManager
from aethelum_core_lite.core.message import NeuralImpulse
from aethelum_core_lite.core.queue import SynapticQueue


class TestWorkerScheduler(unittest.TestCase):
    """工作器调度器测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 创建模拟的工作器管理器
        self.worker_manager = Mock(spec=WorkerManager)
        
        # 创建模拟的工作器
        self.worker1 = Mock(spec=AxonWorker)
        self.worker1.name = "test_worker_1"
        self.worker1.get_state.return_value = WorkerState.RUNNING
        self.worker1.get_stats.return_value = Mock(
            queue_size=10,
            processing_rate=5.0,
            success_rate=95.0,
            health_score=0.9,
            uptime=100.0,
            total_processed=100,
            total_failed=5
        )
        
        self.worker2 = Mock(spec=AxonWorker)
        self.worker2.name = "test_worker_2"
        self.worker2.get_state.return_value = WorkerState.RUNNING
        self.worker2.get_stats.return_value = Mock(
            queue_size=20,
            processing_rate=3.0,
            success_rate=85.0,
            health_score=0.7,
            uptime=200.0,
            total_processed=200,
            total_failed=30
        )
        
        self.worker3 = Mock(spec=AxonWorker)
        self.worker3.name = "test_worker_3"
        self.worker3.get_state.return_value = WorkerState.PAUSED
        self.worker3.get_stats.return_value = Mock(
            queue_size=5,
            processing_rate=2.0,
            success_rate=80.0,
            health_score=0.6,
            uptime=150.0,
            total_processed=150,
            total_failed=30
        )
        
        # 设置工作器管理器的返回值
        self.worker_manager.get_all_workers.return_value = {
            "worker1": self.worker1,
            "worker2": self.worker2,
            "worker3": self.worker3
        }
        
        self.worker_manager.get_worker.return_value = self.worker1
        
        # 创建调度器
        self.scheduler = WorkerScheduler(
            name="test_scheduler",
            worker_manager=self.worker_manager,
            strategy=SchedulingStrategy.ROUND_ROBIN,
            load_update_interval=0.1,  # 快速更新用于测试
            enable_load_balancing=True
        )
    
    def tearDown(self):
        """测试后清理"""
        if self.scheduler.get_state() != SchedulerState.STOPPED:
            self.scheduler.stop()
    
    def test_init(self):
        """测试初始化"""
        self.assertEqual(self.scheduler.name, "test_scheduler")
        self.assertEqual(self.scheduler.worker_manager, self.worker_manager)
        self.assertEqual(self.scheduler.strategy, SchedulingStrategy.ROUND_ROBIN)
        self.assertEqual(self.scheduler.get_state(), SchedulerState.INITIALIZING)
        self.assertTrue(self.scheduler.enable_load_balancing)
        self.assertEqual(self.scheduler.current_index, 0)
    
    def test_start_stop(self):
        """测试启动和停止"""
        # 启动调度器
        self.scheduler.start()
        self.assertEqual(self.scheduler.get_state(), SchedulerState.RUNNING)
        
        # 等待一段时间让调度器更新负载信息
        time.sleep(0.3)
        
        # 检查是否更新了负载信息
        load_info = self.scheduler.get_load_info()
        self.assertGreater(len(load_info), 0)
        
        # 停止调度器
        self.scheduler.stop()
        self.assertEqual(self.scheduler.get_state(), SchedulerState.STOPPED)
    
    def test_pause_resume(self):
        """测试暂停和恢复"""
        # 启动调度器
        self.scheduler.start()
        
        # 暂停调度器
        self.scheduler.pause()
        self.assertEqual(self.scheduler.get_state(), SchedulerState.PAUSED)
        
        # 等待一段时间
        time.sleep(0.3)
        
        # 检查负载更新是否暂停
        load_info_before = self.scheduler.get_load_info()
        
        # 恢复调度器
        self.scheduler.resume()
        self.assertEqual(self.scheduler.get_state(), SchedulerState.RUNNING)
        
        # 等待一段时间
        time.sleep(0.3)
        
        # 检查负载更新是否恢复
        load_info_after = self.scheduler.get_load_info()
        self.assertGreater(len(load_info_after), len(load_info_before))
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_round_robin_strategy(self):
        """测试轮询调度策略"""
        # 设置调度策略为轮询
        self.scheduler.set_strategy(SchedulingStrategy.ROUND_ROBIN)
        
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        message1 = Mock(spec=NeuralImpulse)
        message2 = Mock(spec=NeuralImpulse)
        message3 = Mock(spec=NeuralImpulse)
        
        # 调度消息
        worker1 = self.scheduler.schedule_message(message1)
        worker2 = self.scheduler.schedule_message(message2)
        worker3 = self.scheduler.schedule_message(message3)
        
        # 检查调度结果
        self.assertEqual(worker1, self.worker1)
        self.assertEqual(worker2, self.worker2)
        self.assertEqual(worker3, self.worker1)  # 跳过worker3，因为它处于暂停状态
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_least_loaded_strategy(self):
        """测试最少负载调度策略"""
        # 设置调度策略为最少负载
        self.scheduler.set_strategy(SchedulingStrategy.LEAST_LOADED)
        
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        message = Mock(spec=NeuralImpulse)
        
        # 调度消息
        worker = self.scheduler.schedule_message(message)
        
        # 检查调度结果
        # worker1的队列大小为10，worker2的队列大小为20，所以应该选择worker1
        self.assertEqual(worker, self.worker1)
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_weighted_round_robin_strategy(self):
        """测试加权轮询调度策略"""
        # 设置调度策略为加权轮询
        self.scheduler.set_strategy(SchedulingStrategy.WEIGHTED_ROUND_ROBIN)
        
        # 设置工作器权重
        self.scheduler.set_worker_weight("worker1", 2)
        self.scheduler.set_worker_weight("worker2", 1)
        
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        messages = [Mock(spec=NeuralImpulse) for _ in range(6)]
        
        # 调度消息
        workers = []
        for message in messages:
            worker = self.scheduler.schedule_message(message)
            workers.append(worker)
        
        # 检查调度结果
        # worker1的权重为2，worker2的权重为1，所以应该有4次选择worker1，2次选择worker2
        worker1_count = workers.count(self.worker1)
        worker2_count = workers.count(self.worker2)
        
        self.assertEqual(worker1_count, 4)
        self.assertEqual(worker2_count, 2)
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_random_strategy(self):
        """测试随机调度策略"""
        # 设置调度策略为随机
        self.scheduler.set_strategy(SchedulingStrategy.RANDOM)
        
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        message = Mock(spec=NeuralImpulse)
        
        # 调度消息
        worker = self.scheduler.schedule_message(message)
        
        # 检查调度结果
        # 应该是worker1或worker2中的一个，不应该是worker3，因为它处于暂停状态
        self.assertIn(worker, [self.worker1, self.worker2])
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_load_info(self):
        """测试负载信息"""
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 获取负载信息
        load_info = self.scheduler.get_load_info()
        
        # 检查负载信息
        self.assertEqual(len(load_info), 3)  # 3个工作器
        
        # 检查worker1的负载信息
        worker1_info = load_info["worker1"]
        self.assertEqual(worker1_info.worker_id, "worker1")
        self.assertEqual(worker1_info.worker_name, "test_worker_1")
        self.assertEqual(worker1_info.state, WorkerState.RUNNING)
        self.assertEqual(worker1_info.queue_size, 10)
        self.assertEqual(worker1_info.processing_rate, 5.0)
        self.assertEqual(worker1_info.success_rate, 95.0)
        self.assertEqual(worker1_info.health_score, 0.9)
        self.assertEqual(worker1_info.uptime, 100.0)
        self.assertEqual(worker1_info.total_processed, 100)
        self.assertEqual(worker1_info.total_failed, 5)
        
        # 检查worker3的负载信息
        worker3_info = load_info["worker3"]
        self.assertEqual(worker3_info.state, WorkerState.PAUSED)
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_worker_weights(self):
        """测试工作器权重"""
        # 设置工作器权重
        self.scheduler.set_worker_weight("worker1", 2)
        self.scheduler.set_worker_weight("worker2", 1)
        
        # 检查权重
        self.assertEqual(self.scheduler.get_worker_weight("worker1"), 2)
        self.assertEqual(self.scheduler.get_worker_weight("worker2"), 1)
        self.assertEqual(self.scheduler.get_worker_weight("worker3"), 1)  # 默认权重
        
        # 获取所有权重
        weights = self.scheduler.get_all_worker_weights()
        self.assertEqual(weights["worker1"], 2)
        self.assertEqual(weights["worker2"], 1)
        self.assertEqual(weights["worker3"], 1)
        
        # 移除权重
        self.scheduler.remove_worker_weight("worker1")
        
        # 检查权重是否移除
        self.assertEqual(self.scheduler.get_worker_weight("worker1"), 1)  # 回到默认权重
    
    def test_stats(self):
        """测试统计信息"""
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        messages = [Mock(spec=NeuralImpulse) for _ in range(5)]
        
        # 调度消息
        for message in messages:
            self.scheduler.schedule_message(message)
        
        # 获取统计信息
        stats = self.scheduler.get_stats()
        
        # 检查统计信息
        self.assertEqual(stats.scheduler_id, self.scheduler.scheduler_id)
        self.assertEqual(stats.name, "test_scheduler")
        self.assertEqual(stats.state, SchedulerState.RUNNING)
        self.assertGreater(stats.uptime, 0)
        self.assertEqual(stats.total_scheduled, 5)
        self.assertEqual(stats.active_workers, 2)  # 只有worker1和worker2是活跃的
        self.assertGreater(stats.scheduling_rate, 0)
        self.assertGreater(stats.load_balance_score, 0)
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_str_repr(self):
        """测试字符串表示"""
        # 测试__str__
        str_repr = str(self.scheduler)
        self.assertIn("WorkerScheduler", str_repr)
        self.assertIn("test_scheduler", str_repr)
        self.assertIn("initializing", str_repr)
        
        # 测试__repr__
        repr_str = repr(self.scheduler)
        self.assertIn("WorkerScheduler", repr_str)
        self.assertIn("test_scheduler", repr_str)
        self.assertIn("initializing", repr_str)
        self.assertIn(self.scheduler.scheduler_id, repr_str)
    
    def test_schedule_message_no_available_workers(self):
        """测试没有可用工作器时的消息调度"""
        # 设置所有工作器为非运行状态
        self.worker1.get_state.return_value = WorkerState.ERROR
        self.worker2.get_state.return_value = WorkerState.STOPPED
        self.worker3.get_state.return_value = WorkerState.PAUSED
        
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        message = Mock(spec=NeuralImpulse)
        
        # 调度消息
        worker = self.scheduler.schedule_message(message)
        
        # 检查调度结果
        self.assertIsNone(worker)
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_schedule_message_with_priority(self):
        """测试带优先级的消息调度"""
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        message = Mock(spec=NeuralImpulse)
        message.priority = 5  # 高优先级
        
        # 调度消息
        worker = self.scheduler.schedule_message(message)
        
        # 检查调度结果
        # 高优先级消息应该分配给负载最低的工作器
        self.assertEqual(worker, self.worker1)
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_schedule_batch_messages(self):
        """测试批量消息调度"""
        # 启动调度器
        self.scheduler.start()
        
        # 等待负载更新
        time.sleep(0.3)
        
        # 创建模拟消息
        messages = [Mock(spec=NeuralImpulse) for _ in range(10)]
        
        # 批量调度消息
        results = self.scheduler.schedule_batch_messages(messages)
        
        # 检查调度结果
        self.assertEqual(len(results), 10)
        
        # 检查每个消息都被分配了工作器
        for worker in results:
            self.assertIn(worker, [self.worker1, self.worker2])
        
        # 停止调度器
        self.scheduler.stop()
    
    def test_load_balancing_disabled(self):
        """测试禁用负载均衡"""
        # 创建禁用负载均衡的调度器
        scheduler = WorkerScheduler(
            name="test_scheduler_no_lb",
            worker_manager=self.worker_manager,
            strategy=SchedulingStrategy.ROUND_ROBIN,
            enable_load_balancing=False
        )
        
        # 启动调度器
        scheduler.start()
        
        # 等待一段时间
        time.sleep(0.3)
        
        # 创建模拟消息
        message = Mock(spec=NeuralImpulse)
        
        # 调度消息
        worker = scheduler.schedule_message(message)
        
        # 检查调度结果
        # 即使worker3处于暂停状态，也应该被选择，因为负载均衡被禁用
        self.assertIn(worker, [self.worker1, self.worker2, self.worker3])
        
        # 停止调度器
        scheduler.stop()


if __name__ == '__main__':
    unittest.main()

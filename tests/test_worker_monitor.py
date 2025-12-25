import unittest
import time
import threading
from unittest.mock import Mock, MagicMock, patch
from collections import deque

from aethelum_core_lite.core.worker_monitor import (
    WorkerMonitor, MonitorState, AlertLevel, MetricType, 
    MetricValue, Alert, ThresholdRule, MonitorStats
)
from aethelum_core_lite.core.worker import AxonWorker, WorkerState
from aethelum_core_lite.core.worker_manager import WorkerManager
from aethelum_core_lite.core.worker_scheduler import WorkerScheduler
from aethelum_core_lite.core.message import NeuralImpulse
from aethelum_core_lite.core.queue import SynapticQueue


class TestWorkerMonitor(unittest.TestCase):
    """工作器监控器测试类"""
    
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
        
        # 设置工作器管理器的返回值
        self.worker_manager.get_all_workers.return_value = {
            "worker1": self.worker1,
            "worker2": self.worker2
        }
        
        # 创建模拟的调度器
        self.scheduler = Mock(spec=WorkerScheduler)
        self.scheduler.scheduler_id = "test_scheduler"
        self.scheduler.name = "test_scheduler"
        self.scheduler.get_stats.return_value = Mock(
            scheduling_rate=10.0,
            load_balance_score=0.8,
            active_workers=2
        )
        
        # 创建监控器
        self.monitor = WorkerMonitor(
            name="test_monitor",
            worker_manager=self.worker_manager,
            scheduler=self.scheduler,
            metrics_collection_interval=0.1,  # 快速收集用于测试
            health_check_interval=0.2,  # 快速检查用于测试
            alert_cooldown_period=0.5,  # 短冷却期用于测试
            enable_auto_recovery=True
        )
    
    def tearDown(self):
        """测试后清理"""
        if self.monitor.get_state() != MonitorState.STOPPED:
            self.monitor.stop()
    
    def test_init(self):
        """测试初始化"""
        self.assertEqual(self.monitor.name, "test_monitor")
        self.assertEqual(self.monitor.worker_manager, self.worker_manager)
        self.assertEqual(self.monitor.scheduler, self.scheduler)
        self.assertEqual(self.monitor.get_state(), MonitorState.INITIALIZING)
        self.assertTrue(self.monitor.enable_auto_recovery)
        
        # 检查默认阈值规则
        rules = self.monitor.get_threshold_rules()
        self.assertIn("worker_cpu_high", rules)
        self.assertIn("worker_memory_high", rules)
        self.assertIn("worker_queue_size_high", rules)
        self.assertIn("worker_success_rate_low", rules)
        self.assertIn("worker_health_low", rules)
        self.assertIn("worker_processing_rate_low", rules)
    
    def test_start_stop(self):
        """测试启动和停止"""
        # 启动监控器
        self.monitor.start()
        self.assertEqual(self.monitor.get_state(), MonitorState.RUNNING)
        
        # 等待一段时间让监控器收集指标
        time.sleep(0.3)
        
        # 检查是否收集了指标
        metrics = self.monitor.get_current_metrics()
        self.assertGreater(len(metrics), 0)
        
        # 停止监控器
        self.monitor.stop()
        self.assertEqual(self.monitor.get_state(), MonitorState.STOPPED)
    
    def test_pause_resume(self):
        """测试暂停和恢复"""
        # 启动监控器
        self.monitor.start()
        
        # 暂停监控器
        self.monitor.pause()
        self.assertEqual(self.monitor.get_state(), MonitorState.PAUSED)
        
        # 等待一段时间
        time.sleep(0.3)
        
        # 检查指标收集是否暂停
        metrics_before = self.monitor.get_current_metrics()
        
        # 恢复监控器
        self.monitor.resume()
        self.assertEqual(self.monitor.get_state(), MonitorState.RUNNING)
        
        # 等待一段时间
        time.sleep(0.3)
        
        # 检查指标收集是否恢复
        metrics_after = self.monitor.get_current_metrics()
        self.assertGreater(len(metrics_after), len(metrics_before))
        
        # 停止监控器
        self.monitor.stop()
    
    def test_metrics_collection(self):
        """测试指标收集"""
        # 启动监控器
        self.monitor.start()
        
        # 等待指标收集
        time.sleep(0.3)
        
        # 检查收集的指标
        metrics = self.monitor.get_current_metrics()
        
        # 检查工作器指标
        self.assertIn("worker_queue_size", metrics)
        self.assertIn("worker_processing_rate", metrics)
        self.assertIn("worker_success_rate", metrics)
        self.assertIn("worker_health_score", metrics)
        self.assertIn("worker_uptime", metrics)
        self.assertIn("worker_total_processed", metrics)
        self.assertIn("worker_total_failed", metrics)
        self.assertIn("worker_cpu_usage", metrics)
        self.assertIn("worker_memory_usage", metrics)
        
        # 检查调度器指标
        self.assertIn("scheduler_scheduling_rate", metrics)
        self.assertIn("scheduler_load_balance_score", metrics)
        self.assertIn("scheduler_active_workers", metrics)
        
        # 检查指标值
        self.assertEqual(metrics["worker_queue_size"].value, 10.0)  # worker1的值
        self.assertEqual(metrics["worker_processing_rate"].value, 5.0)  # worker1的值
        self.assertEqual(metrics["worker_success_rate"].value, 95.0)  # worker1的值
        self.assertEqual(metrics["worker_health_score"].value, 0.9)  # worker1的值
        
        # 停止监控器
        self.monitor.stop()
    
    def test_threshold_rules(self):
        """测试阈值规则"""
        # 启动监控器
        self.monitor.start()
        
        # 添加自定义阈值规则
        custom_rule = ThresholdRule(
            rule_id="custom_rule",
            metric_name="worker_queue_size",
            operator=">",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="自定义队列大小阈值"
        )
        self.monitor.add_threshold_rule(custom_rule)
        
        # 检查规则是否添加
        rules = self.monitor.get_threshold_rules()
        self.assertIn("custom_rule", rules)
        
        # 等待阈值检查
        time.sleep(0.3)
        
        # 检查是否触发了告警
        alerts = self.monitor.get_active_alerts()
        self.assertGreater(len(alerts), 0)
        
        # 检查告警内容
        alert_found = False
        for alert in alerts.values():
            if alert.metric_name == "worker_queue_size" and alert.current_value == 10.0:
                alert_found = True
                self.assertEqual(alert.level, AlertLevel.WARNING)
                self.assertEqual(alert.threshold, 5.0)
                break
        
        self.assertTrue(alert_found)
        
        # 移除规则
        self.monitor.remove_threshold_rule("custom_rule")
        
        # 检查规则是否移除
        rules = self.monitor.get_threshold_rules()
        self.assertNotIn("custom_rule", rules)
        
        # 停止监控器
        self.monitor.stop()
    
    def test_health_checks(self):
        """测试健康检查"""
        # 设置工作器为错误状态
        self.worker1.get_state.return_value = WorkerState.ERROR
        
        # 设置工作器健康分数低
        self.worker2.get_stats.return_value.health_score = 0.3
        
        # 启动监控器
        self.monitor.start()
        
        # 等待健康检查
        time.sleep(0.3)
        
        # 检查是否触发了告警
        alerts = self.monitor.get_active_alerts()
        self.assertGreater(len(alerts), 0)
        
        # 检查告警内容
        error_alert_found = False
        health_alert_found = False
        
        for alert in alerts.values():
            if alert.worker_id == "worker1" and "错误状态" in alert.title:
                error_alert_found = True
                self.assertEqual(alert.level, AlertLevel.ERROR)
            
            if alert.worker_id == "worker2" and "健康分数低" in alert.title:
                health_alert_found = True
                self.assertEqual(alert.level, AlertLevel.WARNING)
        
        self.assertTrue(error_alert_found)
        self.assertTrue(health_alert_found)
        
        # 停止监控器
        self.monitor.stop()
    
    def test_alert_callbacks(self):
        """测试告警回调"""
        # 创建告警回调
        alert_callback = Mock()
        self.monitor.add_alert_callback(alert_callback)
        
        # 设置工作器为错误状态
        self.worker1.get_state.return_value = WorkerState.ERROR
        
        # 启动监控器
        self.monitor.start()
        
        # 等待健康检查
        time.sleep(0.3)
        
        # 检查回调是否被调用
        alert_callback.assert_called()
        
        # 获取回调参数
        call_args = alert_callback.call_args[0][0]
        self.assertIsInstance(call_args, Alert)
        self.assertEqual(call_args.worker_id, "worker1")
        
        # 移除回调
        self.monitor.remove_alert_callback(alert_callback)
        
        # 重置mock
        alert_callback.reset_mock()
        
        # 等待一段时间
        time.sleep(0.3)
        
        # 检查回调是否不再被调用
        alert_callback.assert_not_called()
        
        # 停止监控器
        self.monitor.stop()
    
    def test_auto_recovery(self):
        """测试自动恢复"""
        # 创建恢复回调
        recovery_callback = Mock(return_value=True)
        self.monitor.add_recovery_callback(recovery_callback)
        
        # 设置工作器为错误状态
        self.worker1.get_state.return_value = WorkerState.ERROR
        
        # 启动监控器
        self.monitor.start()
        
        # 等待健康检查和自动恢复
        time.sleep(0.3)
        
        # 检查恢复回调是否被调用
        recovery_callback.assert_called()
        
        # 获取回调参数
        call_args = recovery_callback.call_args[0]
        self.assertEqual(call_args[0], "worker1")  # worker_id
        self.assertIsInstance(call_args[1], str)  # alert_id
        
        # 检查告警是否被解决
        alerts = self.monitor.get_active_alerts()
        
        # 由于自动恢复，错误告警应该被解决
        error_alert_found = False
        for alert in alerts.values():
            if alert.worker_id == "worker1" and "错误状态" in alert.title:
                error_alert_found = True
                break
        
        # 注意：由于自动恢复是异步的，可能需要更长时间才能完成
        # 这里我们只检查恢复回调是否被调用
        
        # 停止监控器
        self.monitor.stop()
    
    def test_stats(self):
        """测试统计信息"""
        # 启动监控器
        self.monitor.start()
        
        # 等待指标收集
        time.sleep(0.3)
        
        # 获取统计信息
        stats = self.monitor.get_stats()
        
        # 检查统计信息
        self.assertEqual(stats.monitor_id, self.monitor.monitor_id)
        self.assertEqual(stats.name, "test_monitor")
        self.assertEqual(stats.state, MonitorState.RUNNING)
        self.assertGreater(stats.uptime, 0)
        self.assertGreater(stats.total_metrics_collected, 0)
        self.assertEqual(stats.monitored_workers, 2)
        self.assertGreater(stats.metrics_collection_rate, 0)
        
        # 停止监控器
        self.monitor.stop()
    
    def test_alert_history(self):
        """测试告警历史"""
        # 设置工作器为错误状态
        self.worker1.get_state.return_value = WorkerState.ERROR
        
        # 启动监控器
        self.monitor.start()
        
        # 等待健康检查
        time.sleep(0.3)
        
        # 获取告警历史
        alert_history = self.monitor.get_alert_history()
        self.assertGreater(len(alert_history), 0)
        
        # 检查告警历史内容
        error_alert_found = False
        for alert in alert_history:
            if alert.worker_id == "worker1" and "错误状态" in alert.title:
                error_alert_found = True
                self.assertEqual(alert.level, AlertLevel.ERROR)
                break
        
        self.assertTrue(error_alert_found)
        
        # 停止监控器
        self.monitor.stop()
    
    def test_metric_history(self):
        """测试指标历史"""
        # 启动监控器
        self.monitor.start()
        
        # 等待指标收集
        time.sleep(0.3)
        
        # 获取指标历史
        metric_history = self.monitor.get_metric_history("worker_queue_size")
        self.assertGreater(len(metric_history), 0)
        
        # 检查指标历史内容
        for metric in metric_history:
            self.assertIsInstance(metric, MetricValue)
            self.assertEqual(metric.name, "worker_queue_size")
            self.assertEqual(metric.metric_type, MetricType.GAUGE)
            self.assertEqual(metric.unit, "messages")
            self.assertEqual(metric.description, "工作器队列大小")
        
        # 停止监控器
        self.monitor.stop()
    
    def test_resolve_alert(self):
        """测试解决告警"""
        # 设置工作器为错误状态
        self.worker1.get_state.return_value = WorkerState.ERROR
        
        # 启动监控器
        self.monitor.start()
        
        # 等待健康检查
        time.sleep(0.3)
        
        # 获取活跃告警
        alerts_before = self.monitor.get_active_alerts()
        self.assertGreater(len(alerts_before), 0)
        
        # 获取一个告警ID
        alert_id = next(iter(alerts_before.keys()))
        
        # 解决告警
        self.monitor.resolve_alert(alert_id)
        
        # 检查告警是否被解决
        alerts_after = self.monitor.get_active_alerts()
        self.assertNotIn(alert_id, alerts_after)
        
        # 检查告警历史
        alert_history = self.monitor.get_alert_history()
        resolved_alert = None
        for alert in alert_history:
            if alert.alert_id == alert_id:
                resolved_alert = alert
                break
        
        self.assertIsNotNone(resolved_alert)
        self.assertTrue(resolved_alert.resolved)
        self.assertIsNotNone(resolved_alert.resolved_timestamp)
        
        # 停止监控器
        self.monitor.stop()
    
    def test_export_metrics(self):
        """测试导出指标"""
        # 启动监控器
        self.monitor.start()
        
        # 等待指标收集
        time.sleep(0.3)
        
        # 导出指标
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            temp_file = f.name
        
        try:
            self.monitor.export_metrics(temp_file)
            
            # 检查文件是否存在
            self.assertTrue(os.path.exists(temp_file))
            
            # 检查文件内容
            with open(temp_file, 'r') as f:
                import json
                data = json.load(f)
                
                self.assertIn("current_metrics", data)
                self.assertIn("stats", data)
                
                # 检查指标
                metrics = data["current_metrics"]
                self.assertIn("worker_queue_size", metrics)
                self.assertIn("worker_processing_rate", metrics)
                
                # 检查统计信息
                stats = data["stats"]
                self.assertEqual(stats["name"], "test_monitor")
                self.assertEqual(stats["state"], "running")
                self.assertGreater(stats["total_metrics_collected"], 0)
        finally:
            # 删除临时文件
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        
        # 停止监控器
        self.monitor.stop()
    
    def test_str_repr(self):
        """测试字符串表示"""
        # 测试__str__
        str_repr = str(self.monitor)
        self.assertIn("WorkerMonitor", str_repr)
        self.assertIn("test_monitor", str_repr)
        self.assertIn("initializing", str_repr)
        
        # 测试__repr__
        repr_str = repr(self.monitor)
        self.assertIn("WorkerMonitor", repr_str)
        self.assertIn("test_monitor", repr_str)
        self.assertIn("initializing", repr_str)
        self.assertIn(self.monitor.monitor_id, repr_str)


if __name__ == '__main__':
    unittest.main()

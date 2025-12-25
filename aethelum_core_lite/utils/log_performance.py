"""
日志性能优化模块

提供高性能的日志写入、批量处理和性能监控功能。
"""

import time
import threading
import queue
import asyncio
import multiprocessing
from typing import Any, Dict, List, Optional, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from collections import defaultdict, deque
import weakref
import gc

from .structured_logger import LogEntry, LogOutput, LogLevel


@dataclass
class LogBatch:
    """日志批次"""
    entries: List[LogEntry] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    size_bytes: int = 0
    
    def add_entry(self, entry: LogEntry, entry_size: int):
        """添加日志条目"""
        self.entries.append(entry)
        self.size_bytes += entry_size
    
    def is_full(self, max_entries: int, max_size: int) -> bool:
        """检查批次是否已满"""
        return (len(self.entries) >= max_entries or 
                self.size_bytes >= max_size)
    
    def is_expired(self, max_age: float) -> bool:
        """检查批次是否过期"""
        return time.time() - self.created_at >= max_age


@dataclass
class PerformanceMetrics:
    """性能指标"""
    total_entries: int = 0
    total_batches: int = 0
    total_bytes: int = 0
    total_time: float = 0.0
    avg_batch_size: float = 0.0
    avg_processing_time: float = 0.0
    queue_depth: int = 0
    memory_usage: int = 0
    gc_pressure: int = 0  # GC压力指标
    
    def update(self, batch: LogBatch, processing_time: float):
        """更新指标"""
        self.total_entries += len(batch.entries)
        self.total_batches += 1
        self.total_bytes += batch.size_bytes
        self.total_time += processing_time
        self.avg_batch_size = self.total_entries / max(1, self.total_batches)
        self.avg_processing_time = self.total_time / max(1, self.total_batches)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_entries': self.total_entries,
            'total_batches': self.total_batches,
            'total_bytes': self.total_bytes,
            'total_time': self.total_time,
            'avg_batch_size': self.avg_batch_size,
            'avg_processing_time': self.avg_processing_time,
            'queue_depth': self.queue_depth,
            'memory_usage': self.memory_usage,
            'gc_pressure': self.gc_pressure
        }


class BatchLogOutput(LogOutput):
    """批量日志输出器"""
    
    def __init__(self, output: LogOutput, max_batch_size: int = 100, 
                 max_batch_bytes: int = 1024 * 1024, max_wait_time: float = 1.0,
                 use_multiprocessing: bool = False, process_pool_size: int = 2):
        """
        初始化批量输出器
        
        Args:
            output: 底层输出器
            max_batch_size: 最大批次条目数
            max_batch_bytes: 最大批次字节数
            max_wait_time: 最大等待时间（秒）
            use_multiprocessing: 是否使用多进程
            process_pool_size: 进程池大小
        """
        self.output = output
        self.max_batch_size = max_batch_size
        self.max_batch_bytes = max_batch_bytes
        self.max_wait_time = max_wait_time
        self.use_multiprocessing = use_multiprocessing
        
        self.current_batch = LogBatch()
        self.lock = threading.RLock()
        self.processing_queue = queue.Queue(maxsize=1000)
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.metrics = PerformanceMetrics()
        
        # 进程池
        if self.use_multiprocessing:
            self.process_pool = ProcessPoolExecutor(max_workers=process_pool_size)
        else:
            self.process_pool = ThreadPoolExecutor(max_workers=process_pool_size)
        
        self.start_worker()
    
    def start_worker(self):
        """启动工作线程"""
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
    
    def write(self, formatted_entry: str, entry: LogEntry):
        """写入日志条目"""
        entry_size = len(formatted_entry.encode('utf-8'))
        
        with self.lock:
            self.current_batch.add_entry(entry, entry_size)
            
            # 检查是否需要处理批次
            if (self.current_batch.is_full(self.max_batch_size, self.max_batch_bytes) or
                self.current_batch.is_expired(self.max_wait_time)):
                
                batch = self.current_batch
                self.current_batch = LogBatch()
                
                # 提交批次处理
                try:
                    self.processing_queue.put_nowait(batch)
                except queue.Full:
                    # 队列满，直接写入
                    self._process_batch_sync(batch)
    
    def _worker_loop(self):
        """工作线程循环"""
        while not self.stop_event.is_set():
            try:
                # 等待批次
                batch = self.processing_queue.get(timeout=0.1)
                
                # 处理当前批次
                if batch and batch.entries:
                    self._process_batch(batch)
                
            except queue.Empty:
                # 检查是否有超时的批次
                with self.lock:
                    if (self.current_batch.entries and 
                        self.current_batch.is_expired(self.max_wait_time)):
                        
                        batch = self.current_batch
                        self.current_batch = LogBatch()
                        
                        if batch.entries:
                            self._process_batch(batch)
    
    def _process_batch(self, batch: LogBatch):
        """处理批次"""
        start_time = time.time()
        
        if self.use_multiprocessing and len(batch.entries) > 10:
            # 多进程处理大批次
            future = self.process_pool.submit(self._process_batch_worker, batch)
            future.add_done_callback(lambda f: self._on_batch_complete(f, batch, start_time))
        else:
            # 线程内处理
            try:
                self._process_batch_sync(batch)
                processing_time = time.time() - start_time
                self.metrics.update(batch, processing_time)
            except Exception as e:
                # 处理失败，记录错误
                self._handle_batch_error(batch, e)
    
    def _process_batch_worker(self, batch: LogBatch) -> int:
        """工作进程处理批次"""
        processed_count = 0
        
        for entry in batch.entries:
            try:
                # 这里只能处理已格式化的条目
                # 实际应用中需要传递格式化后的字符串
                processed_count += 1
            except Exception:
                pass
        
        return processed_count
    
    def _process_batch_sync(self, batch: LogBatch):
        """同步处理批次"""
        processed_count = 0
        
        for entry in batch.entries:
            try:
                # 重新格式化条目
                # 这里需要访问格式化器，实际应用中需要更好的设计
                formatted = f"{entry.timestamp} [{entry.level.name}] {entry.message}"
                self.output.write(formatted, entry)
                processed_count += 1
            except Exception:
                pass
        
        return processed_count
    
    def _on_batch_complete(self, future, batch: LogBatch, start_time: float):
        """批次处理完成回调"""
        try:
            result = future.result()
            processing_time = time.time() - start_time
            self.metrics.update(batch, processing_time)
        except Exception as e:
            self._handle_batch_error(batch, e)
    
    def _handle_batch_error(self, batch: LogBatch, error: Exception):
        """处理批次错误"""
        # 记录错误但继续处理其他批次
        pass
    
    def force_flush(self):
        """强制刷新当前批次"""
        with self.lock:
            if self.current_batch.entries:
                batch = self.current_batch
                self.current_batch = LogBatch()
                self._process_batch(batch)
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        self.metrics.queue_depth = self.processing_queue.qsize()
        
        # 更新内存使用情况
        import psutil
        try:
            process = psutil.Process()
            self.metrics.memory_usage = process.memory_info().rss
            self.metrics.gc_pressure = gc.get_count()[0]  # 代数
        except:
            pass
        
        return self.metrics.to_dict()
    
    def close(self):
        """关闭输出器"""
        # 处理剩余批次
        self.force_flush()
        
        # 停止工作线程
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5.0)
        
        # 处理队列中的剩余批次
        while not self.processing_queue.empty():
            try:
                batch = self.processing_queue.get_nowait()
                if batch and batch.entries:
                    self._process_batch_sync(batch)
            except queue.Empty:
                break
        
        # 关闭底层输出器
        self.output.close()
        
        # 关闭进程池
        self.process_pool.shutdown(wait=True)


class AsyncBatchLogOutput(LogOutput):
    """异步批量日志输出器"""
    
    def __init__(self, output: LogOutput, max_batch_size: int = 50,
                 max_wait_time: float = 0.5, max_concurrent_batches: int = 10):
        self.output = output
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.max_concurrent_batches = max_concurrent_batches
        
        self.current_batch = LogBatch()
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(max_concurrent_batches)
        self.pending_batches = asyncio.Queue(maxsize=100)
        self.stop_event = asyncio.Event()
        self.worker_task = None
        self.metrics = PerformanceMetrics()
        
        # 在事件循环中启动工作协程
        self._start_worker()
    
    def _start_worker(self):
        """启动工作协程"""
        try:
            loop = asyncio.get_running_loop()
            self.worker_task = loop.create_task(self._worker_loop())
        except RuntimeError:
            # 没有运行的事件循环，创建新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.worker_task = loop.create_task(self._worker_loop())
    
    async def write_async(self, formatted_entry: str, entry: LogEntry):
        """异步写入日志条目"""
        entry_size = len(formatted_entry.encode('utf-8'))
        
        async with self.lock:
            self.current_batch.add_entry(entry, entry_size)
            
            # 检查是否需要处理批次
            if (self.current_batch.is_full(self.max_batch_size, self.max_batch_bytes) or
                self.current_batch.is_expired(self.max_wait_time)):
                
                batch = self.current_batch
                self.current_batch = LogBatch()
                
                # 提交批次处理
                try:
                    await self.pending_batches.put(batch)
                except asyncio.QueueFull:
                    # 队列满，同步处理
                    await self._process_batch_sync(batch)
    
    def write(self, formatted_entry: str, entry: LogEntry):
        """同步写入接口（兼容LogOutput）"""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # 在事件循环中，创建任务
                loop.create_task(self.write_async(formatted_entry, entry))
            else:
                # 不在事件循环中，运行新的事件循环
                asyncio.run(self.write_async(formatted_entry, entry))
        except RuntimeError:
            # 同步处理
            entry_size = len(formatted_entry.encode('utf-8'))
            async with self.lock:
                self.current_batch.add_entry(entry, entry_size)
                if self.current_batch.is_full(self.max_batch_size, self.max_batch_bytes):
                    batch = self.current_batch
                    self.current_batch = LogBatch()
                    asyncio.run(self._process_batch_sync(batch))
    
    async def _worker_loop(self):
        """工作协程循环"""
        while not self.stop_event.is_set():
            try:
                # 等待批次
                batch = await asyncio.wait_for(
                    self.pending_batches.get(), 
                    timeout=0.1
                )
                
                # 处理批次
                if batch and batch.entries:
                    await self._process_batch(batch)
                    
            except asyncio.TimeoutError:
                # 检查超时批次
                async with self.lock:
                    if (self.current_batch.entries and 
                        self.current_batch.is_expired(self.max_wait_time)):
                        
                        batch = self.current_batch
                        self.current_batch = LogBatch()
                        
                        if batch.entries:
                            await self._process_batch(batch)
    
    async def _process_batch(self, batch: LogBatch):
        """异步处理批次"""
        async with self.semaphore:  # 限制并发批次数量
            start_time = time.time()
            
            try:
                await self._process_batch_sync(batch)
                processing_time = time.time() - start_time
                self.metrics.update(batch, processing_time)
            except Exception as e:
                self._handle_batch_error(batch, e)
    
    async def _process_batch_sync(self, batch: LogBatch):
        """同步处理批次（在异步上下文中）"""
        for entry in batch.entries:
            try:
                # 重新格式化并写入
                formatted = f"{entry.timestamp} [{entry.level.name}] {entry.message}"
                self.output.write(formatted, entry)
                await asyncio.sleep(0)  # 让出控制权
            except Exception:
                pass
    
    def _handle_batch_error(self, batch: LogBatch, error: Exception):
        """处理批次错误"""
        pass
    
    async def force_flush(self):
        """强制刷新当前批次"""
        async with self.lock:
            if self.current_batch.entries:
                batch = self.current_batch
                self.current_batch = LogBatch()
                await self._process_batch(batch)
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        self.metrics.queue_depth = self.pending_batches.qsize()
        return self.metrics.to_dict()
    
    def close(self):
        """关闭输出器"""
        # 处理剩余批次
        if self.worker_task:
            # 创建任务来强制刷新
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.force_flush())
                else:
                    asyncio.run(self.force_flush())
            except:
                pass
        
        # 停止工作协程
        self.stop_event.set()
        if self.worker_task:
            self.worker_task.cancel()
        
        # 关闭底层输出器
        self.output.close()


class LogPerformanceMonitor:
    """日志性能监控器"""
    
    def __init__(self, sample_interval: float = 5.0, history_size: int = 100):
        self.sample_interval = sample_interval
        self.history_size = history_size
        self.outputs: List[Union[BatchLogOutput, AsyncBatchLogOutput]] = []
        self.metrics_history = deque(maxlen=history_size)
        self.stop_monitoring = threading.Event()
        self.monitor_thread = None
        self.lock = threading.Lock()
    
    def add_output(self, output: Union[BatchLogOutput, AsyncBatchLogOutput]):
        """添加要监控的输出器"""
        with self.lock:
            self.outputs.append(output)
    
    def start_monitoring(self):
        """开始监控"""
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.stop_monitoring.clear()
            self.monitor_thread = threading.Thread(
                target=self._monitoring_loop, 
                daemon=True
            )
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监控"""
        self.stop_monitoring.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10.0)
    
    def _monitoring_loop(self):
        """监控循环"""
        while not self.stop_monitoring.is_set():
            try:
                timestamp = time.time()
                metrics = self._collect_metrics()
                
                sample = {
                    'timestamp': timestamp,
                    'metrics': metrics,
                    'output_count': len(self.outputs)
                }
                
                self.metrics_history.append(sample)
                
                # 检查性能问题
                self._check_performance_issues(metrics)
                
                time.sleep(self.sample_interval)
                
            except Exception as e:
                # 监控错误不应该影响日志系统
                time.sleep(self.sample_interval)
    
    def _collect_metrics(self) -> Dict[str, Any]:
        """收集指标"""
        with self.lock:
            if not self.outputs:
                return {}
            
            total_metrics = {
                'total_entries': 0,
                'total_batches': 0,
                'total_bytes': 0,
                'avg_processing_time': 0.0,
                'total_queue_depth': 0,
                'total_memory_usage': 0,
                'output_count': len(self.outputs)
            }
            
            for output in self.outputs:
                try:
                    metrics = output.get_metrics()
                    total_metrics['total_entries'] += metrics.get('total_entries', 0)
                    total_metrics['total_batches'] += metrics.get('total_batches', 0)
                    total_metrics['total_bytes'] += metrics.get('total_bytes', 0)
                    total_metrics['avg_processing_time'] += metrics.get('avg_processing_time', 0)
                    total_metrics['total_queue_depth'] += metrics.get('queue_depth', 0)
                    total_metrics['total_memory_usage'] += metrics.get('memory_usage', 0)
                except Exception:
                    pass
            
            if total_metrics['output_count'] > 0:
                total_metrics['avg_processing_time'] /= total_metrics['output_count']
                total_metrics['avg_queue_depth'] = total_metrics['total_queue_depth'] / total_metrics['output_count']
            
            return total_metrics
    
    def _check_performance_issues(self, metrics: Dict[str, Any]):
        """检查性能问题"""
        # 队列积压过多
        if metrics.get('avg_queue_depth', 0) > 100:
            self._trigger_performance_alert('high_queue_depth', metrics)
        
        # 处理时间过长
        if metrics.get('avg_processing_time', 0) > 0.1:  # 100ms
            self._trigger_performance_alert('slow_processing', metrics)
        
        # 内存使用过多
        if metrics.get('total_memory_usage', 0) > 100 * 1024 * 1024:  # 100MB
            self._trigger_performance_alert('high_memory_usage', metrics)
    
    def _trigger_performance_alert(self, alert_type: str, metrics: Dict[str, Any]):
        """触发性能警报"""
        # 这里可以发送警报、记录到监控系统等
        pass
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        if not self.metrics_history:
            return {}
        
        recent_samples = list(self.metrics_history)[-10:]  # 最近10个样本
        
        if not recent_samples:
            return {}
        
        # 计算平均值和趋势
        avg_entries = sum(s['metrics'].get('total_entries', 0) for s in recent_samples) / len(recent_samples)
        avg_processing_time = sum(s['metrics'].get('avg_processing_time', 0) for s in recent_samples) / len(recent_samples)
        avg_queue_depth = sum(s['metrics'].get('avg_queue_depth', 0) for s in recent_samples) / len(recent_samples)
        
        # 计算趋势（最后两个样本的对比）
        if len(recent_samples) >= 2:
            last_sample = recent_samples[-1]['metrics']
            prev_sample = recent_samples[-2]['metrics']
            
            entries_trend = last_sample.get('total_entries', 0) - prev_sample.get('total_entries', 0)
            processing_trend = last_sample.get('avg_processing_time', 0) - prev_sample.get('avg_processing_time', 0)
            queue_trend = last_sample.get('avg_queue_depth', 0) - prev_sample.get('avg_queue_depth', 0)
        else:
            entries_trend = processing_trend = queue_trend = 0
        
        return {
            'current_metrics': recent_samples[-1]['metrics'],
            'averages': {
                'avg_entries': avg_entries,
                'avg_processing_time': avg_processing_time,
                'avg_queue_depth': avg_queue_depth
            },
            'trends': {
                'entries_trend': entries_trend,
                'processing_time_trend': processing_trend,
                'queue_depth_trend': queue_trend
            },
            'sample_count': len(recent_samples),
            'monitoring_duration': len(self.metrics_history) * self.sample_interval
        }


# 全局性能监控器
_global_performance_monitor = LogPerformanceMonitor()

def get_performance_monitor() -> LogPerformanceMonitor:
    """获取全局性能监控器"""
    return _global_performance_monitor

def start_log_performance_monitoring():
    """启动日志性能监控"""
    _global_performance_monitor.start_monitoring()

def stop_log_performance_monitoring():
    """停止日志性能监控"""
    _global_performance_monitor.stop_monitoring()

def get_log_performance_summary() -> Dict[str, Any]:
    """获取日志性能摘要"""
    return _global_performance_monitor.get_performance_summary()
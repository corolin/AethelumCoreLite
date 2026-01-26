"""
Hook性能优化模块

提供Hook执行性能优化、监控和调优功能。
"""

import asyncio
import time
import threading
import logging
import queue
import weakref
from typing import Any, Dict, List, Optional, Callable, Union, Tuple
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from collections import defaultdict, deque
import gc

# psutil 是可选依赖
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from .base_hook import BaseHook, AsyncHook


@dataclass
class PerformanceMetrics:
    """性能指标"""
    execution_time: float = 0.0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    success: bool = True
    error_message: str = ""
    timestamp: float = field(default_factory=time.time)
    hook_name: str = ""
    hook_type: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'execution_time': self.execution_time,
            'memory_usage': self.memory_usage,
            'cpu_usage': self.cpu_usage,
            'success': self.success,
            'error_message': self.error_message,
            'timestamp': self.timestamp,
            'hook_name': self.hook_name,
            'hook_type': self.hook_type
        }


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.real_time_stats: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.lock = threading.RLock()
        self.logger = logging.getLogger("hook_performance_monitor")
        
    def record_metrics(self, metrics: PerformanceMetrics):
        """记录性能指标"""
        with self.lock:
            hook_key = f"{metrics.hook_type}:{metrics.hook_name}"
            self.metrics_history[hook_key].append(metrics)
            
            # 更新实时统计
            stats = self.real_time_stats[hook_key]
            recent_metrics = list(self.metrics_history[hook_key])
            
            if recent_metrics:
                execution_times = [m.execution_time for m in recent_metrics]
                memory_usages = [m.memory_usage for m in recent_metrics if m.memory_usage > 0]
                success_count = sum(1 for m in recent_metrics if m.success)
                
                stats.update({
                    'total_executions': len(recent_metrics),
                    'success_rate': success_count / len(recent_metrics),
                    'avg_execution_time': sum(execution_times) / len(execution_times),
                    'max_execution_time': max(execution_times),
                    'min_execution_time': min(execution_times),
                    'avg_memory_usage': sum(memory_usages) / len(memory_usages) if memory_usages else 0,
                    'last_execution': metrics.timestamp
                })
    
    def get_hook_performance(self, hook_name: str, hook_type: str = "base") -> Dict[str, Any]:
        """获取Hook性能信息"""
        hook_key = f"{hook_type}:{hook_name}"
        with self.lock:
            stats = self.real_time_stats.get(hook_key, {})
            recent_metrics = list(self.metrics_history.get(hook_key, []))
            
            return {
                'hook_name': hook_name,
                'hook_type': hook_type,
                'real_time_stats': stats,
                'recent_metrics': [m.to_dict() for m in recent_metrics[-10:]]  # 最近10次
            }
    
    def get_system_performance(self) -> Dict[str, Any]:
        """获取系统性能信息"""
        if not PSUTIL_AVAILABLE:
            # psutil 不可用，返回基础信息
            return {
                'cpu_percent': 0.0,
                'memory_info': {},
                'memory_percent': 0.0,
                'threads': threading.active_count(),
                'open_files': 0,
                'timestamp': time.time(),
                'note': 'psutil 不可用，返回基础信息'
            }

        process = psutil.Process()
        return {
            'cpu_percent': process.cpu_percent(),
            'memory_info': process.memory_info()._asdict(),
            'memory_percent': process.memory_percent(),
            'threads': process.num_threads(),
            'open_files': len(process.open_files()),
            'timestamp': time.time()
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        with self.lock:
            summary = {
                'total_hooks': len(self.real_time_stats),
                'system_performance': self.get_system_performance(),
                'hook_performance': {},
                'slow_hooks': [],
                'error_prone_hooks': []
            }
            
            for hook_key, stats in self.real_time_stats.items():
                hook_type, hook_name = hook_key.split(':', 1)
                hook_perf = self.get_hook_performance(hook_name, hook_type)
                summary['hook_performance'][hook_key] = hook_perf
                
                # 识别慢Hook
                if stats.get('avg_execution_time', 0) > 0.1:  # 100ms
                    summary['slow_hooks'].append({
                        'hook_name': hook_name,
                        'hook_type': hook_type,
                        'avg_time': stats['avg_execution_time']
                    })
                
                # 识别错误率高的Hook
                if stats.get('success_rate', 1.0) < 0.95:  # 95%
                    summary['error_prone_hooks'].append({
                        'hook_name': hook_name,
                        'hook_type': hook_type,
                        'success_rate': stats['success_rate']
                    })
            
            return summary


class HookCache:
    """Hook结果缓存"""
    
    def __init__(self, max_size: int = 1000, ttl: float = 300.0):
        self.max_size = max_size
        self.ttl = ttl  # 缓存生存时间（秒）
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.access_times: Dict[str, float] = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger("hook_cache")
        
    def _generate_key(self, impulse: Any, hook_name: str) -> str:
        """生成缓存键"""
        # 基于脉冲内容和Hook名称生成键
        if hasattr(impulse, 'session_id'):
            base_key = f"{hook_name}:{impulse.session_id}"
        else:
            base_key = f"{hook_name}:{hash(str(impulse))}"
            
        # 包含关键字段
        if hasattr(impulse, 'action_intent'):
            base_key += f":{impulse.action_intent}"
        if hasattr(impulse, 'source_agent'):
            base_key += f":{impulse.source_agent}"
            
        return base_key
    
    def get(self, impulse: Any, hook_name: str) -> Optional[Any]:
        """获取缓存结果"""
        key = self._generate_key(impulse, hook_name)
        
        with self.lock:
            if key not in self.cache:
                return None
                
            result, timestamp = self.cache[key]
            
            # 检查TTL
            if time.time() - timestamp > self.ttl:
                del self.cache[key]
                if key in self.access_times:
                    del self.access_times[key]
                return None
            
            # 更新访问时间
            self.access_times[key] = time.time()
            return result
    
    def put(self, impulse: Any, hook_name: str, result: Any):
        """存储缓存结果"""
        key = self._generate_key(impulse, hook_name)
        
        with self.lock:
            # 检查缓存大小，必要时清理
            if len(self.cache) >= self.max_size:
                self._evict_lru()
            
            self.cache[key] = (result, time.time())
            self.access_times[key] = time.time()
    
    def _evict_lru(self):
        """移除最少使用的条目"""
        if not self.access_times:
            return
            
        lru_key = min(self.access_times.items(), key=lambda x: x[1])[0]
        if lru_key in self.cache:
            del self.cache[lru_key]
        del self.access_times[lru_key]
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self.lock:
            return {
                'cache_size': len(self.cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'memory_usage': sum(len(str(result)) for result, _ in self.cache.values())
            }


class AsyncHookExecutor:
    """异步Hook执行器"""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.logger = logging.getLogger("async_hook_executor")
        
    async def execute_async_hooks(self, hooks: List[AsyncHook], impulse: Any, source_queue: str) -> Any:
        """异步执行多个Hook"""
        if not hooks:
            return impulse
            
        tasks = []
        for hook in hooks:
            if hook.enabled:
                task = self._execute_single_async_hook(hook, impulse, source_queue)
                tasks.append(task)
        
        if not tasks:
            return impulse
            
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        final_impulse = impulse
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"异步Hook {hooks[i].hook_name} 执行失败: {result}")
                final_impulse.metadata[f'async_hook_error_{hooks[i].hook_name}'] = str(result)
            elif result is not None:
                final_impulse = result
                
        return final_impulse
    
    async def _execute_single_async_hook(self, hook: AsyncHook, impulse: Any, source_queue: str) -> Any:
        """执行单个异步Hook"""
        async with self.semaphore:
            try:
                return await hook.async_process(impulse, source_queue)
            except Exception as e:
                self.logger.error(f"异步Hook {hook.hook_name} 执行异常: {e}")
                raise e
    
    def execute_parallel_hooks(self, hooks: List[BaseHook], impulse: Any, source_queue: str) -> Any:
        """并行执行多个Hook"""
        if not hooks:
            return impulse
            
        enabled_hooks = [h for h in hooks if h.enabled]
        if not enabled_hooks:
            return impulse
            
        if len(enabled_hooks) == 1:
            return enabled_hooks[0].process(impulse, source_queue)
        
        # 提交所有任务
        futures = {
            self.executor.submit(self._execute_hook_safe, hook, impulse, source_queue): hook
            for hook in enabled_hooks
        }
        
        results = []
        errors = []
        
        # 收集结果
        for future in as_completed(futures):
            hook = futures[future]
            try:
                result = future.result()
                results.append((hook, result))
            except Exception as e:
                self.logger.error(f"并行Hook {hook.hook_name} 执行失败: {e}")
                errors.append((hook, str(e)))
        
        # 合并结果（使用最后一个成功的结果）
        final_impulse = impulse
        if results:
            final_impulse = results[-1][1]
            
        # 添加错误信息
        for hook, error in errors:
            final_impulse.metadata[f'parallel_hook_error_{hook.hook_name}'] = error
            
        return final_impulse
    
    def _execute_hook_safe(self, hook: BaseHook, impulse: Any, source_queue: str) -> Any:
        """安全执行Hook"""
        try:
            return hook.process(impulse, source_queue)
        except Exception as e:
            self.logger.error(f"Hooks {hook.hook_name} 执行失败: {e}")
            raise e
    
    def shutdown(self):
        """关闭执行器"""
        self.executor.shutdown(wait=True)


class PerformanceOptimizer:
    """性能优化器"""
    
    def __init__(self, enable_caching: bool = True, cache_size: int = 1000, 
                 enable_monitoring: bool = True, max_async_workers: int = 10):
        self.enable_caching = enable_caching
        self.enable_monitoring = enable_monitoring
        self.logger = logging.getLogger("hook_performance_optimizer")
        
        # 初始化组件
        self.cache = HookCache(max_size=cache_size) if enable_caching else None
        self.monitor = PerformanceMonitor() if enable_monitoring else None
        self.async_executor = AsyncHookExecutor(max_concurrent=max_async_workers)
        
        # 性能配置
        self.performance_config = {
            'slow_threshold': 0.1,  # 100ms
            'memory_threshold': 50 * 1024 * 1024,  # 50MB
            'cpu_threshold': 80.0,  # 80%
            'auto_gc_threshold': 100  # 执行次数
        }
        
        self.execution_count = 0
        
    def optimize_hook_execution(self, hook: BaseHook, impulse: Any, source_queue: str, 
                                use_cache: Optional[bool] = None, parallel: bool = False) -> Any:
        """优化Hook执行"""
        start_time = time.time()
        start_memory = self._get_memory_usage()
        success = True
        error_message = ""
        result = impulse
        
        try:
            # 缓存检查
            use_cache = use_cache if use_cache is not None else self.enable_caching
            if use_cache and self.cache:
                cached_result = self.cache.get(impulse, hook.hook_name)
                if cached_result is not None:
                    return cached_result
            
            # 执行Hook
            if isinstance(hook, AsyncHook) and hasattr(asyncio, 'get_running_loop'):
                # 尝试异步执行
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        # 在事件循环中，使用线程池执行
                        result = self.async_executor.executor.submit(
                            hook.process, impulse, source_queue
                        ).result()
                    else:
                        result = hook.process(impulse, source_queue)
                except RuntimeError:
                    result = hook.process(impulse, source_queue)
            else:
                result = hook.process(impulse, source_queue)
            
            # 缓存结果
            if use_cache and self.cache and success:
                self.cache.put(impulse, hook.hook_name, result)
                
        except Exception as e:
            success = False
            error_message = str(e)
            self.logger.error(f"Hooks {hook.hook_name} 执行失败: {e}")
            result = impulse
            
        finally:
            # 记录性能指标
            execution_time = time.time() - start_time
            end_memory = self._get_memory_usage()
            memory_usage = end_memory - start_memory
            cpu_usage = self._get_cpu_usage()
            
            if self.monitor:
                metrics = PerformanceMetrics(
                    execution_time=execution_time,
                    memory_usage=memory_usage,
                    cpu_usage=cpu_usage,
                    success=success,
                    error_message=error_message,
                    hook_name=hook.hook_name,
                    hook_type=getattr(hook, 'hook_type', 'base')
                )
                self.monitor.record_metrics(metrics)
            
            # 自动垃圾回收
            self.execution_count += 1
            if (self.execution_count % self.performance_config['auto_gc_threshold'] == 0 and
                memory_usage > self.performance_config['memory_threshold']):
                gc.collect()
                self.logger.info("执行自动垃圾回收")
            
            # 性能警告
            if execution_time > self.performance_config['slow_threshold']:
                self.logger.warning(f"Hooks {hook.hook_name} 执行缓慢: {execution_time:.3f}s")
        
        return result
    
    async def optimize_async_hooks_execution(self, hooks: List[AsyncHook], impulse: Any, 
                                           source_queue: str) -> Any:
        """优化异步Hook执行"""
        return await self.async_executor.execute_async_hooks(hooks, impulse, source_queue)
    
    def optimize_parallel_execution(self, hooks: List[BaseHook], impulse: Any, 
                                   source_queue: str) -> Any:
        """优化并行Hook执行"""
        return self.async_executor.execute_parallel_hooks(hooks, impulse, source_queue)
    
    def _get_memory_usage(self) -> float:
        """获取当前内存使用量"""
        if not PSUTIL_AVAILABLE:
            # psutil 不可用，返回估算值
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        try:
            process = psutil.Process()
            return process.memory_info().rss
        except:
            return 0.0
    
    def _get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        try:
            process = psutil.Process()
            return process.cpu_percent()
        except:
            return 0.0
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        report = {
            'optimizer_config': {
                'enable_caching': self.enable_caching,
                'enable_monitoring': self.enable_monitoring,
                'execution_count': self.execution_count
            }
        }
        
        if self.cache:
            report['cache_stats'] = self.cache.get_stats()
            
        if self.monitor:
            report['performance_summary'] = self.monitor.get_performance_summary()
            
        return report
    
    def clear_cache(self):
        """清空缓存"""
        if self.cache:
            self.cache.clear()
            self.logger.info("已清空Hook缓存")
    
    def shutdown(self):
        """关闭优化器"""
        self.async_executor.shutdown()
        self.logger.info("性能优化器已关闭")


# 全局性能优化器实例
_global_optimizer = None

def get_performance_optimizer(enable_caching: bool = True, cache_size: int = 1000, 
                             enable_monitoring: bool = True, max_async_workers: int = 10) -> PerformanceOptimizer:
    """获取全局性能优化器"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = PerformanceOptimizer(
            enable_caching=enable_caching,
            cache_size=cache_size,
            enable_monitoring=enable_monitoring,
            max_async_workers=max_async_workers
        )
    return _global_optimizer
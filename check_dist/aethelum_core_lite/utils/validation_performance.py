"""
验证性能优化模块

提供验证结果缓存、并行验证和性能监控功能。
"""

import time
import threading
import asyncio
import hashlib
import json
from typing import Any, Dict, List, Optional, Union, Callable, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from collections import defaultdict, OrderedDict
import weakref
import pickle

from .unified_validator import (
    BaseValidator, ValidationResult, ValidationContext, ValidationStatus,
    ValidationSeverity
)


@dataclass
class ValidationCacheKey:
    """验证缓存键"""
    validator_name: str
    data_hash: str
    context_hash: str
    
    def __eq__(self, other):
        if not isinstance(other, ValidationCacheKey):
            return False
        return (self.validator_name == other.validator_name and
                self.data_hash == other.data_hash and
                self.context_hash == other.context_hash)
    
    def __hash__(self):
        return hash((self.validator_name, self.data_hash, self.context_hash))
    
    @classmethod
    def create(cls, validator_name: str, data: Any, context: ValidationContext) -> 'ValidationCacheKey':
        """创建缓存键"""
        data_hash = cls._hash_data(data)
        context_hash = cls._hash_context(context)
        return cls(validator_name, data_hash, context_hash)
    
    @staticmethod
    def _hash_data(data: Any) -> str:
        """哈希数据"""
        try:
            if isinstance(data, (str, int, float, bool)) or data is None:
                data_str = str(data)
            elif isinstance(data, (list, tuple)):
                data_str = json.dumps([ValidationCacheKey._hash_data(item) for item in data], sort_keys=True)
            elif isinstance(data, dict):
                # 排序字典键确保一致性
                sorted_data = {k: ValidationCacheKey._hash_data(v) for k, v in sorted(data.items())}
                data_str = json.dumps(sorted_data, sort_keys=True)
            else:
                # 对于其他类型，使用pickle序列化
                data_str = hashlib.md5(pickle.dumps(data)).hexdigest()
            
            return hashlib.sha256(data_str.encode('utf-8')).hexdigest()[:16]
        except Exception:
            # 如果哈希失败，使用字符串表示
            return hashlib.sha256(str(data).encode('utf-8')).hexdigest()[:16]
    
    @staticmethod
    def _hash_context(context: ValidationContext) -> str:
        """哈希上下文"""
        context_data = {
            'field_path': context.field_path,
            'parent_path': context.parent_path,
            'session_id': context.session_id,
            'correlation_id': context.correlation_id
        }
        context_str = json.dumps(context_data, sort_keys=True, default=str)
        return hashlib.sha256(context_str.encode('utf-8')).hexdigest()[:16]


@dataclass
class CacheEntry:
    """缓存条目"""
    result: ValidationResult
    created_at: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    def is_expired(self, ttl: float) -> bool:
        """检查是否过期"""
        return time.time() - self.created_at > ttl
    
    def access(self):
        """访问缓存条目"""
        self.access_count += 1
        self.last_accessed = time.time()


class ValidationCache:
    """验证结果缓存"""
    
    def __init__(self, max_size: int = 1000, ttl: float = 300.0):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict[ValidationCacheKey, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expired_cleanups': 0
        }
    
    def get(self, validator_name: str, data: Any, context: ValidationContext) -> Optional[ValidationResult]:
        """获取缓存结果"""
        key = ValidationCacheKey.create(validator_name, data, context)
        
        with self.lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            entry = self.cache[key]
            
            # 检查过期
            if entry.is_expired(self.ttl):
                del self.cache[key]
                self.stats['expired_cleanups'] += 1
                self.stats['misses'] += 1
                return None
            
            # 移到末尾（LRU）
            self.cache.move_to_end(key)
            entry.access()
            self.stats['hits'] += 1
            
            return entry.result
    
    def put(self, validator_name: str, data: Any, context: ValidationContext, 
            result: ValidationResult):
        """存储缓存结果"""
        key = ValidationCacheKey.create(validator_name, data, context)
        entry = CacheEntry(result=result, created_at=time.time())
        
        with self.lock:
            # 检查容量
            if len(self.cache) >= self.max_size:
                self._evict_lru()
            
            self.cache[key] = entry
    
    def _evict_lru(self):
        """移除最少使用的条目"""
        if self.cache:
            # 移除最老的条目
            self.cache.popitem(last=False)
            self.stats['evictions'] += 1
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.stats = {
                'hits': 0,
                'misses': 0,
                'evictions': 0,
                'expired_cleanups': 0
            }
    
    def cleanup_expired(self):
        """清理过期条目"""
        current_time = time.time()
        expired_keys = []
        
        with self.lock:
            for key, entry in self.cache.items():
                if entry.is_expired(self.ttl):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
                self.stats['expired_cleanups'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self.lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / max(1, total_requests)) * 100
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'hit_rate': hit_rate,
                'evictions': self.stats['evictions'],
                'expired_cleanups': self.stats['expired_cleanups'],
                'total_requests': total_requests
            }


class ParallelValidationEngine:
    """并行验证引擎"""
    
    def __init__(self, max_workers: int = 4, use_processes: bool = False,
                 process_pool_size: int = 2):
        self.max_workers = max_workers
        self.use_processes = use_processes
        
        if use_processes:
            self.executor = ProcessPoolExecutor(max_workers=process_pool_size)
        else:
            self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        self.stats = {
            'parallel_validations': 0,
            'sequential_validations': 0,
            'total_time_saved': 0.0
        }
        self.lock = threading.Lock()
    
    def validate_parallel(self, validators: List[BaseValidator], 
                        data: Any, context: ValidationContext) -> List[ValidationResult]:
        """并行验证"""
        if not validators:
            return []
        
        if len(validators) == 1:
            # 单个验证器，顺序执行
            start_time = time.time()
            result = validators[0]._execute_validation(data, context)
            execution_time = time.time() - start_time
            
            with self.lock:
                self.stats['sequential_validations'] += 1
            
            return [result]
        
        # 多个验证器，并行执行
        start_time = time.time()
        
        # 提交所有验证任务
        futures = {
            self.executor.submit(self._execute_validator_safe, validator, data, context): validator
            for validator in validators if validator.enabled
        }
        
        # 收集结果
        results = []
        for future in as_completed(futures):
            validator = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                # 验证器执行失败，创建错误结果
                error_result = ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"验证器 {validator.name} 执行异常: {str(e)}",
                    validator_name=validator.name
                )
                results.append(error_result)
        
        execution_time = time.time() - start_time
        
        # 估算节省的时间（假设顺序执行的总时间）
        estimated_sequential_time = len(validators) * execution_time / len(results)
        time_saved = max(0, estimated_sequential_time - execution_time)
        
        with self.lock:
            self.stats['parallel_validations'] += 1
            self.stats['total_time_saved'] += time_saved
        
        return results
    
    def _execute_validator_safe(self, validator: BaseValidator, 
                            data: Any, context: ValidationContext) -> ValidationResult:
        """安全执行验证器"""
        try:
            return validator._execute_validation(data, context)
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"验证器 {validator.name} 执行异常: {str(e)}",
                validator_name=validator.name
            )
    
    async def validate_async(self, validators: List[BaseValidator],
                          data: Any, context: ValidationContext) -> List[ValidationResult]:
        """异步验证"""
        if not validators:
            return []
        
        # 创建异步任务
        tasks = []
        for validator in validators:
            if validator.enabled:
                if hasattr(validator, 'async_validate'):
                    # 支持异步的验证器
                    task = asyncio.create_task(
                        self._execute_async_validator(validator, data, context)
                    )
                else:
                    # 同步验证器在线程池中执行
                    task = asyncio.get_running_loop().run_in_executor(
                        self.executor,
                        self._execute_validator_safe,
                        validator, data, context
                    )
                tasks.append(task)
        
        # 等待所有任务完成
        results = []
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                results.append(result)
            except Exception as e:
                error_result = ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"异步验证执行异常: {str(e)}",
                )
                results.append(error_result)
        
        return results
    
    async def _execute_async_validator(self, validator: BaseValidator,
                                    data: Any, context: ValidationContext) -> ValidationResult:
        """执行异步验证器"""
        try:
            if hasattr(validator, 'async_validate'):
                return await validator.async_validate(data, context)
            else:
                return validator._execute_validation(data, context)
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"异步验证器 {validator.name} 执行异常: {str(e)}",
                validator_name=validator.name
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            return self.stats.copy()
    
    def shutdown(self):
        """关闭执行器"""
        self.executor.shutdown(wait=True)


class ValidationPerformanceOptimizer:
    """验证性能优化器"""
    
    def __init__(self, enable_cache: bool = True, cache_size: int = 1000,
                 cache_ttl: float = 300.0, max_workers: int = 4,
                 use_processes: bool = False):
        self.enable_cache = enable_cache
        self.cache = ValidationCache(cache_size, cache_ttl) if enable_cache else None
        self.engine = ParallelValidationEngine(max_workers, use_processes)
        
        # 性能统计
        self.validation_stats = defaultdict(lambda: {
            'total_validations': 0,
            'total_time': 0.0,
            'cache_hits': 0,
            'cache_misses': 0
        })
        
        self.lock = threading.Lock()
    
    def validate_with_optimization(self, validators: List[BaseValidator],
                                 data: Any, context: ValidationContext,
                                 use_cache: Optional[bool] = None,
                                 parallel: bool = True) -> List[ValidationResult]:
        """优化验证"""
        use_cache = use_cache if use_cache is not None else self.enable_cache
        start_time = time.time()
        
        results = []
        
        if parallel and len(validators) > 1:
            # 并行验证
            results = self._validate_parallel_with_cache(validators, data, context, use_cache)
        else:
            # 顺序验证
            results = self._validate_sequential_with_cache(validators, data, context, use_cache)
        
        # 更新统计
        execution_time = time.time() - start_time
        self._update_stats(validators, execution_time, use_cache)
        
        return results
    
    def _validate_sequential_with_cache(self, validators: List[BaseValidator],
                                   data: Any, context: ValidationContext,
                                   use_cache: bool) -> List[ValidationResult]:
        """带缓存的顺序验证"""
        results = []
        
        for validator in validators:
            if not validator.enabled:
                continue
            
            # 检查缓存
            result = None
            if use_cache and self.cache:
                result = self.cache.get(validator.name, data, context)
                
                if result:
                    self._update_validator_stats(validator, 'cache_hit')
                else:
                    self._update_validator_stats(validator, 'cache_miss')
            
            # 缓存未命中，执行验证
            if result is None:
                result = validator._execute_validation(data, context)
                
                # 存储到缓存
                if use_cache and self.cache:
                    self.cache.put(validator.name, data, context, result)
            
            results.append(result)
        
        return results
    
    def _validate_parallel_with_cache(self, validators: List[BaseValidator],
                                  data: Any, context: ValidationContext,
                                  use_cache: bool) -> List[ValidationResult]:
        """带缓存的并行验证"""
        # 先检查缓存
        cached_results = {}
        uncached_validators = []
        
        if use_cache and self.cache:
            for validator in validators:
                if not validator.enabled:
                    continue
                
                cached_result = self.cache.get(validator.name, data, context)
                if cached_result:
                    cached_results[validator] = cached_result
                    self._update_validator_stats(validator, 'cache_hit')
                else:
                    uncached_validators.append(validator)
                    self._update_validator_stats(validator, 'cache_miss')
        
        # 并行执行未缓存的验证器
        uncached_results = []
        if uncached_validators:
            uncached_results = self.engine.validate_parallel(
                uncached_validators, data, context
            )
            
            # 存储到缓存
            if use_cache and self.cache:
                for validator, result in zip(uncached_validators, uncached_results):
                    self.cache.put(validator.name, data, context, result)
        
        # 合并结果
        all_results = []
        
        # 添加缓存结果
        for validator, result in cached_results.items():
            all_results.append(result)
        
        # 添加未缓存结果
        all_results.extend(uncached_results)
        
        # 按原顺序排序
        validator_order = {v: i for i, v in enumerate(validators)}
        all_results.sort(key=lambda r: validator_order.get(
            next((v for v in validators if v.name == r.validator_name), None), 
            float('inf')
        ))
        
        return all_results
    
    async def validate_async_with_optimization(self, validators: List[BaseValidator],
                                           data: Any, context: ValidationContext,
                                           use_cache: Optional[bool] = None) -> List[ValidationResult]:
        """异步优化验证"""
        use_cache = use_cache if use_cache is not None else self.enable_cache
        
        # 先检查缓存
        cached_results = {}
        uncached_validators = []
        
        if use_cache and self.cache:
            for validator in validators:
                if not validator.enabled:
                    continue
                
                cached_result = self.cache.get(validator.name, data, context)
                if cached_result:
                    cached_results[validator] = cached_result
                    self._update_validator_stats(validator, 'cache_hit')
                else:
                    uncached_validators.append(validator)
                    self._update_validator_stats(validator, 'cache_miss')
        
        # 异步执行未缓存的验证器
        uncached_results = []
        if uncached_validators:
            uncached_results = await self.engine.validate_async(
                uncached_validators, data, context
            )
            
            # 存储到缓存
            if use_cache and self.cache:
                for validator, result in zip(uncached_validators, uncached_results):
                    self.cache.put(validator.name, data, context, result)
        
        # 合并结果
        all_results = list(cached_results.values()) + uncached_results
        
        # 按原顺序排序
        validator_order = {v: i for i, v in enumerate(validators)}
        all_results.sort(key=lambda r: validator_order.get(
            next((v for v in validators if v.name == r.validator_name), None), 
            float('inf')
        ))
        
        return all_results
    
    def _update_validator_stats(self, validator: BaseValidator, stat_type: str):
        """更新验证器统计"""
        with self.lock:
            stats = self.validation_stats[validator.name]
            if stat_type == 'cache_hit':
                stats['cache_hits'] += 1
            elif stat_type == 'cache_miss':
                stats['cache_misses'] += 1
    
    def _update_stats(self, validators: List[BaseValidator], execution_time: float, use_cache: bool):
        """更新全局统计"""
        with self.lock:
            for validator in validators:
                stats = self.validation_stats[validator.name]
                stats['total_validations'] += 1
                stats['total_time'] += execution_time
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        with self.lock:
            stats = {
                'validator_stats': dict(self.validation_stats),
                'cache_stats': self.cache.get_stats() if self.cache else None,
                'engine_stats': self.engine.get_stats()
            }
            
            # 计算总体统计
            total_validations = sum(
                s['total_validations'] for s in self.validation_stats.values()
            )
            total_time = sum(
                s['total_time'] for s in self.validation_stats.values()
            )
            total_cache_hits = sum(
                s['cache_hits'] for s in self.validation_stats.values()
            )
            total_cache_misses = sum(
                s['cache_misses'] for s in self.validation_stats.values()
            )
            
            stats['global_stats'] = {
                'total_validations': total_validations,
                'total_time': total_time,
                'avg_time': total_time / max(1, total_validations),
                'total_cache_hits': total_cache_hits,
                'total_cache_misses': total_cache_misses,
                'cache_hit_rate': (total_cache_hits / max(1, total_cache_hits + total_cache_misses)) * 100
            }
            
            return stats
    
    def clear_cache(self):
        """清空缓存"""
        if self.cache:
            self.cache.clear()
    
    def cleanup_cache(self):
        """清理过期缓存"""
        if self.cache:
            self.cache.cleanup_expired()
    
    def shutdown(self):
        """关闭优化器"""
        self.engine.shutdown()


class ValidationProfiler:
    """验证性能分析器"""
    
    def __init__(self):
        self.profiles: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.Lock()
    
    def profile_validation(self, validator_name: str, execution_time: float):
        """记录验证性能"""
        with self.lock:
            self.profiles[validator_name].append(execution_time)
            
            # 保留最近1000次记录
            if len(self.profiles[validator_name]) > 1000:
                self.profiles[validator_name] = self.profiles[validator_name][-1000:]
    
    def get_validator_profile(self, validator_name: str) -> Dict[str, Any]:
        """获取验证器性能分析"""
        with self.lock:
            times = self.profiles.get(validator_name, [])
            
            if not times:
                return {}
            
            import statistics
            
            return {
                'validator_name': validator_name,
                'sample_count': len(times),
                'avg_time': statistics.mean(times),
                'median_time': statistics.median(times),
                'min_time': min(times),
                'max_time': max(times),
                'std_deviation': statistics.stdev(times) if len(times) > 1 else 0,
                'p95': statistics.quantiles(times, n=20)[18] if len(times) > 20 else max(times),
                'p99': statistics.quantiles(times, n=100)[98] if len(times) > 100 else max(times)
            }
    
    def get_all_profiles(self) -> List[Dict[str, Any]]:
        """获取所有验证器性能分析"""
        return [
            self.get_validator_profile(validator_name)
            for validator_name in self.profiles.keys()
        ]
    
    def clear_profiles(self):
        """清空性能分析"""
        with self.lock:
            self.profiles.clear()


# 全局性能优化器
_global_optimizer = None

def get_validation_optimizer(enable_cache: bool = True, cache_size: int = 1000,
                         cache_ttl: float = 300.0, max_workers: int = 4,
                         use_processes: bool = False) -> ValidationPerformanceOptimizer:
    """获取全局验证优化器"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = ValidationPerformanceOptimizer(
            enable_cache=enable_cache,
            cache_size=cache_size,
            cache_ttl=cache_ttl,
            max_workers=max_workers,
            use_processes=use_processes
        )
    return _global_optimizer

def validate_with_optimization(validators: List[BaseValidator], data: Any,
                           context: ValidationContext, use_cache: Optional[bool] = None,
                           parallel: bool = True) -> List[ValidationResult]:
    """使用优化器进行验证"""
    optimizer = get_validation_optimizer()
    return optimizer.validate_with_optimization(
        validators, data, context, use_cache, parallel
    )

async def validate_async_with_optimization(validators: List[BaseValidator], data: Any,
                                       context: ValidationContext,
                                       use_cache: Optional[bool] = None) -> List[ValidationResult]:
    """异步优化验证"""
    optimizer = get_validation_optimizer()
    return await optimizer.validate_async_with_optimization(
        validators, data, context, use_cache
    )
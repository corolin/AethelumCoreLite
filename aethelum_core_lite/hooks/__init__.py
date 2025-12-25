"""
Hook模块

包含各种钩子函数的定义和实现，以及Hook链管理和性能优化功能。
"""

from .base_hook import (
    BaseHook, SimpleHook, FilterHook, PreHook, PostHook, ErrorHook, 
    ConditionalHook, AsyncHook, MetricsHook, SecurityHook,
    create_simple_hook, create_filter_hook, create_pre_hook, 
    create_post_hook, create_error_hook
)

from .hook_chain import HookChain, HookChainManager, get_hook_manager
from .performance_optimizer import (
    PerformanceOptimizer, PerformanceMonitor, PerformanceMetrics, 
    HookCache, AsyncHookExecutor, get_performance_optimizer
)

__all__ = [
    # 基础Hook类
    "BaseHook", "SimpleHook", "FilterHook", "PreHook", "PostHook", 
    "ErrorHook", "ConditionalHook", "AsyncHook", "MetricsHook", "SecurityHook",
    
    # 便捷创建函数
    "create_simple_hook", "create_filter_hook", "create_pre_hook", 
    "create_post_hook", "create_error_hook",
    
    # Hook链管理
    "HookChain", "HookChainManager", "get_hook_manager",
    
    # 性能优化
    "PerformanceOptimizer", "PerformanceMonitor", "PerformanceMetrics", 
    "HookCache", "AsyncHookExecutor", "get_performance_optimizer"
]
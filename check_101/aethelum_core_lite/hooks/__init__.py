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
    "HookCache", "AsyncHookExecutor", "get_performance_optimizer",

    # 默认处理器
    "create_default_error_handler"
]


def create_default_error_handler():
    """
    创建默认错误处理Hook

    Returns:
        Callable: 错误处理函数
    """
    def handle_error(impulse, source_queue):
        """默认错误处理函数"""
        import logging
        logger = logging.getLogger("DefaultErrorHandler")
        logger.error(
            f"错误队列处理: session_id={impulse.session_id}, "
            f"source_queue={source_queue}, "
            f"action_intent={impulse.action_intent}"
        )
        # 将消息路由到完成队列
        impulse.action_intent = "Q_DONE"
        return impulse

    return handle_error
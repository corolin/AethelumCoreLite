"""
基础钩子 (BaseHook)

提供Hook函数的基础抽象类和工具函数。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from ..core.message import NeuralImpulse


class BaseHook(ABC):
    """
    基础钩子抽象类

    定义了所有Hook函数必须实现的接口，提供通用的Hook功能。
    """

    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        """
        初始化基础钩子

        Args:
            hook_name: Hook名称
            enable_logging: 是否启用日志记录
            priority: Hook优先级（0-100，数值越小优先级越高）
        """
        self.hook_name = hook_name
        self.enabled = True
        self.priority = priority
        self.logger = logging.getLogger(f"hook.{hook_name}")
        self.hook_type = "base"

        # 统计信息
        self._stats = {
            'total_processed': 0,
            'total_errors': 0,
            'total_skipped': 0,
            'avg_processing_time': 0.0,
            'last_processed_at': None,
            'execution_count': 0,
            'total_execution_time': 0.0
        }

    @abstractmethod
    def process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        处理神经脉冲的抽象方法

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现process方法")

    def __call__(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        使Hook函数可调用

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        return self.execute(impulse, source_queue)

    def execute(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        执行Hook函数，包含错误处理和统计

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        import time

        if not self.enabled:
            self.logger.debug(f"Hook {self.hook_name} 已禁用，跳过处理")
            self._stats['total_skipped'] += 1
            return impulse

        start_time = time.time()

        try:
            # 调用子类实现的process方法
            result = self.process(impulse, source_queue)

            # 更新统计信息
            processing_time = time.time() - start_time
            self._update_stats(processing_time, success=True)

            self.logger.debug(f"Hook {self.hook_name} 处理完成: {impulse.session_id[:8]}...")
            return result

        except Exception as e:
            # 错误处理
            self.logger.error(f"Hook {self.hook_name} 处理失败: {e}")

            # 更新统计信息
            processing_time = time.time() - start_time
            self._update_stats(processing_time, success=False)

            # 将错误信息添加到脉冲元数据
            impulse.metadata[f'hook_error_{self.hook_name}'] = {
                'error': str(e),
                'hook_name': self.hook_name,
                'source_queue': source_queue
            }

            return impulse

    def _update_stats(self, processing_time: float, success: bool) -> None:
        """更新统计信息"""
        import time

        with self:
            self._stats['total_processed'] += 1
            if not success:
                self._stats['total_errors'] += 1

            # 更新平均处理时间
            if self._stats['total_processed'] > 0:
                self._stats['avg_processing_time'] = (
                    (self._stats['avg_processing_time'] * (self._stats['total_processed'] - 1) + processing_time) /
                    self._stats['total_processed']
                )

            self._stats['last_processed_at'] = time.time()

    def enable(self) -> None:
        """启用Hook"""
        self.enabled = True
        self.logger.info(f"Hook {self.hook_name} 已启用")

    def disable(self) -> None:
        """禁用Hook"""
        self.enabled = False
        self.logger.info(f"Hook {self.hook_name} 已禁用")

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            'total_processed': 0,
            'total_errors': 0,
            'total_skipped': 0,
            'avg_processing_time': 0.0,
            'last_processed_at': None
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self:
            return {
                **self._stats,
                'hook_name': self.hook_name,
                'enabled': self.enabled,
                'error_rate': (
                    self._stats['total_errors'] / max(1, self._stats['total_processed'])
                ) if self._stats['total_processed'] > 0 else 0.0
            }

    def get_hook_info(self) -> Dict[str, Any]:
        """获取Hook信息"""
        return {
            'hook_name': self.hook_name,
            'hook_type': self.__class__.__name__,
            'enabled': self.enabled,
            'stats': self.get_stats()
        }

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        pass

    def __str__(self) -> str:
        """字符串表示"""
        status = "启用" if self.enabled else "禁用"
        return f"BaseHook(name='{self.hook_name}', status={status})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"BaseHook(name='{self.hook_name}', type={self.__class__.__name__}, "
                f"enabled={self.enabled}, processed={self._stats['total_processed']})")


class SimpleHook(BaseHook):
    """
    简单Hook实现

    提供一个简单的Hook实现示例，可以直接传入处理函数。
    """

    def __init__(
        self,
        hook_name: str,
        process_function: callable,
        enable_logging: bool = True
    ):
        """
        初始化简单Hook

        Args:
            hook_name: Hook名称
            process_function: 处理函数，签名为 (impulse, source_queue) -> impulse
            enable_logging: 是否启用日志记录
        """
        super().__init__(hook_name, enable_logging)
        self.process_function = process_function

    def process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        处理神经脉冲

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        return self.process_function(impulse, source_queue)


class FilterHook(BaseHook):
    """
    过滤Hook

    根据条件过滤神经脉冲，可以选择性丢弃或修改脉冲。
    """

    def __init__(
        self,
        hook_name: str,
        filter_function: callable,
        drop_on_match: bool = False,
        enable_logging: bool = True
    ):
        """
        初始化过滤Hook

        Args:
            hook_name: Hook名称
            filter_function: 过滤函数，签名为 (impulse, source_queue) -> bool
            drop_on_match: 匹配时是否丢弃脉冲
            enable_logging: 是否启用日志记录
        """
        super().__init__(hook_name, enable_logging)
        self.filter_function = filter_function
        self.drop_on_match = drop_on_match

    def process(self, impulse: NeuralImpulse, source_queue: str) -> Optional[NeuralImpulse]:
        """
        处理神经脉冲

        Args:
            impulse: 输入的神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲，如果丢弃则返回None
        """
        should_filter = self.filter_function(impulse, source_queue)

        if should_filter:
            if self.drop_on_match:
                self.logger.debug(f"过滤Hook丢弃脉冲: {impulse.session_id[:8]}...")
                return None
            else:
                # 可以在这里修改脉冲
                impulse.metadata[f'filtered_by_{self.hook_name}'] = True
                return impulse

        return impulse


def create_simple_hook(hook_name: str, process_function: callable) -> SimpleHook:
    """
    创建简单Hook的便捷函数

    Args:
        hook_name: Hook名称
        process_function: 处理函数

    Returns:
        SimpleHook: 简单Hook实例
    """
    return SimpleHook(hook_name, process_function)


def create_filter_hook(hook_name: str, filter_function: callable, drop_on_match: bool = False) -> FilterHook:
    """
    创建过滤Hook的便捷函数

    Args:
        hook_name: Hook名称
        filter_function: 过滤函数
        drop_on_match: 匹配时是否丢弃脉冲

    Returns:
        FilterHook: 过滤Hook实例
    """
    return FilterHook(hook_name, filter_function, drop_on_match)


class PreHook(BaseHook):
    """
    前置Hook - 在主处理逻辑执行前运行
    """
    
    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "pre"
    
    @abstractmethod
    def pre_process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """
        前置处理方法
        
        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称
            
        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        pass
    
    def process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """实现基类的process方法，调用pre_process"""
        return self.pre_process(impulse, source_queue)


class PostHook(BaseHook):
    """
    后置Hook - 在主处理逻辑执行后运行
    """
    
    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "post"
    
    @abstractmethod
    def post_process(self, impulse: 'NeuralImpulse', source_queue: str, result: Any = None) -> 'NeuralImpulse':
        """
        后置处理方法
        
        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称
            result: 主处理逻辑的执行结果
            
        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        pass
    
    def process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """实现基类的process方法，调用post_process"""
        return self.post_process(impulse, source_queue)


class ErrorHook(BaseHook):
    """
    异常Hook - 当发生错误时运行
    """
    
    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "error"
    
    @abstractmethod
    def handle_error(self, impulse: 'NeuralImpulse', source_queue: str, error: Exception) -> 'NeuralImpulse':
        """
        错误处理方法
        
        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称
            error: 发生的异常
            
        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        pass
    
    def process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """ErrorHook通常不直接调用process，而是通过handle_error"""
        raise NotImplementedError("ErrorHook应该通过handle_error方法调用")


class ConditionalHook(BaseHook):
    """
    条件Hook - 根据条件决定是否执行
    """
    
    def __init__(self, hook_name: str, condition_function: callable, 
                 target_hook: BaseHook, enable_logging: bool = True, priority: int = 50):
        """
        初始化条件Hook
        
        Args:
            hook_name: Hook名称
            condition_function: 条件判断函数，返回bool
            target_hook: 条件满足时要执行的Hook
            enable_logging: 是否启用日志记录
            priority: 优先级
        """
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "conditional"
        self.condition_function = condition_function
        self.target_hook = target_hook
    
    def process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """根据条件执行目标Hook"""
        if self.condition_function(impulse, source_queue):
            self.logger.debug(f"条件满足，执行Hook: {self.target_hook.hook_name}")
            return self.target_hook.process(impulse, source_queue)
        else:
            self.logger.debug(f"条件不满足，跳过Hook: {self.target_hook.hook_name}")
            return impulse


class AsyncHook(BaseHook):
    """
    异步Hook - 支持异步执行
    """
    
    def __init__(self, hook_name: str, enable_logging: bool = True, priority: int = 50):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "async"
    
    @abstractmethod
    async def async_process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """
        异步处理方法
        
        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称
            
        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        pass
    
    def process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """同步调用异步方法"""
        import asyncio
        
        try:
            # 检查是否在事件循环中
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在事件循环中，创建任务
                self.logger.warning("AsyncHook在同步上下文中执行，使用run_coroutine_threadsafe")
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.async_process(impulse, source_queue))
                    return future.result()
            else:
                # 如果不在事件循环中，直接运行
                return asyncio.run(self.async_process(impulse, source_queue))
        except Exception as e:
            self.logger.error(f"异步Hook执行失败: {e}")
            return impulse


class MetricsHook(BaseHook):
    """
    指标Hook - 用于收集和报告指标
    """
    
    def __init__(self, hook_name: str, metrics_collector: callable = None, 
                 enable_logging: bool = True, priority: int = 90):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "metrics"
        self.metrics_collector = metrics_collector or self._default_collector
        self.custom_metrics = {}
    
    def _default_collector(self, impulse: 'NeuralImpulse', source_queue: str) -> Dict[str, Any]:
        """默认指标收集器"""
        return {
            'session_id': impulse.session_id,
            'source_agent': impulse.source_agent,
            'action_intent': impulse.action_intent,
            'timestamp': impulse.timestamp,
            'metadata_count': len(impulse.metadata) if impulse.metadata else 0,
            'routing_history_length': len(impulse.routing_history) if impulse.routing_history else 0
        }
    
    def process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """收集指标"""
        try:
            metrics = self.metrics_collector(impulse, source_queue)
            
            # 添加自定义指标
            metrics.update(self.custom_metrics)
            
            # 将指标存储到脉冲元数据中
            impulse.metadata[f'metrics_{self.hook_name}'] = {
                'timestamp': int(__import__('time').time()),
                'metrics': metrics
            }
            
            self.logger.debug(f"收集指标: {len(metrics)} 项")
            
        except Exception as e:
            self.logger.error(f"指标收集失败: {e}")
            
        return impulse
    
    def add_custom_metric(self, name: str, value: Any):
        """添加自定义指标"""
        self.custom_metrics[name] = value


class SecurityHook(BaseHook):
    """
    安全Hook - 用于安全检查和控制
    """
    
    def __init__(self, hook_name: str, security_rules: list = None, 
                 enable_logging: bool = True, priority: int = 10):
        super().__init__(hook_name, enable_logging, priority)
        self.hook_type = "security"
        self.security_rules = security_rules or []
        self.blocked_count = 0
    
    def add_security_rule(self, rule_name: str, rule_function: callable):
        """添加安全规则"""
        self.security_rules.append({
            'name': rule_name,
            'function': rule_function
        })
    
    def process(self, impulse: 'NeuralImpulse', source_queue: str) -> 'NeuralImpulse':
        """执行安全检查"""
        for rule in self.security_rules:
            try:
                result = rule['function'](impulse, source_queue)
                
                if isinstance(result, tuple) and len(result) == 2:
                    is_valid, message = result
                else:
                    is_valid = bool(result)
                    message = f"安全规则 '{rule['name']}' 检查失败"
                
                if not is_valid:
                    self.blocked_count += 1
                    self.logger.warning(f"安全检查失败: {message}")
                    
                    # 添加安全违规信息
                    impulse.metadata[f'security_violation_{rule["name"]}'] = {
                        'timestamp': int(__import__('time').time()),
                        'message': message,
                        'blocked_count': self.blocked_count
                    }
                    
                    # 可以选择阻止处理或仅记录
                    if hasattr(impulse, 'action_intent'):
                        impulse.action_intent = "SECURITY_BLOCKED"
                        
            except Exception as e:
                self.logger.error(f"安全规则 '{rule['name']}' 执行失败: {e}")
        
        return impulse


# 便捷函数
def create_pre_hook(hook_name: str, pre_process_function: callable, 
                    enable_logging: bool = True, priority: int = 50) -> PreHook:
    """创建前置Hook的便捷函数"""
    class SimplePreHook(PreHook):
        def __init__(self, name, process_func, logging=True, pri=50):
            super().__init__(name, logging, pri)
            self.process_func = process_func
        
        def pre_process(self, impulse, source_queue):
            return self.process_func(impulse, source_queue)
    
    return SimplePreHook(hook_name, pre_process_function, enable_logging, priority)


def create_post_hook(hook_name: str, post_process_function: callable, 
                     enable_logging: bool = True, priority: int = 50) -> PostHook:
    """创建后置Hook的便捷函数"""
    class SimplePostHook(PostHook):
        def __init__(self, name, process_func, logging=True, pri=50):
            super().__init__(name, logging, pri)
            self.process_func = process_func
        
        def post_process(self, impulse, source_queue, result=None):
            return self.process_func(impulse, source_queue, result)
    
    return SimplePostHook(hook_name, post_process_function, enable_logging, priority)


def create_error_hook(hook_name: str, error_handler_function: callable, 
                      enable_logging: bool = True, priority: int = 10) -> ErrorHook:
    """创建错误Hook的便捷函数"""
    class SimpleErrorHook(ErrorHook):
        def __init__(self, name, handler_func, logging=True, pri=10):
            super().__init__(name, logging, pri)
            self.handler_func = handler_func
        
        def handle_error(self, impulse, source_queue, error):
            return self.handler_func(impulse, source_queue, error)
    
    return SimpleErrorHook(hook_name, error_handler_function, enable_logging, priority)
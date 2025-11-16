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

    def __init__(self, hook_name: str, enable_logging: bool = True):
        """
        初始化基础钩子

        Args:
            hook_name: Hook名称
            enable_logging: 是否启用日志记录
        """
        self.hook_name = hook_name
        self.enabled = True
        self.logger = logging.getLogger(f"hook.{hook_name}")

        # 统计信息
        self._stats = {
            'total_processed': 0,
            'total_errors': 0,
            'total_skipped': 0,
            'avg_processing_time': 0.0,
            'last_processed_at': None
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
"""
默认钩子模块

提供常用的默认处理钩子函数和 BaseHook 类
"""

import logging
import time
import threading
from typing import Callable, Optional, Any, Dict, List
from .message import NeuralImpulse


class BaseHook:
    """
    钩子基类
    提供钩子的通用接口和统计功能
    """

    def __init__(self, name: Optional[str] = None):
        """
        初始化钩子

        Args:
            name: 钩子名称，默认使用类名
        """
        self.name = name or self.__class__.__name__
        self._call_count = 0
        self._success_count = 0
        self._error_count = 0
        self._total_execution_time = 0.0
        self._lock = threading.Lock()
        self._last_execution_time: Optional[float] = None

    def __call__(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        调用钩子（子类需要实现此方法）

        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        raise NotImplementedError("Subclasses must implement __call__")

    def execute(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        执行钩子并记录统计信息

        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        start_time = time.time()
        try:
            result = self(impulse, source_queue)
            execution_time = time.time() - start_time

            with self._lock:
                self._call_count += 1
                self._success_count += 1
                self._total_execution_time += execution_time
                self._last_execution_time = execution_time

            return result
        except Exception as e:
            execution_time = time.time() - start_time

            with self._lock:
                self._call_count += 1
                self._error_count += 1
                self._total_execution_time += execution_time
                self._last_execution_time = execution_time

            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        获取钩子统计信息

        Returns:
            Dict: 统计信息
        """
        with self._lock:
            return {
                'name': self.name,
                'call_count': self._call_count,
                'success_count': self._success_count,
                'error_count': self._error_count,
                'total_execution_time': self._total_execution_time,
                'average_execution_time': (
                    self._total_execution_time / self._call_count
                    if self._call_count > 0
                    else 0.0
                ),
                'last_execution_time': self._last_execution_time,
            }

    def reset_stats(self):
        """重置统计信息"""
        with self._lock:
            self._call_count = 0
            self._success_count = 0
            self._error_count = 0
            self._total_execution_time = 0.0
            self._last_execution_time = None


def create_default_error_handler():
    """
    创建默认错误处理器钩子

    Returns:
        Callable: 错误处理钩子函数
    """
    logger = logging.getLogger("DefaultErrorHandler")

    def handle_error(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理错误脉冲"""
        error_message = impulse.metadata.get('error_message', 'Unknown error')
        error_source = impulse.metadata.get('error_source', 'Unknown')
        original_session_id = impulse.metadata.get('original_session_id', 'Unknown')

        logger.error(f"错误处理器接收到的错误 - 来源: {error_source}, 消息: {error_message}, 原始会话ID: {original_session_id}, 错误脉冲ID: {impulse.session_id}")

        # 更新源Agent记录
        impulse.update_source("ErrorHandler")

        # 清除action_intent以防止自动路由（Q_ERROR_HANDLER是终点）
        impulse.action_intent = "Done"
        return impulse

    return handle_error


def create_default_response_handler():
    """
    创建默认响应处理器钩子

    Returns:
        Callable: 响应处理钩子函数
    """
    logger = logging.getLogger("DefaultResponseHandler")

    def handle_response(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理响应脉冲"""
        readable_content = ""
        # 尝试获取响应内容
        try:
            readable_content = impulse.get_text_content()
            logger.debug(f"收到响应: '{readable_content}'")
        except Exception as e:
            logger.error(f"提取响应内容失败: {e}")
            readable_content = f"响应内容提取失败: {str(e)}"
        impulse.action_intent = "Done"
        return impulse

    return handle_response
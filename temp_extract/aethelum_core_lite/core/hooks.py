"""
默认钩子模块

提供常用的默认处理钩子函数

注意: BaseHook 类已移动到 hooks/base_hook.py，请从那里导入
"""

import logging
from typing import Callable
from .message import NeuralImpulse

# BaseHook 现在从 hooks/base_hook.py 导入（更完整的实现）
from ..hooks.base_hook import BaseHook


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
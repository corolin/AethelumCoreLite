"""
异步错误处理器

提供异步版本的错误分类、处理和路由功能。
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class AsyncErrorType(Enum):
    """异步错误类型枚举"""
    VALIDATION_ERROR = "validation_error"
    PROCESS_ERROR = "process_error"
    ROUTING_ERROR = "routing_error"
    TIMEOUT_ERROR = "timeout_error"
    RESOURCE_ERROR = "resource_error"
    SECURITY_ERROR = "security_error"
    HOOK_ERROR = "hook_error"


@dataclass
class ErrorContext:
    """错误上下文"""
    worker_id: Optional[str] = None
    queue_id: Optional[str] = None
    stage: Optional[str] = None
    timestamp: float = 0.0
    additional_info: Dict[str, Any] = None

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if self.additional_info is None:
            self.additional_info = {}


class AsyncErrorHandler:
    """
    异步错误处理器

    负责错误分类、处理和路由到错误队列。
    """

    def __init__(self, router: 'AsyncNeuralSomaRouter'):
        """
        初始化异步错误处理器

        Args:
            router: 异步路由器引用
        """
        self.router = router
        self._error_stats = {
            error_type: 0
            for error_type in AsyncErrorType
        }
        self._lock = asyncio.Lock()

    async def handle_error(
        self,
        error: Exception,
        impulse: Any,
        context: ErrorContext
    ) -> bool:
        """
        处理错误

        Args:
            error: 异常对象
            impulse: 神经脉冲
            context: 错误上下文

        Returns:
            bool: True表示处理成功
        """
        # 分类错误
        error_type = self._classify_error(error, context)

        # 更新统计
        async with self._lock:
            self._error_stats[error_type] += 1

        # 记录错误
        logger.error(
            f"[ErrorHandler] 类型: {error_type.value}, "
            f"消息: {str(error)}, "
            f"上下文: {context}"
        )

        # 创建错误脉冲
        error_impulse = await self._create_error_impulse(
            error, impulse, error_type, context
        )

        # 路由到错误处理队列
        try:
            # 尝试路由到Q_ERROR_HANDLER
            if "Q_ERROR_HANDLER" in self.router._queues:
                await self.router.route_message(
                    error_impulse,
                    "Q_ERROR_HANDLER"
                )
                return True
            else:
                logger.warning(
                    "[ErrorHandler] Q_ERROR_HANDLER队列不存在，"
                    "无法路由错误脉冲"
                )
                return False

        except Exception as e:
            logger.error(f"[ErrorHandler] 无法路由错误脉冲: {e}")
            return False

    def _classify_error(
        self,
        error: Exception,
        context: ErrorContext
    ) -> AsyncErrorType:
        """
        分类错误

        Args:
            error: 异常对象
            context: 错误上下文

        Returns:
            AsyncErrorType: 错误类型
        """
        # 异步超时错误
        if isinstance(error, asyncio.TimeoutError):
            return AsyncErrorType.TIMEOUT_ERROR

        # 根据错误消息和上下文分类
        error_msg = str(error).lower()

        if "validation" in error_msg or "验证" in error_msg:
            return AsyncErrorType.VALIDATION_ERROR
        elif "security" in error_msg or "permission" in error_msg or "权限" in error_msg:
            return AsyncErrorType.SECURITY_ERROR
        elif "routing" in context.stage or "路由" in str(context.stage):
            return AsyncErrorType.ROUTING_ERROR
        elif "hook" in context.stage or context.stage == "hook":
            return AsyncErrorType.HOOK_ERROR
        elif "timeout" in error_msg or "超时" in error_msg:
            return AsyncErrorType.TIMEOUT_ERROR
        elif "resource" in error_msg or "资源" in error_msg:
            return AsyncErrorType.RESOURCE_ERROR
        else:
            return AsyncErrorType.PROCESS_ERROR

    async def _create_error_impulse(
        self,
        error: Exception,
        original_impulse: Any,
        error_type: AsyncErrorType,
        context: ErrorContext
    ) -> Any:
        """
        创建错误脉冲

        Args:
            error: 异常对象
            original_impulse: 原始脉冲
            error_type: 错误类型
            context: 错误上下文

        Returns:
            NeuralImpulse: 错误脉冲
        """
        from .message import NeuralImpulse

        # 提取原始脉冲信息
        original_session_id = getattr(original_impulse, 'session_id', 'unknown')
        original_source = getattr(original_impulse, 'source_agent', 'unknown')

        # 创建错误脉冲
        error_impulse = NeuralImpulse(
            content=str(error),
            action_intent="Q_ERROR_HANDLER"
        )
        error_impulse.metadata.update({
            "error_type": error_type.value,
            "error_message": str(error),
            "original_session_id": original_session_id,
            "original_source": original_source,
            "error_context": {
                "worker_id": context.worker_id,
                "queue_id": context.queue_id,
                "stage": context.stage,
                "timestamp": context.timestamp
            },
            "timestamp": time.time()
        })

        return error_impulse

    async def get_error_stats(self) -> Dict[str, int]:
        """
        获取错误统计

        Returns:
            Dict[str, int]: 错误统计
        """
        async with self._lock:
            return {
                error_type.value: count
                for error_type, count in self._error_stats.items()
            }

    async def reset_stats(self):
        """重置错误统计"""
        async with self._lock:
            for error_type in self._error_stats:
                self._error_stats[error_type] = 0

        logger.info("[ErrorHandler] 错误统计已重置")

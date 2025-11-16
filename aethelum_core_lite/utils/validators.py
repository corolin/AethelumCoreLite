"""
验证工具模块

提供消息包和系统的验证功能。
"""

import re
from typing import Any, Dict, List, Optional, Union
from ..core.message import NeuralImpulse


class ValidationError(Exception):
    """验证错误异常"""
    pass


class NeuralImpulseValidator:
    """神经脉冲验证器"""

    # 必需字段
    REQUIRED_FIELDS = {
        'session_id': str,
        'action_intent': str,
        'source_agent': str,
        'input_source': str
    }

    # 有效的action_intent列表
    VALID_ACTION_INTENTS = {
        'Q_AUDIT_INPUT',
        'Q_AUDIT_OUTPUT',
        'Q_AUDITED_INPUT',
        'Q_RESPONSE_SINK',
        'Q_ERROR_HANDLER'
    }

    # 有效的input_source列表
    VALID_INPUT_SOURCES = {
        'USER', 'API', 'WEBSOCKET', 'CLI', 'SYSTEM', 'INTERNAL'
    }

    @classmethod
    def validate(cls, impulse: NeuralImpulse, strict: bool = False) -> List[str]:
        """
        验证神经脉冲

        Args:
            impulse: 神经脉冲对象
            strict: 是否启用严格模式验证

        Returns:
            List[str]: 验证错误列表，空列表表示验证通过

        Raises:
            ValidationError: 如果验证失败且strict为True
        """
        errors = []

        # 转换为字典进行验证
        impulse_dict = impulse.to_dict()

        # 验证必需字段
        for field, field_type in cls.REQUIRED_FIELDS.items():
            if field not in impulse_dict or impulse_dict[field] is None:
                errors.append(f"缺少必需字段: {field}")
            elif not isinstance(impulse_dict[field], field_type):
                errors.append(f"字段 {field} 类型错误，期望 {field_type.__name__}，实际 {type(impulse_dict[field]).__name__}")

        # 验证session_id格式
        if 'session_id' in impulse_dict and impulse_dict['session_id']:
            if not cls._validate_session_id(impulse_dict['session_id']):
                errors.append("session_id 格式无效")

        # 验证action_intent
        if 'action_intent' in impulse_dict and impulse_dict['action_intent']:
            if strict and impulse_dict['action_intent'] not in cls.VALID_ACTION_INTENTS:
                errors.append(f"无效的action_intent: {impulse_dict['action_intent']}")

        # 验证input_source
        if 'input_source' in impulse_dict and impulse_dict['input_source']:
            if impulse_dict['input_source'] not in cls.VALID_INPUT_SOURCES:
                errors.append(f"无效的input_source: {impulse_dict['input_source']}")

        # 验证routing_history
        if 'routing_history' in impulse_dict and impulse_dict['routing_history']:
            if not isinstance(impulse_dict['routing_history'], list):
                errors.append("routing_history 必须是列表类型")
            elif not all(isinstance(item, str) for item in impulse_dict['routing_history']):
                errors.append("routing_history 中的所有元素必须是字符串")

        # 验证metadata
        if 'metadata' in impulse_dict and impulse_dict['metadata']:
            if not isinstance(impulse_dict['metadata'], dict):
                errors.append("metadata 必须是字典类型")

        # 验证timestamp
        if 'timestamp' in impulse_dict and impulse_dict['timestamp']:
            if not isinstance(impulse_dict['timestamp'], (int, float)):
                errors.append("timestamp 必须是数字类型")

        # 严格模式下抛出异常
        if strict and errors:
            raise ValidationError(f"神经脉冲验证失败: {'; '.join(errors)}")

        return errors

    @staticmethod
    def _validate_session_id(session_id: str) -> bool:
        """验证session_id格式"""
        if not session_id or not isinstance(session_id, str):
            return False

        # 简单的UUID格式验证或长度验证
        if len(session_id) < 8:
            return False

        # 可以添加更复杂的格式验证
        return True

    @staticmethod
    def validate_session_id_format(session_id: str) -> bool:
        """验证session_id是否为有效的UUID格式"""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(session_id))

    @staticmethod
    def sanitize_string(input_string: str, max_length: int = 1000) -> str:
        """
        清理字符串

        Args:
            input_string: 输入字符串
            max_length: 最大长度

        Returns:
            str: 清理后的字符串
        """
        if not isinstance(input_string, str):
            return str(input_string)

        # 移除控制字符
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', input_string)

        # 限制长度
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        return sanitized.strip()


class QueueValidator:
    """队列验证器"""

    @staticmethod
    def validate_queue_name(name: str) -> bool:
        """
        验证队列名称

        Args:
            name: 队列名称

        Returns:
            bool: 是否有效
        """
        if not name or not isinstance(name, str):
            return False

        # 队列名称规则：字母、数字、下划线，以字母开头
        pattern = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
        return bool(pattern.match(name))

    @staticmethod
    def validate_hook_function(hook_func: Any) -> bool:
        """
        验证Hook函数

        Args:
            hook_func: Hook函数

        Returns:
            bool: 是否有效
        """
        if not callable(hook_func):
            return False

        # 可以添加更复杂的函数签名验证
        return True


class SystemValidator:
    """系统验证器"""

    @staticmethod
    def validate_router_configuration(
        queues: Dict[str, Any],
        hooks: Dict[str, Any]
    ) -> List[str]:
        """
        验证路由器配置

        Args:
            queues: 队列字典
            hooks: Hook字典

        Returns:
            List[str]: 验证错误列表
        """
        errors = []

        # 验证强制性队列
        mandatory_queues = {'Q_AUDIT_INPUT', 'Q_AUDIT_OUTPUT', 'Q_RESPONSE_SINK'}
        missing_queues = mandatory_queues - set(queues.keys())
        if missing_queues:
            errors.append(f"缺少强制性队列: {missing_queues}")

        # 验证Hook注册
        forbidden_hook_queues = {'Q_AUDIT_INPUT', 'Q_AUDIT_OUTPUT'}
        invalid_hooks = set(hooks.keys()) & forbidden_hook_queues
        if invalid_hooks:
            errors.append(f"禁止向这些队列注册Hook: {invalid_hooks}")

        return errors

    @staticmethod
    def validate_system_health(router: Any) -> Dict[str, Any]:
        """
        验证系统健康状态

        Args:
            router: 路由器实例

        Returns:
            Dict[str, Any]: 健康状态报告
        """
        health_status = {
            'status': 'healthy',
            'issues': [],
            'stats': {}
        }

        try:
            # 获取统计信息
            stats = router.get_stats()
            health_status['stats'] = {
                'queue_count': stats.get('queue_count', 0),
                'worker_count': stats.get('worker_count', 0),
                'total_impulses': stats.get('total_impulses_processed', 0),
                'is_active': stats.get('is_active', False)
            }

            # 检查队列状态
            queue_sizes = router.get_queue_sizes()
            for queue_name, size in queue_sizes.items():
                if size > 1000:  # 队列积压过多
                    health_status['issues'].append(f"队列 {queue_name} 积压过多: {size}")

            # 检查强制性队列
            mandatory_queues = {'Q_AUDIT_INPUT', 'Q_AUDIT_OUTPUT', 'Q_RESPONSE_SINK'}
            existing_queues = set(router.list_queues())
            missing_mandatory = mandatory_queues - existing_queues
            if missing_mandatory:
                health_status['issues'].append(f"缺少强制性队列: {missing_mandatory}")

            # 确定健康状态
            if health_status['issues']:
                health_status['status'] = 'unhealthy'

        except Exception as e:
            health_status['status'] = 'error'
            health_status['issues'].append(f"健康检查失败: {e}")

        return health_status


def validate_message_package(impulse: NeuralImpulse, strict: bool = False) -> bool:
    """
    验证消息包（向后兼容函数）

    Args:
        impulse: 神经脉冲对象
        strict: 是否启用严格模式

    Returns:
        bool: 验证是否通过
    """
    try:
        errors = NeuralImpulseValidator.validate(impulse, strict)
        return len(errors) == 0
    except ValidationError:
        return False


# 便捷验证函数
def is_valid_session_id(session_id: str) -> bool:
    """检查session_id是否有效"""
    return NeuralImpulseValidator._validate_session_id(session_id)


def is_valid_queue_name(name: str) -> bool:
    """检查队列名称是否有效"""
    return QueueValidator.validate_queue_name(name)


def sanitize_user_input(input_text: str, max_length: int = 1000) -> str:
    """清理用户输入"""
    return NeuralImpulseValidator.sanitize_string(input_text, max_length)
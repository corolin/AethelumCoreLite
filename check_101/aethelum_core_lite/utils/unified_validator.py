"""
统一验证框架

提供可扩展的验证系统，支持多种验证器类型和自定义验证规则。
"""

import re
import json
import time
import threading
import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Union, Callable, Type, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum
from collections import defaultdict, deque
import concurrent.futures


class ValidationSeverity(Enum):
    """验证严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationStatus(Enum):
    """验证状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class ValidationResult:
    """验证结果"""
    status: ValidationStatus
    severity: ValidationSeverity = ValidationSeverity.ERROR
    message: str = ""
    field_name: str = ""
    field_path: str = ""  # 嵌套字段路径，如 "user.profile.email"
    actual_value: Any = None
    expected_value: Any = None
    validator_name: str = ""
    validation_time: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'status': self.status.value,
            'severity': self.severity.value,
            'message': self.message,
            'field_name': self.field_name,
            'field_path': self.field_path,
            'actual_value': self._serialize_value(self.actual_value),
            'expected_value': self._serialize_value(self.expected_value),
            'validator_name': self.validator_name,
            'validation_time': self.validation_time,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }
    
    def _serialize_value(self, value: Any) -> Any:
        """序列化值"""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        else:
            return str(value)
    
    def is_success(self) -> bool:
        """是否验证成功"""
        return self.status == ValidationStatus.PASSED
    
    def is_failure(self) -> bool:
        """是否验证失败"""
        return self.status in [ValidationStatus.FAILED, ValidationStatus.CRITICAL]


@dataclass
class ValidationContext:
    """验证上下文"""
    data: Any
    field_path: str = ""
    parent_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    correlation_id: str = ""
    user_context: Dict[str, Any] = field(default_factory=dict)
    
    def get_field_path(self, field_name: str = "") -> str:
        """获取完整字段路径"""
        if field_name:
            if self.field_path:
                return f"{self.field_path}.{field_name}"
            return field_name
        return self.field_path
    
    def get_nested_context(self, field_name: str, field_data: Any) -> 'ValidationContext':
        """获取嵌套上下文"""
        return ValidationContext(
            data=field_data,
            field_path=self.get_field_path(field_name),
            parent_path=self.field_path,
            metadata=self.metadata.copy(),
            session_id=self.session_id,
            correlation_id=self.correlation_id,
            user_context=self.user_context.copy()
        )


class BaseValidator(ABC):
    """验证器基类"""
    
    def __init__(self, name: str, severity: ValidationSeverity = ValidationSeverity.ERROR):
        self.name = name
        self.severity = severity
        self.enabled = True
        self.execution_count = 0
        self.success_count = 0
        self.total_execution_time = 0.0
        self.lock = threading.Lock()
    
    @abstractmethod
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        """验证数据"""
        pass
    
    def _execute_validation(self, data: Any, context: ValidationContext) -> ValidationResult:
        """执行验证（包含统计）"""
        start_time = time.time()
        
        try:
            result = self.validate(data, context)
            result.validator_name = self.name
            result.validation_time = time.time() - start_time
            
            # 更新统计
            with self.lock:
                self.execution_count += 1
                self.total_execution_time += result.validation_time
                if result.is_success():
                    self.success_count += 1
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            with self.lock:
                self.execution_count += 1
                self.total_execution_time += execution_time
            
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"验证器执行异常: {str(e)}",
                validator_name=self.name,
                validation_time=execution_time
            )
    
    def enable(self):
        """启用验证器"""
        self.enabled = True
    
    def disable(self):
        """禁用验证器"""
        self.enabled = False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            success_rate = (self.success_count / max(1, self.execution_count)) * 100
            avg_time = self.total_execution_time / max(1, self.execution_count)
            
            return {
                'name': self.name,
                'enabled': self.enabled,
                'execution_count': self.execution_count,
                'success_count': self.success_count,
                'success_rate': success_rate,
                'total_execution_time': self.total_execution_time,
                'avg_execution_time': avg_time
            }


class RequiredValidator(BaseValidator):
    """必填验证器"""
    
    def __init__(self, name: str = "required", allow_empty: bool = False):
        super().__init__(name)
        self.allow_empty = allow_empty
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if data is None:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 不能为空",
                field_path=context.field_path,
                actual_value=None
            )
        
        if not self.allow_empty and data == "":
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 不能为空字符串",
                field_path=context.field_path,
                actual_value=data
            )
        
        if not self.allow_empty and isinstance(data, (list, dict)) and len(data) == 0:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 不能为空集合",
                field_path=context.field_path,
                actual_value=data
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class TypeValidator(BaseValidator):
    """类型验证器"""
    
    def __init__(self, expected_type: Type, name: str = "type"):
        super().__init__(name)
        self.expected_type = expected_type
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, self.expected_type):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 类型错误，期望 {self.expected_type.__name__}，实际 {type(data).__name__}",
                field_path=context.field_path,
                actual_value=type(data).__name__,
                expected_value=self.expected_type.__name__
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class RangeValidator(BaseValidator):
    """范围验证器"""
    
    def __init__(self, min_val: Any = None, max_val: Any = None, 
                 name: str = "range", inclusive: bool = True):
        super().__init__(name)
        self.min_val = min_val
        self.max_val = max_val
        self.inclusive = inclusive
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, (int, float)):
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"范围验证器只支持数字类型，跳过验证",
                field_path=context.field_path
            )
        
        errors = []
        
        if self.min_val is not None:
            if self.inclusive:
                if data < self.min_val:
                    errors.append(f"值 {data} 小于最小值 {self.min_val}")
            else:
                if data <= self.min_val:
                    errors.append(f"值 {data} 小于等于最小值 {self.min_val}")
        
        if self.max_val is not None:
            if self.inclusive:
                if data > self.max_val:
                    errors.append(f"值 {data} 大于最大值 {self.max_val}")
            else:
                if data >= self.max_val:
                    errors.append(f"值 {data} 大于等于最大值 {self.max_val}")
        
        if errors:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 范围验证失败: {'; '.join(errors)}",
                field_path=context.field_path,
                actual_value=data,
                expected_value=f"[{self.min_val}, {self.max_val}]"
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class LengthValidator(BaseValidator):
    """长度验证器"""
    
    def __init__(self, min_length: int = None, max_length: int = None,
                 name: str = "length"):
        super().__init__(name)
        self.min_length = min_length
        self.max_length = max_length
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not hasattr(data, '__len__'):
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"字段 {context.field_path} 没有长度属性，跳过长度验证",
                field_path=context.field_path
            )
        
        length = len(data)
        errors = []
        
        if self.min_length is not None and length < self.min_length:
            errors.append(f"长度 {length} 小于最小长度 {self.min_length}")
        
        if self.max_length is not None and length > self.max_length:
            errors.append(f"长度 {length} 大于最大长度 {self.max_length}")
        
        if errors:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 长度验证失败: {'; '.join(errors)}",
                field_path=context.field_path,
                actual_value=length,
                expected_value=f"[{self.min_length}, {self.max_length}]"
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class RegexValidator(BaseValidator):
    """正则表达式验证器"""
    
    def __init__(self, pattern: str, name: str = "regex", 
                 flags: int = 0, error_message: str = ""):
        super().__init__(name)
        self.pattern = pattern
        self.regex = re.compile(pattern, flags)
        self.error_message = error_message or f"值不匹配正则表达式 {pattern}"
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, str):
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"正则验证器只支持字符串类型，跳过验证",
                field_path=context.field_path
            )
        
        if not self.regex.match(data):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 正则验证失败: {self.error_message}",
                field_path=context.field_path,
                actual_value=data,
                expected_value=f"匹配模式: {self.pattern}"
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class EmailValidator(RegexValidator):
    """邮箱验证器"""
    
    def __init__(self, name: str = "email"):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        super().__init__(email_pattern, name, error_message="邮箱格式不正确")


class PhoneValidator(RegexValidator):
    """手机号验证器"""
    
    def __init__(self, pattern: str = None, name: str = "phone"):
        if pattern is None:
            pattern = r'^1[3-9]\d{9}$'  # 中国手机号
        super().__init__(pattern, name, error_message="手机号格式不正确")


class ChoicesValidator(BaseValidator):
    """选项验证器"""
    
    def __init__(self, choices: List[Any], name: str = "choices"):
        super().__init__(name)
        self.choices = choices
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if data not in self.choices:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 的值 {data} 不在允许的选项中",
                field_path=context.field_path,
                actual_value=data,
                expected_value=self.choices
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class CustomValidator(BaseValidator):
    """自定义验证器"""
    
    def __init__(self, validator_func: Callable[[Any, ValidationContext], bool],
                 error_message: str = "自定义验证失败", name: str = "custom"):
        super().__init__(name)
        self.validator_func = validator_func
        self.error_message = error_message
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        try:
            is_valid = self.validator_func(data, context)
            
            if not is_valid:
                return ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=self.severity,
                    message=f"字段 {context.field_path} 自定义验证失败: {self.error_message}",
                    field_path=context.field_path,
                    actual_value=data
                )
            
            return ValidationResult(status=ValidationStatus.PASSED)
            
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"字段 {context.field_path} 自定义验证异常: {str(e)}",
                field_path=context.field_path,
                actual_value=data
            )


class ConditionalValidator(BaseValidator):
    """条件验证器"""
    
    def __init__(self, condition_func: Callable[[Any, ValidationContext], bool],
                 validator: BaseValidator, name: str = "conditional"):
        super().__init__(name)
        self.condition_func = condition_func
        self.validator = validator
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        try:
            should_validate = self.condition_func(data, context)
            
            if not should_validate:
                return ValidationResult(
                    status=ValidationStatus.SKIPPED,
                    message=f"字段 {context.field_path} 条件不满足，跳过验证",
                    field_path=context.field_path
                )
            
            # 执行实际验证
            result = self.validator.validate(data, context)
            result.validator_name = self.name
            return result
            
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"字段 {context.field_path} 条件验证异常: {str(e)}",
                field_path=context.field_path
            )


class AsyncValidator(BaseValidator):
    """异步验证器"""
    
    def __init__(self, async_validator_func: Callable[[Any, ValidationContext], 
                  Union[bool, ValidationResult]], name: str = "async"):
        super().__init__(name)
        self.async_validator_func = async_validator_func
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_running_loop()
            
            if loop.is_running():
                # 在事件循环中，创建任务
                future = loop.create_task(self.async_validate(data, context))
                return future
            else:
                # 不在事件循环中，运行新的事件循环
                return asyncio.run(self.async_validate(data, context))
                
        except RuntimeError:
            # 没有事件循环，在线程池中运行
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(self.async_validate(data, context))
                )
                return future.result(timeout=30)  # 30秒超时
    
    async def async_validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        """异步验证方法"""
        try:
            result = await self.async_validator_func(data, context)
            
            if isinstance(result, ValidationResult):
                result.validator_name = self.name
                return result
            elif isinstance(result, bool):
                if not result:
                    return ValidationResult(
                        status=ValidationStatus.FAILED,
                        severity=self.severity,
                        message=f"字段 {context.field_path} 异步验证失败",
                        field_path=context.field_path,
                        actual_value=data
                    )
                return ValidationResult(status=ValidationStatus.PASSED)
            else:
                return ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"字段 {context.field_path} 异步验证器返回无效结果",
                    field_path=context.field_path
                )
                
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"字段 {context.field_path} 异步验证异常: {str(e)}",
                field_path=context.field_path
            )


class SchemaValidator(BaseValidator):
    """Schema验证器"""
    
    def __init__(self, schema: Dict[str, List[BaseValidator]], 
                 name: str = "schema", strict: bool = False):
        super().__init__(name)
        self.schema = schema
        self.strict = strict
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, dict):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"Schema验证器需要字典类型数据，实际类型: {type(data).__name__}",
                field_path=context.field_path,
                actual_value=type(data).__name__
            )
        
        results = []
        
        # 验证schema中定义的字段
        for field_name, validators in self.schema.items():
            field_value = data.get(field_name)
            field_context = context.get_nested_context(field_name, field_value)
            
            for validator in validators:
                if not validator.enabled:
                    continue
                    
                result = validator._execute_validation(field_value, field_context)
                result.field_name = field_name
                results.append(result)
        
        # 严格模式下检查额外字段
        if self.strict:
            for field_name in data.keys():
                if field_name not in self.schema:
                    results.append(ValidationResult(
                        status=ValidationStatus.FAILED,
                        severity=ValidationSeverity.WARNING,
                        message=f"发现未定义的字段: {field_name}",
                        field_name=field_name,
                        field_path=context.get_field_path(field_name)
                    ))
        
        # 汇总结果
        failed_results = [r for r in results if r.is_failure()]
        
        if failed_results:
            messages = [r.message for r in failed_results]
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"Schema验证失败: {'; '.join(messages)}",
                field_path=context.field_path,
                metadata={'validation_results': [r.to_dict() for r in failed_results]}
            )
        
        return ValidationResult(
            status=ValidationStatus.PASSED,
            metadata={'validation_results': [r.to_dict() for r in results]}
        )
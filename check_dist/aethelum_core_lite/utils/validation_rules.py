"""
验证规则模块

提供预定义的验证规则、组合验证器和业务规则验证。
"""

import re
import json
import time
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, date
import hashlib
import requests
from urllib.parse import urlparse

from .unified_validator import (
    BaseValidator, ValidationResult, ValidationContext, ValidationStatus,
    ValidationSeverity, RequiredValidator, TypeValidator, RangeValidator,
    LengthValidator, RegexValidator, EmailValidator, PhoneValidator,
    ChoicesValidator, CustomValidator, ConditionalValidator
)


class BusinessRuleValidator(BaseValidator):
    """业务规则验证器基类"""
    
    def __init__(self, rule_name: str, description: str = ""):
        super().__init__(rule_name)
        self.description = description


class DateRangeValidator(BusinessRuleValidator):
    """日期范围验证器"""
    
    def __init__(self, min_date: Union[str, date, datetime] = None,
                 max_date: Union[str, date, datetime] = None,
                 date_format: str = "%Y-%m-%d", name: str = "date_range"):
        super().__init__(name)
        self.min_date = self._parse_date(min_date, date_format)
        self.max_date = self._parse_date(max_date, date_format)
        self.date_format = date_format
    
    def _parse_date(self, date_input: Union[str, date, datetime], 
                   date_format: str) -> Optional[datetime]:
        """解析日期"""
        if date_input is None:
            return None
        elif isinstance(date_input, datetime):
            return date_input
        elif isinstance(date_input, date):
            return datetime.combine(date_input, datetime.min.time())
        elif isinstance(date_input, str):
            try:
                return datetime.strptime(date_input, date_format)
            except ValueError:
                return None
        return None
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if isinstance(data, str):
            try:
                parsed_date = datetime.strptime(data, self.date_format)
            except ValueError:
                return ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=self.severity,
                    message=f"字段 {context.field_path} 日期格式错误，期望格式: {self.date_format}",
                    field_path=context.field_path,
                    actual_value=data
                )
        elif isinstance(data, datetime):
            parsed_date = data
        elif isinstance(data, date):
            parsed_date = datetime.combine(data, datetime.min.time())
        else:
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"字段 {context.field_path} 不是有效的日期类型",
                field_path=context.field_path
            )
        
        errors = []
        
        if self.min_date and parsed_date < self.min_date:
            errors.append(f"日期 {parsed_date.strftime(self.date_format)} 早于最小日期 {self.min_date.strftime(self.date_format)}")
        
        if self.max_date and parsed_date > self.max_date:
            errors.append(f"日期 {parsed_date.strftime(self.date_format)} 晚于最大日期 {self.max_date.strftime(self.date_format)}")
        
        if errors:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 日期范围验证失败: {'; '.join(errors)}",
                field_path=context.field_path,
                actual_value=parsed_date.strftime(self.date_format),
                expected_value=f"[{self.min_date.strftime(self.date_format) if self.min_date else 'None'}, {self.max_date.strftime(self.date_format) if self.max_date else 'None'}]"
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class URLValidator(BusinessRuleValidator):
    """URL验证器"""
    
    def __init__(self, allowed_schemes: List[str] = None, 
                 require_https: bool = False, name: str = "url"):
        super().__init__(name)
        self.allowed_schemes = allowed_schemes or ['http', 'https']
        self.require_https = require_https
        
        # 构建正则表达式
        scheme_pattern = '|'.join(self.allowed_schemes)
        self.url_pattern = re.compile(
            rf'^({scheme_pattern})://'  # 协议
            r'(?:(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}'  # 域名
            r'|(?:\d{1,3}\.){3}\d{1,3})'  # IP地址
            r'(?::\d+)?'  # 端口
            r'(?:/[^\s]*)?$',  # 路径
            re.IGNORECASE
        )
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, str):
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"URL验证器只支持字符串类型",
                field_path=context.field_path
            )
        
        if not self.url_pattern.match(data):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 不是有效的URL格式",
                field_path=context.field_path,
                actual_value=data
            )
        
        # 检查HTTPS要求
        if self.require_https and not data.startswith('https://'):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 必须使用HTTPS协议",
                field_path=context.field_path,
                actual_value=data
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class PasswordStrengthValidator(BusinessRuleValidator):
    """密码强度验证器"""
    
    def __init__(self, min_length: int = 8, require_upper: bool = True,
                 require_lower: bool = True, require_digit: bool = True,
                 require_special: bool = True, special_chars: str = "!@#$%^&*",
                 name: str = "password_strength"):
        super().__init__(name)
        self.min_length = min_length
        self.require_upper = require_upper
        self.require_lower = require_lower
        self.require_digit = require_digit
        self.require_special = require_special
        self.special_chars = special_chars
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, str):
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"密码强度验证器只支持字符串类型",
                field_path=context.field_path
            )
        
        errors = []
        
        # 长度检查
        if len(data) < self.min_length:
            errors.append(f"密码长度少于{self.min_length}位")
        
        # 大写字母检查
        if self.require_upper and not re.search(r'[A-Z]', data):
            errors.append("密码必须包含大写字母")
        
        # 小写字母检查
        if self.require_lower and not re.search(r'[a-z]', data):
            errors.append("密码必须包含小写字母")
        
        # 数字检查
        if self.require_digit and not re.search(r'\d', data):
            errors.append("密码必须包含数字")
        
        # 特殊字符检查
        if self.require_special:
            special_pattern = f'[{re.escape(self.special_chars)}]'
            if not re.search(special_pattern, data):
                errors.append(f"密码必须包含特殊字符: {self.special_chars}")
        
        if errors:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 密码强度不足: {'; '.join(errors)}",
                field_path=context.field_path,
                actual_value=data
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class CreditCardValidator(BusinessRuleValidator):
    """信用卡号验证器"""
    
    def __init__(self, name: str = "credit_card"):
        super().__init__(name)
        # Luhn算法验证的正则表达式
        self.card_pattern = re.compile(r'^\d{13,19}$')
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, str):
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"信用卡验证器只支持字符串类型",
                field_path=context.field_path
            )
        
        # 移除空格和横线
        clean_number = re.sub(r'[\s-]', '', data)
        
        if not self.card_pattern.match(clean_number):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 信用卡号格式错误",
                field_path=context.field_path,
                actual_value=data
            )
        
        # Luhn算法验证
        if not self._luhn_check(clean_number):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 信用卡号无效（Luhn算法验证失败）",
                field_path=context.field_path,
                actual_value=data
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)
    
    def _luhn_check(self, card_number: str) -> bool:
        """Luhn算法验证"""
        total = 0
        reverse_digits = card_number[::-1]
        
        for i, digit in enumerate(reverse_digits):
            n = int(digit)
            
            if i % 2 == 1:  # 偶数位置（从0开始）
                n *= 2
                if n > 9:
                    n = (n // 10) + (n % 10)
            
            total += n
        
        return total % 10 == 0


class ChineseIDValidator(BusinessRuleValidator):
    """中国身份证号验证器"""
    
    def __init__(self, name: str = "chinese_id"):
        super().__init__(name)
        # 18位身份证号正则表达式
        self.id_pattern = re.compile(r'^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$')
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if not isinstance(data, str):
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"身份证验证器只支持字符串类型",
                field_path=context.field_path
            )
        
        if not self.id_pattern.match(data):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 身份证号格式错误",
                field_path=context.field_path,
                actual_value=data
            )
        
        # 校验位验证
        if not self._validate_check_digit(data):
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 身份证号校验位错误",
                field_path=context.field_path,
                actual_value=data
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)
    
    def _validate_check_digit(self, id_number: str) -> bool:
        """验证身份证校验位"""
        if len(id_number) != 18:
            return False
        
        # 权重因子
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        # 校验码对应值
        check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
        
        total = 0
        for i in range(17):
            total += int(id_number[i]) * weights[i]
        
        mod = total % 11
        expected_check = check_codes[mod]
        actual_check = id_number[-1].upper()
        
        return expected_check == actual_check


class JSONSchemaValidator(BusinessRuleValidator):
    """JSON Schema验证器"""
    
    def __init__(self, schema: Dict[str, Any], name: str = "json_schema"):
        super().__init__(name)
        self.schema = schema
        
        # 尝试导入jsonschema
        try:
            import jsonschema
            self.jsonschema = jsonschema
            self.schema_validator = self.jsonschema.Draft7Validator(schema)
        except ImportError:
            self.jsonschema = None
            self.schema_validator = None
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        if self.jsonschema is None:
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message="JSON Schema验证不可用，请安装jsonschema库",
                field_path=context.field_path
            )
        
        try:
            # 解析JSON字符串（如果需要）
            if isinstance(data, str):
                try:
                    json_data = json.loads(data)
                except json.JSONDecodeError as e:
                    return ValidationResult(
                        status=ValidationStatus.FAILED,
                        severity=self.severity,
                        message=f"字段 {context.field_path} JSON格式错误: {str(e)}",
                        field_path=context.field_path,
                        actual_value=data
                    )
            else:
                json_data = data
            
            # 验证schema
            self.schema_validator.validate(json_data)
            
            return ValidationResult(status=ValidationStatus.PASSED)
            
        except self.jsonschema.ValidationError as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} JSON Schema验证失败: {e.message}",
                field_path=context.field_path,
                actual_value=data,
                metadata={'schema_path': list(e.schema_path), 'error_path': list(e.path)}
            )
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"字段 {context.field_path} JSON Schema验证异常: {str(e)}",
                field_path=context.field_path,
                actual_value=data
            )


class UniqueValidator(BusinessRuleValidator):
    """唯一性验证器"""
    
    def __init__(self, existing_values: List[Any] = None, 
                 check_func: Callable[[Any], bool] = None,
                 case_sensitive: bool = True, name: str = "unique"):
        super().__init__(name)
        self.existing_values = existing_values or []
        self.check_func = check_func
        self.case_sensitive = case_sensitive
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        check_value = data
        
        if not self.case_sensitive and isinstance(data, str):
            check_value = data.lower()
            existing_set = set(v.lower() if isinstance(v, str) else v for v in self.existing_values)
        else:
            existing_set = set(self.existing_values)
        
        # 使用自定义检查函数
        if self.check_func:
            try:
                is_unique = self.check_func(data)
            except Exception:
                return ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"字段 {context.field_path} 唯一性检查函数执行失败",
                    field_path=context.field_path,
                    actual_value=data
                )
        else:
            is_unique = check_value not in existing_set
        
        if not is_unique:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=self.severity,
                message=f"字段 {context.field_path} 的值已存在，违反唯一性约束",
                field_path=context.field_path,
                actual_value=data
            )
        
        return ValidationResult(status=ValidationStatus.PASSED)


class ComparisonValidator(BusinessRuleValidator):
    """比较验证器"""
    
    def __init__(self, operator: str, compare_value: Any,
                 get_compare_value: Callable[[Any, ValidationContext], Any] = None,
                 name: str = "comparison"):
        super().__init__(name)
        self.operator = operator
        self.compare_value = compare_value
        self.get_compare_value = get_compare_value
        
        # 验证操作符
        valid_operators = ['==', '!=', '>', '>=', '<', '<=', 'in', 'not_in']
        if operator not in valid_operators:
            raise ValueError(f"不支持的操作符: {operator}，支持的操作符: {valid_operators}")
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        # 获取比较值
        if self.get_compare_value:
            try:
                compare_value = self.get_compare_value(data, context)
            except Exception as e:
                return ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.ERROR,
                    message=f"字段 {context.field_path} 获取比较值失败: {str(e)}",
                    field_path=context.field_path,
                    actual_value=data
                )
        else:
            compare_value = self.compare_value
        
        # 执行比较
        try:
            if self.operator == '==':
                result = data == compare_value
            elif self.operator == '!=':
                result = data != compare_value
            elif self.operator == '>':
                result = data > compare_value
            elif self.operator == '>=':
                result = data >= compare_value
            elif self.operator == '<':
                result = data < compare_value
            elif self.operator == '<=':
                result = data <= compare_value
            elif self.operator == 'in':
                result = data in compare_value
            elif self.operator == 'not_in':
                result = data not in compare_value
            else:
                result = False
            
            if not result:
                return ValidationResult(
                    status=ValidationStatus.FAILED,
                    severity=self.severity,
                    message=f"字段 {context.field_path} 比较验证失败: {data} {self.operator} {compare_value}",
                    field_path=context.field_path,
                    actual_value=data,
                    expected_value=f"{self.operator} {compare_value}"
                )
            
            return ValidationResult(status=ValidationStatus.PASSED)
            
        except Exception as e:
            return ValidationResult(
                status=ValidationStatus.FAILED,
                severity=ValidationSeverity.ERROR,
                message=f"字段 {context.field_path} 比较验证异常: {str(e)}",
                field_path=context.field_path,
                actual_value=data
            )


class ConditionalRequiredValidator(ConditionalValidator):
    """条件必填验证器"""
    
    def __init__(self, condition_func: Callable[[Any, ValidationContext], bool],
                 allow_empty: bool = False, name: str = "conditional_required"):
        required_validator = RequiredValidator(allow_empty=allow_empty)
        super().__init__(condition_func, required_validator, name)


class DependentFieldValidator(BusinessRuleValidator):
    """依赖字段验证器"""
    
    def __init__(self, dependency_field: str, dependency_values: List[Any],
                 validator: BaseValidator, name: str = "dependent_field"):
        super().__init__(name)
        self.dependency_field = dependency_field
        self.dependency_values = dependency_values
        self.validator = validator
    
    def validate(self, data: Any, context: ValidationContext) -> ValidationResult:
        # 获取依赖字段的值
        root_data = context.data if isinstance(context.data, dict) else {}
        dependency_value = root_data.get(self.dependency_field)
        
        # 检查依赖条件
        if dependency_value not in self.dependency_values:
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                message=f"依赖字段 {self.dependency_field} 的值不在依赖列表中，跳过验证",
                field_path=context.field_path
            )
        
        # 执行验证
        return self.validator._execute_validation(data, context)


# 预定义验证规则
class CommonValidationRules:
    """常用验证规则"""
    
    @staticmethod
    def username(name: str = "username") -> List[BaseValidator]:
        """用户名验证"""
        return [
            RequiredValidator(f"{name}_required"),
            LengthValidator(3, 20, f"{name}_length"),
            RegexValidator(r'^[a-zA-Z0-9_]+$', f"{name}_format", 
                         error_message="用户名只能包含字母、数字和下划线")
        ]
    
    @staticmethod
    def password(name: str = "password", strength: str = "medium") -> List[BaseValidator]:
        """密码验证"""
        if strength == "weak":
            return [
                RequiredValidator(f"{name}_required"),
                LengthValidator(6, None, f"{name}_length")
            ]
        elif strength == "medium":
            return [
                RequiredValidator(f"{name}_required"),
                LengthValidator(8, None, f"{name}_length"),
                PasswordStrengthValidator(f"{name}_strength")
            ]
        elif strength == "strong":
            return [
                RequiredValidator(f"{name}_required"),
                LengthValidator(12, None, f"{name}_length"),
                PasswordStrengthValidator(f"{name}_strength", min_length=12)
            ]
        else:
            return [
                RequiredValidator(f"{name}_required"),
                LengthValidator(8, None, f"{name}_length")
            ]
    
    @staticmethod
    def email(name: str = "email") -> List[BaseValidator]:
        """邮箱验证"""
        return [
            RequiredValidator(f"{name}_required"),
            EmailValidator(f"{name}_format")
        ]
    
    @staticmethod
    def phone(name: str = "phone", pattern: str = None) -> List[BaseValidator]:
        """手机号验证"""
        return [
            RequiredValidator(f"{name}_required"),
            PhoneValidator(f"{name}_format", pattern)
        ]
    
    @staticmethod
    def chinese_id(name: str = "id_card") -> List[BaseValidator]:
        """中国身份证验证"""
        return [
            RequiredValidator(f"{name}_required"),
            ChineseIDValidator(f"{name}_format")
        ]
    
    @staticmethod
    def age(min_age: int = 0, max_age: int = 150, name: str = "age") -> List[BaseValidator]:
        """年龄验证"""
        return [
            RequiredValidator(f"{name}_required"),
            TypeValidator(int, f"{name}_type"),
            RangeValidator(min_age, max_age, f"{name}_range")
        ]
    
    @staticmethod
    def non_negative(name: str = "amount") -> List[BaseValidator]:
        """非负数验证"""
        return [
            RequiredValidator(f"{name}_required"),
            TypeValidator((int, float), f"{name}_type"),
            RangeValidator(0, None, f"{name}_range")
        ]
    
    @staticmethod
    def percentage(name: str = "percentage") -> List[BaseValidator]:
        """百分比验证"""
        return [
            RequiredValidator(f"{name}_required"),
            TypeValidator((int, float), f"{name}_type"),
            RangeValidator(0, 100, f"{name}_range")
        ]
    
    @staticmethod
    def url(name: str = "url", require_https: bool = False) -> List[BaseValidator]:
        """URL验证"""
        validators = [URLValidator(f"{name}_format", require_https=require_https)]
        
        # 可选的必填验证
        return [RequiredValidator(f"{name}_required")] + validators
    
    @staticmethod
    def datetime_range(start_field: str, end_field: str, name: str = "datetime_range") -> List[BaseValidator]:
        """时间范围验证"""
        def validate_datetime_range(data: Any, context: ValidationContext) -> bool:
            root_data = context.data if isinstance(context.data, dict) else {}
            start_time = root_data.get(start_field)
            end_time = root_data.get(end_field)
            
            if start_time and end_time:
                try:
                    if isinstance(start_time, str):
                        start_time = datetime.fromisoformat(start_time)
                    if isinstance(end_time, str):
                        end_time = datetime.fromisoformat(end_time)
                    
                    return start_time <= end_time
                except:
                    return False
            
            return True
        
        return [
            CustomValidator(
                validate_datetime_range,
                f"{start_field} 必须早于或等于 {end_field}",
                name
            )
        ]
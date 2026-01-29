"""
工具模块

包含日志、验证、性能监控和错误处理等工具函数。
"""

# 基础工具
from .logger import setup_logger
from .validators import validate_message_package
from .logging_config import get_logger, setup_debug_logging

# 结构化日志系统
from .structured_logger import (
    LogLevel, LogFormat, LogEntry, LogOutput, ConsoleOutput, FileOutput,
    RotatingFileOutput, StructuredLogger, LoggerManager,
    get_structured_logger, set_global_logging_config, set_global_log_level,
    close_all_loggers, get_logging_stats
)

# 日志级别管理（需要 pyyaml 和 watchdog，属于可选依赖）
try:
    from .log_level_manager import (
        LogLevelRule, LogCondition, LogLevelManager, DynamicStructuredLogger,
        get_log_level_manager, create_dynamic_logger, load_log_level_config,
        set_temp_log_level, set_error_log_mode, set_debug_log_mode,
        get_effective_log_level, update_log_context
    )
    _HAS_LOG_LEVEL_MANAGER = True
except ImportError:
    # 如果没有安装 pyyaml 和 watchdog，设置为 None
    LogLevelRule = None
    LogCondition = None
    LogLevelManager = None
    DynamicStructuredLogger = None
    get_log_level_manager = None
    create_dynamic_logger = None
    load_log_level_config = None
    set_temp_log_level = None
    set_error_log_mode = None
    set_debug_log_mode = None
    get_effective_log_level = None
    update_log_context = None
    _HAS_LOG_LEVEL_MANAGER = False

# 日志性能优化
from .log_performance import (
    LogBatch, PerformanceMetrics, BatchLogOutput, AsyncBatchLogOutput,
    LogPerformanceMonitor, get_performance_monitor, start_log_performance_monitoring,
    stop_log_performance_monitoring, get_log_performance_summary
)

# 日志聚合分析
from .log_analytics import (
    AggregationType, TimeWindow, LogPattern, AlertRule, LogAggregator,
    get_log_aggregator, add_log_pattern, add_log_alert,
    query_logs, get_log_statistics, aggregate_logs
)

# 统一验证框架
from .unified_validator import (
    ValidationSeverity, ValidationStatus, ValidationResult, ValidationContext,
    BaseValidator, RequiredValidator, TypeValidator, RangeValidator,
    LengthValidator, RegexValidator, EmailValidator, PhoneValidator,
    ChoicesValidator, CustomValidator, ConditionalValidator, AsyncValidator,
    SchemaValidator
)

# 验证规则
from .validation_rules import (
    BusinessRuleValidator, DateRangeValidator, URLValidator,
    PasswordStrengthValidator, CreditCardValidator, ChineseIDValidator,
    JSONSchemaValidator, UniqueValidator, ComparisonValidator,
    ConditionalRequiredValidator, DependentFieldValidator, CommonValidationRules
)

# 验证性能优化
from .validation_performance import (
    ValidationCacheKey, CacheEntry, ValidationCache, ParallelValidationEngine,
    ValidationPerformanceOptimizer, ValidationProfiler,
    get_validation_optimizer, validate_with_optimization,
    validate_async_with_optimization
)

# 错误处理和报告
from .error_reporting import (
    ErrorSeverity, ErrorCategory, ErrorContext, ErrorReport, ErrorClassifier,
    ErrorReporter, get_error_reporter, report_error,
    report_custom_error
)

__all__ = [
    # 基础工具
    "setup_logger", "validate_message_package", "get_logger", "setup_debug_logging",
    
    # 结构化日志系统
    "LogLevel", "LogFormat", "LogEntry", "LogOutput", "ConsoleOutput", "FileOutput",
    "RotatingFileOutput", "StructuredLogger", "LoggerManager",
    "get_structured_logger", "set_global_logging_config", "set_global_log_level",
    "close_all_loggers", "get_logging_stats",
    
    # 日志级别管理
    "LogLevelRule", "LogCondition", "LogLevelManager", "DynamicStructuredLogger",
    "get_log_level_manager", "create_dynamic_logger", "load_log_level_config",
    "set_temp_log_level", "set_error_log_mode", "set_debug_log_mode",
    "get_effective_log_level", "update_log_context",
    
    # 日志性能优化
    "LogBatch", "PerformanceMetrics", "BatchLogOutput", "AsyncBatchLogOutput",
    "LogPerformanceMonitor", "get_performance_monitor", "start_log_performance_monitoring",
    "stop_log_performance_monitoring", "get_log_performance_summary",
    
    # 日志聚合分析
    "AggregationType", "TimeWindow", "LogPattern", "AlertRule", "LogAggregator",
    "get_log_aggregator", "add_log_pattern", "add_log_alert",
    "query_logs", "get_log_statistics", "aggregate_logs",
    
    # 统一验证框架
    "ValidationSeverity", "ValidationStatus", "ValidationResult", "ValidationContext",
    "BaseValidator", "RequiredValidator", "TypeValidator", "RangeValidator",
    "LengthValidator", "RegexValidator", "EmailValidator", "PhoneValidator",
    "ChoicesValidator", "CustomValidator", "ConditionalValidator", "AsyncValidator",
    "SchemaValidator",
    
    # 验证规则
    "BusinessRuleValidator", "DateRangeValidator", "URLValidator",
    "PasswordStrengthValidator", "CreditCardValidator", "ChineseIDValidator",
    "JSONSchemaValidator", "UniqueValidator", "ComparisonValidator",
    "ConditionalRequiredValidator", "DependentFieldValidator", "CommonValidationRules",
    
    # 验证性能优化
    "ValidationCacheKey", "CacheEntry", "ValidationCache", "ParallelValidationEngine",
    "ValidationPerformanceOptimizer", "ValidationProfiler",
    "get_validation_optimizer", "validate_with_optimization",
    "validate_async_with_optimization",
    
    # 错误处理和报告
    "ErrorSeverity", "ErrorCategory", "ErrorContext", "ErrorReport", "ErrorClassifier",
    "ErrorReporter", "get_error_reporter", "report_error",
    "report_custom_error"
]
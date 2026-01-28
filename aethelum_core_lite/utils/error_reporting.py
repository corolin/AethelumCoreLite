"""
错误处理和报告机制

提供统一的错误处理、错误报告和异常管理功能。
"""

import traceback
import sys
import time
import threading
import json
import os
from typing import Any, Dict, List, Optional, Union, Callable, Type, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from pathlib import Path

from .structured_logger import get_structured_logger, LogLevel


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """错误类别"""
    SYSTEM = "system"
    BUSINESS = "business"
    NETWORK = "network"
    DATABASE = "database"
    VALIDATION = "validation"
    SECURITY = "security"
    PERFORMANCE = "performance"
    USER_INPUT = "user_input"
    EXTERNAL_SERVICE = "external_service"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """错误上下文"""
    user_id: str = ""
    session_id: str = ""
    request_id: str = ""
    correlation_id: str = ""
    operation: str = ""
    module: str = ""
    function: str = ""
    line_number: int = 0
    thread_id: int = 0
    process_id: int = 0
    environment: str = ""
    version: str = ""
    custom_data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_current(cls, **kwargs) -> 'ErrorContext':
        """从当前环境创建上下文"""
        import inspect
        frame = inspect.currentframe()
        
        # 找到调用者帧
        caller_frame = None
        for _ in range(3):  # 向上查找3层
            if frame and frame.f_back:
                frame = frame.f_back
                caller_frame = frame
            else:
                break
        
        context = cls(**kwargs)
        
        if caller_frame:
            context.module = caller_frame.f_globals.get('__name__', '')
            context.function = caller_frame.f_code.co_name
            context.line_number = caller_frame.f_lineno
        
        context.thread_id = threading.get_ident()
        context.process_id = os.getpid()
        context.environment = os.getenv('ENVIRONMENT', 'development')
        
        return context


@dataclass
class ErrorReport:
    """错误报告"""
    error_id: str
    timestamp: float
    severity: ErrorSeverity
    category: ErrorCategory
    title: str
    message: str
    exception_type: str = ""
    exception_message: str = ""
    stack_trace: str = ""
    context: Optional[ErrorContext] = None
    resolved: bool = False
    resolution_notes: str = ""
    reporter: str = "system"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['severity'] = self.severity.value
        data['category'] = self.category.value
        data['timestamp_iso'] = datetime.fromtimestamp(self.timestamp).isoformat()
        if self.context:
            data['context'] = asdict(self.context)
        return data
    
    def get_summary(self) -> str:
        """获取错误摘要"""
        return f"[{self.severity.value.upper()}] {self.category.value}: {self.title}"


class ErrorClassifier:
    """错误分类器"""
    
    def __init__(self):
        self.classification_rules = {
            # 系统错误
            'MemoryError': (ErrorCategory.SYSTEM, ErrorSeverity.HIGH),
            'OSError': (ErrorCategory.SYSTEM, ErrorSeverity.MEDIUM),
            'IOError': (ErrorCategory.SYSTEM, ErrorSeverity.MEDIUM),
            
            # 网络错误
            'ConnectionError': (ErrorCategory.NETWORK, ErrorSeverity.MEDIUM),
            'TimeoutError': (ErrorCategory.NETWORK, ErrorSeverity.MEDIUM),
            'requests.exceptions.ConnectionError': (ErrorCategory.NETWORK, ErrorSeverity.MEDIUM),
            'requests.exceptions.Timeout': (ErrorCategory.NETWORK, ErrorSeverity.MEDIUM),
            
            # 数据库错误
            'sqlite3.DatabaseError': (ErrorCategory.DATABASE, ErrorSeverity.HIGH),
            'psycopg2.Error': (ErrorCategory.DATABASE, ErrorSeverity.HIGH),
            'pymysql.Error': (ErrorCategory.DATABASE, ErrorSeverity.HIGH),
            
            # 验证错误
            'ValidationError': (ErrorCategory.VALIDATION, ErrorSeverity.LOW),
            'ValueError': (ErrorCategory.VALIDATION, ErrorSeverity.LOW),
            'TypeError': (ErrorCategory.VALIDATION, ErrorSeverity.LOW),
            
            # 安全错误
            'PermissionError': (ErrorCategory.SECURITY, ErrorSeverity.HIGH),
            'AuthenticationError': (ErrorCategory.SECURITY, ErrorSeverity.HIGH),
            'AuthorizationError': (ErrorCategory.SECURITY, ErrorSeverity.HIGH),
            
            # 配置错误
            'ConfigurationError': (ErrorCategory.CONFIGURATION, ErrorSeverity.HIGH),
            'ImportError': (ErrorCategory.CONFIGURATION, ErrorSeverity.MEDIUM),
        }
    
    def classify(self, exception: Exception) -> Tuple[ErrorCategory, ErrorSeverity]:
        """分类异常"""
        exception_name = exception.__class__.__name__
        full_exception_name = f"{exception.__class__.__module__}.{exception.__class__.__name__}"
        
        # 精确匹配
        if full_exception_name in self.classification_rules:
            return self.classification_rules[full_exception_name]
        
        # 类名匹配
        if exception_name in self.classification_rules:
            return self.classification_rules[exception_name]
        
        # 模式匹配
        for pattern, classification in self.classification_rules.items():
            if pattern in full_exception_name or pattern in exception_name:
                return classification
        
        # 默认分类
        return (ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM)
    
    def add_rule(self, exception_pattern: str, category: ErrorCategory, severity: ErrorSeverity):
        """添加分类规则"""
        self.classification_rules[exception_pattern] = (category, severity)


class ErrorReporter:
    """错误报告器"""
    
    def __init__(self, app_name: str = "aethelum-core-lite"):
        self.app_name = app_name
        self.classifier = ErrorClassifier()
        self.error_handlers: List[Callable[[ErrorReport], None]] = []
        self.error_storage: List[ErrorReport] = []
        self.lock = threading.RLock()
        self.logger = get_structured_logger(f"{app_name}.error_reporter")
        
        # 配置
        self.config = {
            'enable_file_logging': True,
            'enable_console_logging': True,
            'enable_storage': True,
            'max_storage_size': 10000,
            'cleanup_interval': 3600,  # 1小时
            'retention_days': 30
        }
        
        # 存储路径
        self.storage_path = Path("logs") / "errors.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载已有错误
        self._load_errors()
        
        # 启动清理任务
        self._start_cleanup_task()
    
    def configure(self, **config):
        """配置错误报告器"""
        self.config.update(config)
    
    def add_handler(self, handler: Callable[[ErrorReport], None]):
        """添加错误处理器"""
        self.error_handlers.append(handler)
    
    def report_error(self, exception: Exception, title: str = "", 
                   context: Optional[ErrorContext] = None,
                   severity: Optional[ErrorSeverity] = None,
                   category: Optional[ErrorCategory] = None,
                   tags: List[str] = None, **metadata) -> ErrorReport:
        """报告错误"""
        # 生成错误ID
        error_id = self._generate_error_id(exception)
        
        # 分类异常
        if category is None:
            category, auto_severity = self.classifier.classify(exception)
        
        final_severity = severity or auto_severity
        
        # 创建错误报告
        error_report = ErrorReport(
            error_id=error_id,
            timestamp=time.time(),
            severity=final_severity,
            category=category,
            title=title or f"{exception.__class__.__name__}: {str(exception)}",
            message=str(exception),
            exception_type=exception.__class__.__name__,
            exception_message=str(exception),
            stack_trace=traceback.format_exc(),
            context=context or ErrorContext.from_current(),
            reporter="system",
            tags=tags or [],
            metadata=metadata
        )
        
        # 存储错误
        if self.config['enable_storage']:
            self._store_error(error_report)
        
        # 日志记录
        self._log_error(error_report)
        
        # 调用处理器
        self._call_handlers(error_report)
        
        return error_report
    
    def report_custom_error(self, title: str, message: str,
                         severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                         category: ErrorCategory = ErrorCategory.UNKNOWN,
                         context: Optional[ErrorContext] = None,
                         tags: List[str] = None, **metadata) -> ErrorReport:
        """报告自定义错误"""
        error_id = self._generate_custom_error_id(title, message)
        
        error_report = ErrorReport(
            error_id=error_id,
            timestamp=time.time(),
            severity=severity,
            category=category,
            title=title,
            message=message,
            exception_type="CustomError",
            context=context or ErrorContext.from_current(),
            reporter="custom",
            tags=tags or [],
            metadata=metadata
        )
        
        # 存储错误
        if self.config['enable_storage']:
            self._store_error(error_report)
        
        # 日志记录
        self._log_error(error_report)
        
        # 调用处理器
        self._call_handlers(error_report)
        
        return error_report
    
    def _generate_error_id(self, exception: Exception) -> str:
        """生成错误ID"""
        import hashlib
        error_str = f"{exception.__class__.__name__}_{str(exception)}_{time.time()}"
        return hashlib.md5(error_str.encode()).hexdigest()[:16]
    
    def _generate_custom_error_id(self, title: str, message: str) -> str:
        """生成自定义错误ID"""
        import hashlib
        error_str = f"{title}_{message}_{time.time()}"
        return hashlib.md5(error_str.encode()).hexdigest()[:16]
    
    def _store_error(self, error_report: ErrorReport):
        """存储错误报告"""
        with self.lock:
            self.error_storage.append(error_report)
            
            # 限制存储大小
            if len(self.error_storage) > self.config['max_storage_size']:
                self.error_storage = self.error_storage[-self.config['max_storage_size']:]
            
            # 持久化到文件
            try:
                with open(self.storage_path, 'w', encoding='utf-8') as f:
                    error_data = [error.to_dict() for error in self.error_storage]
                    json.dump(error_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                self.logger.error(f"保存错误报告失败: {e}")
    
    def _load_errors(self):
        """加载已有错误"""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                error_data = json.load(f)
                
                self.error_storage = []
                for item in error_data:
                    error_report = self._dict_to_error_report(item)
                    self.error_storage.append(error_report)
                    
        except Exception as e:
            self.logger.error(f"加载错误报告失败: {e}")
            self.error_storage = []
    
    def _dict_to_error_report(self, data: Dict[str, Any]) -> ErrorReport:
        """从字典创建错误报告"""
        # 转换枚举
        severity = ErrorSeverity(data['severity'])
        category = ErrorCategory(data['category'])
        
        # 重建上下文
        context = None
        if 'context' in data and data['context']:
            context = ErrorContext(**data['context'])
        
        return ErrorReport(
            error_id=data['error_id'],
            timestamp=data['timestamp'],
            severity=severity,
            category=category,
            title=data['title'],
            message=data['message'],
            exception_type=data.get('exception_type', ''),
            exception_message=data.get('exception_message', ''),
            stack_trace=data.get('stack_trace', ''),
            context=context,
            resolved=data.get('resolved', False),
            resolution_notes=data.get('resolution_notes', ''),
            reporter=data.get('reporter', 'system'),
            tags=data.get('tags', []),
            metadata=data.get('metadata', {})
        )
    
    def _log_error(self, error_report: ErrorReport):
        """记录错误日志"""
        log_data = {
            'error_id': error_report.error_id,
            'severity': error_report.severity.value,
            'category': error_report.category.value,
            'title': error_report.title,
            'message': error_report.message,
            'exception_type': error_report.exception_type,
            'context': error_report.context.to_dict() if error_report.context else {}
        }
        
        # 根据严重程度选择日志级别
        if error_report.severity == ErrorSeverity.CRITICAL:
            self.logger.critical("错误报告", **log_data)
        elif error_report.severity == ErrorSeverity.HIGH:
            self.logger.error("错误报告", **log_data)
        elif error_report.severity == ErrorSeverity.MEDIUM:
            self.logger.warning("错误报告", **log_data)
        else:
            self.logger.info("错误报告", **log_data)
    
    def _call_handlers(self, error_report: ErrorReport):
        """调用错误处理器"""
        for handler in self.error_handlers:
            try:
                handler(error_report)
            except Exception as e:
                self.logger.error(f"错误处理器执行失败: {e}")
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        def cleanup():
            while True:
                try:
                    self.cleanup_old_errors()
                    time.sleep(self.config['cleanup_interval'])
                except Exception as e:
                    self.logger.error(f"错误清理任务失败: {e}")
                    time.sleep(300)  # 5分钟后重试
        
        cleanup_thread = threading.Thread(target=cleanup, daemon=True)
        cleanup_thread.start()
    
    def cleanup_old_errors(self):
        """清理旧错误"""
        cutoff_time = time.time() - (self.config['retention_days'] * 24 * 3600)
        
        with self.lock:
            original_count = len(self.error_storage)
            self.error_storage = [
                error for error in self.error_storage 
                if error.timestamp > cutoff_time
            ]
            
            removed_count = original_count - len(self.error_storage)
            
            if removed_count > 0:
                self.logger.info(f"清理了 {removed_count} 个旧错误报告")
                
                # 更新文件
                try:
                    with open(self.storage_path, 'w', encoding='utf-8') as f:
                        error_data = [error.to_dict() for error in self.error_storage]
                        json.dump(error_data, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    self.logger.error(f"保存清理后的错误报告失败: {e}")
    
    def get_errors(self, limit: int = 100, severity: Optional[ErrorSeverity] = None,
                   category: Optional[ErrorCategory] = None,
                   start_time: Optional[float] = None,
                   end_time: Optional[float] = None,
                   resolved: Optional[bool] = None) -> List[ErrorReport]:
        """获取错误列表"""
        with self.lock:
            errors = self.error_storage.copy()
        
        # 过滤条件
        if severity:
            errors = [e for e in errors if e.severity == severity]
        
        if category:
            errors = [e for e in errors if e.category == category]
        
        if start_time:
            errors = [e for e in errors if e.timestamp >= start_time]
        
        if end_time:
            errors = [e for e in errors if e.timestamp <= end_time]
        
        if resolved is not None:
            errors = [e for e in errors if e.resolved == resolved]
        
        # 排序和限制
        errors.sort(key=lambda e: e.timestamp, reverse=True)
        return errors[:limit]
    
    def get_error_by_id(self, error_id: str) -> Optional[ErrorReport]:
        """根据ID获取错误"""
        with self.lock:
            for error in self.error_storage:
                if error.error_id == error_id:
                    return error
        return None
    
    def resolve_error(self, error_id: str, resolution_notes: str = "") -> bool:
        """解决错误"""
        with self.lock:
            for error in self.error_storage:
                if error.error_id == error_id:
                    error.resolved = True
                    error.resolution_notes = resolution_notes
                    
                    # 更新文件
                    try:
                        with open(self.storage_path, 'w', encoding='utf-8') as f:
                            error_data = [error.to_dict() for error in self.error_storage]
                            json.dump(error_data, f, indent=2, ensure_ascii=False)
                    except Exception as e:
                        self.logger.error(f"保存错误解决状态失败: {e}")
                    
                    self.logger.info(f"错误已解决: {error_id}")
                    return True
        
        return False
    
    def get_error_statistics(self, days: int = 7) -> Dict[str, Any]:
        """获取错误统计"""
        cutoff_time = time.time() - (days * 24 * 3600)
        
        with self.lock:
            recent_errors = [
                error for error in self.error_storage 
                if error.timestamp >= cutoff_time
            ]
        
        if not recent_errors:
            return {'total_errors': 0, 'days': days}
        
        # 按严重程度统计
        severity_stats = {}
        for severity in ErrorSeverity:
            count = len([e for e in recent_errors if e.severity == severity])
            severity_stats[severity.value] = count
        
        # 按类别统计
        category_stats = {}
        for category in ErrorCategory:
            count = len([e for e in recent_errors if e.category == category])
            category_stats[category.value] = count
        
        # 按日期统计
        date_stats = {}
        for error in recent_errors:
            date_str = datetime.fromtimestamp(error.timestamp).strftime('%Y-%m-%d')
            date_stats[date_str] = date_stats.get(date_str, 0) + 1
        
        # 解决率
        resolved_count = len([e for e in recent_errors if e.resolved])
        resolution_rate = (resolved_count / len(recent_errors)) * 100
        
        return {
            'total_errors': len(recent_errors),
            'days': days,
            'severity_distribution': severity_stats,
            'category_distribution': category_stats,
            'daily_distribution': date_stats,
            'resolved_count': resolved_count,
            'resolution_rate': resolution_rate
        }

# 全局错误报告器
_global_error_reporter = None

def get_error_reporter(app_name: str = "aethelum-core-lite") -> ErrorReporter:
    """获取全局错误报告器"""
    global _global_error_reporter
    if _global_error_reporter is None:
        _global_error_reporter = ErrorReporter(app_name)
    return _global_error_reporter

def report_error(exception: Exception, title: str = "",
               context: Optional[ErrorContext] = None,
               severity: Optional[ErrorSeverity] = None,
               category: Optional[ErrorCategory] = None,
               tags: List[str] = None, **metadata) -> ErrorReport:
    """报告错误"""
    reporter = get_error_reporter()
    return reporter.report_error(exception, title, context, severity, category, tags, **metadata)

def report_custom_error(title: str, message: str,
                     severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                     category: ErrorCategory = ErrorCategory.UNKNOWN,
                     context: Optional[ErrorContext] = None,
                     tags: List[str] = None, **metadata) -> ErrorReport:
    """报告自定义错误"""
    reporter = get_error_reporter()
    return reporter.report_custom_error(title, message, severity, category, context, tags, **metadata)
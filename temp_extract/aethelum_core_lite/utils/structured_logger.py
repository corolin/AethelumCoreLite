"""
结构化日志系统

提供高性能、可配置的结构化日志记录功能，支持多种输出格式和聚合分析。
"""

import json
import time
import threading
import logging
import logging.handlers
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
from collections import deque
import queue
import asyncio
from pathlib import Path


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4
    
    @classmethod
    def from_string(cls, level_str: str) -> 'LogLevel':
        """从字符串创建日志级别"""
        level_map = {
            'DEBUG': cls.DEBUG,
            'INFO': cls.INFO,
            'WARNING': cls.WARNING,
            'WARN': cls.WARNING,
            'ERROR': cls.ERROR,
            'CRITICAL': cls.CRITICAL,
            'FATAL': cls.CRITICAL
        }
        return level_map.get(level_str.upper(), cls.INFO)
    
    def to_logging_level(self) -> int:
        """转换为标准logging级别"""
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL
        }
        return mapping[self]


class LogFormat(Enum):
    """日志格式枚举"""
    JSON = "json"
    PLAIN = "plain"
    STRUCTURED = "structured"
    ELASTIC = "elastic"


@dataclass
class LogEntry:
    """日志条目数据结构"""
    timestamp: float
    level: LogLevel
    logger_name: str
    message: str
    module: str = ""
    function: str = ""
    line_number: int = 0
    thread_id: int = 0
    thread_name: str = ""
    process_id: int = 0
    session_id: str = ""
    correlation_id: str = ""
    user_id: str = ""
    request_id: str = ""
    tags: List[str] = None
    metadata: Dict[str, Any] = None
    exception: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['level'] = self.level.name
        data['timestamp_iso'] = datetime.fromtimestamp(
            self.timestamp, timezone.utc
        ).isoformat()
        return data
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(',', ':'))


class LogFormatter:
    """日志格式化器基类"""
    
    def format(self, entry: LogEntry) -> str:
        """格式化日志条目"""
        raise NotImplementedError


class JsonFormatter(LogFormatter):
    """JSON格式化器"""
    
    def __init__(self, pretty: bool = False):
        self.pretty = pretty
    
    def format(self, entry: LogEntry) -> str:
        """格式化为JSON"""
        if self.pretty:
            return json.dumps(entry.to_dict(), ensure_ascii=False, indent=2)
        return entry.to_json()


class PlainFormatter(LogFormatter):
    """纯文本格式化器"""
    
    def __init__(self, include_metadata: bool = False):
        self.include_metadata = include_metadata
    
    def format(self, entry: LogEntry) -> str:
        """格式化为纯文本"""
        timestamp = datetime.fromtimestamp(entry.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        parts = [
            f"{timestamp}",
            f"[{entry.level.name}]",
            entry.logger_name,
            entry.message
        ]
        
        if entry.module:
            parts.insert(-1, f"({entry.module}:{entry.line_number})")
        
        base_msg = " - ".join(parts)
        
        if self.include_metadata and entry.metadata:
            metadata_str = " | ".join([f"{k}={v}" for k, v in entry.metadata.items()])
            base_msg += f" | {metadata_str}"
        
        if entry.tags:
            tags_str = " ".join([f"#{tag}" for tag in entry.tags])
            base_msg += f" [{tags_str}]"
        
        return base_msg


class StructuredFormatter(LogFormatter):
    """结构化格式化器"""
    
    def format(self, entry: LogEntry) -> str:
        """格式化为结构化文本"""
        timestamp = datetime.fromtimestamp(entry.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        parts = [
            f"time={timestamp}",
            f"level={entry.level.name}",
            f"logger={entry.logger_name}",
            f"msg=\"{entry.message}\""
        ]
        
        if entry.module:
            parts.append(f"module={entry.module}")
            parts.append(f"line={entry.line_number}")
        
        if entry.session_id:
            parts.append(f"session_id={entry.session_id}")
        
        if entry.correlation_id:
            parts.append(f"correlation_id={entry.correlation_id}")
        
        if entry.tags:
            parts.append(f"tags={','.join(entry.tags)}")
        
        for key, value in entry.metadata.items():
            parts.append(f"{key}={value}")
        
        return " ".join(parts)


class ElasticFormatter(LogFormatter):
    """ElasticSearch格式化器"""
    
    def format(self, entry: LogEntry) -> str:
        """格式化为ElasticSearch格式"""
        data = entry.to_dict()
        data['@timestamp'] = data.pop('timestamp_iso')
        data['level'] = entry.level.name.lower()
        
        # 添加ElasticSearch特定的字段
        data['environment'] = 'production'  # 可以从配置获取
        data['service'] = 'aethelum-core-lite'
        
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


class LogOutput:
    """日志输出器基类"""
    
    def write(self, formatted_entry: str, entry: LogEntry):
        """写入日志条目"""
        raise NotImplementedError
    
    def close(self):
        """关闭输出器"""
        pass


class ConsoleOutput(LogOutput):
    """控制台输出器"""
    
    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors and hasattr(self.stream, 'isatty') and self.stream.isatty()
        self.stream = None
    
    def write(self, formatted_entry: str, entry: LogEntry):
        """输出到控制台"""
        if self.stream is None:
            import sys
            self.stream = sys.stdout
        
        if self.use_colors:
            color_map = {
                LogLevel.DEBUG: '\033[36m',      # 青色
                LogLevel.INFO: '\033[32m',       # 绿色
                LogLevel.WARNING: '\033[33m',    # 黄色
                LogLevel.ERROR: '\033[31m',      # 红色
                LogLevel.CRITICAL: '\033[35m',   # 紫色
            }
            reset = '\033[0m'
            color = color_map.get(entry.level, '')
            formatted_entry = f"{color}{formatted_entry}{reset}"
        
        print(formatted_entry, file=self.stream)
        self.stream.flush()


class FileOutput(LogOutput):
    """文件输出器"""
    
    def __init__(self, file_path: str, max_size: int = 50 * 1024 * 1024, 
                 backup_count: int = 10, encoding: str = 'utf-8'):
        self.file_path = Path(file_path)
        self.max_size = max_size
        self.backup_count = backup_count
        self.encoding = encoding
        self.lock = threading.Lock()
        
        # 确保目录存在
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def write(self, formatted_entry: str, entry: LogEntry):
        """写入文件"""
        with self.lock:
            # 检查文件大小并轮转
            if self.file_path.exists() and self.file_path.stat().st_size >= self.max_size:
                self._rotate_files()
            
            # 写入日志
            with open(self.file_path, 'a', encoding=self.encoding) as f:
                f.write(formatted_entry + '\n')
                f.flush()
    
    def _rotate_files(self):
        """轮转日志文件"""
        # 删除最老的备份文件
        oldest_backup = self.file_path.with_suffix(f'.{self.backup_count}')
        if oldest_backup.exists():
            oldest_backup.unlink()
        
        # 重命名现有备份文件
        for i in range(self.backup_count - 1, 0, -1):
            old_backup = self.file_path.with_suffix(f'.{i}')
            new_backup = self.file_path.with_suffix(f'.{i + 1}')
            if old_backup.exists():
                old_backup.rename(new_backup)
        
        # 重命名当前文件为第一个备份
        if self.file_path.exists():
            backup_path = self.file_path.with_suffix('.1')
            self.file_path.rename(backup_path)
    
    def close(self):
        """关闭文件输出器"""
        pass


class RotatingFileOutput(LogOutput):
    """按时间轮转的文件输出器"""
    
    def __init__(self, base_path: str, rotation: str = 'daily', 
                 encoding: str = 'utf-8', max_files: int = 30):
        self.base_path = Path(base_path)
        self.rotation = rotation
        self.encoding = encoding
        self.max_files = max_files
        self.lock = threading.Lock()
        self.current_file_path = None
        self.current_date = None
        
        # 确保目录存在
        self.base_path.parent.mkdir(parents=True, exist_ok=True)
        self._update_file_path()
    
    def write(self, formatted_entry: str, entry: LogEntry):
        """写入文件"""
        self._update_file_path()
        
        with self.lock:
            with open(self.current_file_path, 'a', encoding=self.encoding) as f:
                f.write(formatted_entry + '\n')
                f.flush()
    
    def _update_file_path(self):
        """更新当前文件路径"""
        now = datetime.now()
        
        if self.rotation == 'daily':
            date_str = now.strftime('%Y-%m-%d')
            file_name = f"{self.base_path.stem}_{date_str}{self.base_path.suffix}"
        elif self.rotation == 'hourly':
            date_str = now.strftime('%Y-%m-%d_%H')
            file_name = f"{self.base_path.stem}_{date_str}{self.base_path.suffix}"
        elif self.rotation == 'monthly':
            date_str = now.strftime('%Y-%m')
            file_name = f"{self.base_path.stem}_{date_str}{self.base_path.suffix}"
        else:
            file_name = self.base_path.name
        
        self.current_file_path = self.base_path.parent / file_name
        self.current_date = now.date()
        
        # 清理旧文件
        if self.rotation != 'none':
            self._cleanup_old_files()
    
    def _cleanup_old_files(self):
        """清理旧文件"""
        import glob
        
        pattern = f"{self.base_path.stem}_*{self.base_path.suffix}"
        files = list(self.base_path.parent.glob(pattern))
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # 删除超过最大文件数的文件
        for file_path in files[self.max_files:]:
            file_path.unlink()
    
    def close(self):
        """关闭输出器"""
        pass


class AsyncLogOutput(LogOutput):
    """异步日志输出器"""
    
    def __init__(self, output: LogOutput, buffer_size: int = 1000, 
                 flush_interval: float = 1.0):
        self.output = output
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.buffer = queue.Queue(maxsize=buffer_size)
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.start_worker()
    
    def start_worker(self):
        """启动工作线程"""
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
    
    def _worker_loop(self):
        """工作线程循环"""
        last_flush = time.time()
        
        while not self.stop_event.is_set():
            try:
                # 等待日志条目
                entry_data = self.buffer.get(timeout=0.1)
                formatted_entry, log_entry = entry_data
                self.output.write(formatted_entry, log_entry)
                last_flush = time.time()
                
            except queue.Empty:
                # 定期刷新
                if time.time() - last_flush >= self.flush_interval:
                    self._flush_buffer()
                    last_flush = time.time()
    
    def write(self, formatted_entry: str, entry: LogEntry):
        """异步写入"""
        try:
            self.buffer.put_nowait((formatted_entry, entry))
        except queue.Full:
            # 缓冲区满，直接写入
            self.output.write(formatted_entry, entry)
    
    def _flush_buffer(self):
        """刷新缓冲区"""
        while not self.buffer.empty():
            try:
                entry_data = self.buffer.get_nowait()
                formatted_entry, log_entry = entry_data
                self.output.write(formatted_entry, log_entry)
            except queue.Empty:
                break
    
    def close(self):
        """关闭异步输出器"""
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5.0)
        self._flush_buffer()
        self.output.close()


class StructuredLogger:
    """结构化日志记录器"""
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO,
                 outputs: List[LogOutput] = None, formatter: LogFormat = LogFormat.JSON):
        self.name = name
        self.level = level
        self.outputs = outputs or []
        self.formatter = self._create_formatter(formatter)
        self.default_context = {}
    
    def _create_formatter(self, format_type: LogFormat) -> LogFormatter:
        """创建格式化器"""
        if format_type == LogFormat.JSON:
            return JsonFormatter()
        elif format_type == LogFormat.PLAIN:
            return PlainFormatter()
        elif format_type == LogFormat.STRUCTURED:
            return StructuredFormatter()
        elif format_type == LogFormat.ELASTIC:
            return ElasticFormatter()
        else:
            return JsonFormatter()
    
    def set_level(self, level: LogLevel):
        """设置日志级别"""
        self.level = level
    
    def add_output(self, output: LogOutput):
        """添加输出器"""
        self.outputs.append(output)
    
    def set_default_context(self, **context):
        """设置默认上下文"""
        self.default_context.update(context)
    
    def _create_log_entry(self, level: LogLevel, message: str, 
                         exc_info=None, **kwargs) -> LogEntry:
        """创建日志条目"""
        import inspect
        import sys
        
        # 获取调用栈信息
        frame = inspect.currentframe()
        try:
            # 向上找到调用栈中不是日志框架的帧
            caller_frame = frame
            while caller_frame:
                caller_frame = caller_frame.f_back
                module_name = caller_frame.f_globals.get('__name__', '')
                if not module_name.startswith('aethelum_core_lite.utils.structured_logger'):
                    break
            
            if caller_frame:
                module = caller_frame.f_globals.get('__name__', '')
                function = caller_frame.f_code.co_name
                line_number = caller_frame.f_lineno
            else:
                module = function = ""
                line_number = 0
        finally:
            del frame
        
        # 处理异常信息
        exception_info = None
        if exc_info:
            import traceback
            exc_type, exc_value, exc_traceback = exc_info
            exception_info = {
                'type': exc_type.__name__ if exc_type else None,
                'message': str(exc_value) if exc_value else None,
                'traceback': traceback.format_exception(exc_type, exc_value, exc_traceback) if exc_traceback else None
            }
        
        # 创建日志条目
        entry = LogEntry(
            timestamp=time.time(),
            level=level,
            logger_name=self.name,
            message=message,
            module=module,
            function=function,
            line_number=line_number,
            thread_id=threading.get_ident(),
            thread_name=threading.current_thread().name,
            process_id=0,  # 可以通过 os.getpid() 获取
            tags=kwargs.pop('tags', []),
            metadata={**self.default_context, **kwargs}
        )
        
        if exception_info:
            entry.exception = exception_info
        
        return entry
    
    def _log(self, level: LogLevel, message: str, exc_info=None, **kwargs):
        """内部日志方法"""
        if level.value < self.level.value:
            return
        
        entry = self._create_log_entry(level, message, exc_info, **kwargs)
        formatted_entry = self.formatter.format(entry)
        
        for output in self.outputs:
            output.write(formatted_entry, entry)
    
    def debug(self, message: str, **kwargs):
        """记录调试日志"""
        self._log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """记录信息日志"""
        self._log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录警告日志"""
        self._log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, exc_info=None, **kwargs):
        """记录错误日志"""
        self._log(LogLevel.ERROR, message, exc_info=exc_info, **kwargs)
    
    def critical(self, message: str, exc_info=None, **kwargs):
        """记录严重错误日志"""
        self._log(LogLevel.CRITICAL, message, exc_info=exc_info, **kwargs)
    
    def exception(self, message: str, **kwargs):
        """记录异常日志（包含堆栈）"""
        self.error(message, exc_info=True, **kwargs)
    
    def log_impulse(self, impulse, action: str, **kwargs):
        """记录神经脉冲信息"""
        self._log(LogLevel.INFO, f"神经脉冲操作: {action}",
                 session_id=getattr(impulse, 'session_id', ''),
                 action_intent=getattr(impulse, 'action_intent', ''),
                 source_agent=getattr(impulse, 'source_agent', ''),
                 correlation_id=getattr(impulse, 'correlation_id', ''),
                 tags=['impulse'],
                 **kwargs)
    
    def log_performance(self, operation: str, duration: float, **kwargs):
        """记录性能信息"""
        self._log(LogLevel.INFO, f"性能统计: {operation}",
                 operation=operation,
                 duration=duration,
                 tags=['performance'],
                 **kwargs)
    
    def log_hook(self, hook_name: str, action: str, **kwargs):
        """记录Hook信息"""
        self._log(LogLevel.DEBUG, f"Hook {action}: {hook_name}",
                 hook_name=hook_name,
                 action=action,
                 tags=['hook'],
                 **kwargs)
    
    def close(self):
        """关闭日志记录器"""
        for output in self.outputs:
            output.close()


class LoggerManager:
    """日志管理器"""
    
    def __init__(self):
        self.loggers: Dict[str, StructuredLogger] = {}
        self.config = {}
        self.lock = threading.Lock()
    
    def create_logger(self, name: str, **config) -> StructuredLogger:
        """创建日志记录器"""
        with self.lock:
            if name in self.loggers:
                return self.loggers[name]
            
            # 合并配置
            final_config = {**self.config, **config}
            
            # 创建输出器
            outputs = self._create_outputs(final_config)
            
            # 创建日志记录器
            logger = StructuredLogger(
                name=name,
                level=LogLevel.from_string(final_config.get('level', 'INFO')),
                outputs=outputs,
                formatter=LogFormat(final_config.get('format', 'json'))
            )
            
            # 设置默认上下文
            default_context = final_config.get('default_context', {})
            if default_context:
                logger.set_default_context(**default_context)
            
            self.loggers[name] = logger
            return logger
    
    def _create_outputs(self, config: Dict[str, Any]) -> List[LogOutput]:
        """创建输出器"""
        outputs = []
        
        # 控制台输出
        if config.get('console', True):
            outputs.append(ConsoleOutput(use_colors=config.get('console_colors', True)))
        
        # 文件输出
        file_config = config.get('file')
        if file_config:
            file_path = file_config.get('path')
            if file_path:
                if file_config.get('rotation'):
                    outputs.append(RotatingFileOutput(
                        file_path,
                        rotation=file_config.get('rotation', 'daily'),
                        max_files=file_config.get('max_files', 30)
                    ))
                else:
                    outputs.append(FileOutput(
                        file_path,
                        max_size=file_config.get('max_size', 50 * 1024 * 1024),
                        backup_count=file_config.get('backup_count', 10)
                    ))
        
        # 异步输出包装
        if config.get('async_output', True):
            outputs = [AsyncLogOutput(output) for output in outputs]
        
        return outputs
    
    def get_logger(self, name: str) -> StructuredLogger:
        """获取日志记录器"""
        with self.lock:
            if name not in self.loggers:
                return self.create_logger(name)
            return self.loggers[name]
    
    def set_global_config(self, **config):
        """设置全局配置"""
        with self.lock:
            self.config.update(config)
    
    def set_global_level(self, level: LogLevel):
        """设置全局日志级别"""
        with self.lock:
            for logger in self.loggers.values():
                logger.set_level(level)
    
    def close_all(self):
        """关闭所有日志记录器"""
        with self.lock:
            for logger in self.loggers.values():
                logger.close()
            self.loggers.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            return {
                'logger_count': len(self.loggers),
                'loggers': list(self.loggers.keys()),
                'global_config': self.config
            }


# 全局日志管理器
_logger_manager = LoggerManager()

def get_structured_logger(name: str, **config) -> StructuredLogger:
    """获取结构化日志记录器"""
    return _logger_manager.get_logger(name)

def set_global_logging_config(**config):
    """设置全局日志配置"""
    _logger_manager.set_global_config(**config)

def set_global_log_level(level: LogLevel):
    """设置全局日志级别"""
    _logger_manager.set_global_level(level)

def close_all_loggers():
    """关闭所有日志记录器"""
    _logger_manager.close_all()

def get_logging_stats() -> Dict[str, Any]:
    """获取日志统计信息"""
    return _logger_manager.get_stats()
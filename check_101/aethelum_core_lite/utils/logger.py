"""
日志工具模块

提供统一的日志配置和工具函数。
"""

import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""

    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }

    def format(self, record):
        # 添加颜色
        if record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}"
                f"{self.COLORS['RESET']}"
            )

        return super().format(record)


def setup_logger(
    name: str,
    level: str = "INFO",
    log_format: Optional[str] = None,
    enable_colors: bool = True,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: 日志格式字符串
        enable_colors: 是否启用彩色输出
        log_file: 日志文件路径（可选）

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # 默认日志格式
    if log_format is None:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if enable_colors and sys.stdout.isatty():
        console_formatter = ColoredFormatter(log_format)
    else:
        console_formatter = logging.Formatter(log_format)

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器（如果指定了日志文件）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # 防止日志传播到根日志记录器
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        logging.Logger: 日志记录器
    """
    return logging.getLogger(name)


class PerformanceLogger:
    """性能日志记录器"""

    def __init__(self, logger: logging.Logger, operation_name: str):
        self.logger = logger
        self.operation_name = operation_name
        self.start_time = None

    def __enter__(self):
        import time
        self.start_time = time.time()
        self.logger.debug(f"开始操作: {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        if self.start_time:
            duration = time.time() - self.start_time
            if exc_type:
                self.logger.error(f"操作失败: {self.operation_name}, 耗时: {duration:.3f}秒, 错误: {exc_val}")
            else:
                self.logger.debug(f"操作完成: {self.operation_name}, 耗时: {duration:.3f}秒")


def log_performance(operation_name: str):
    """
    性能日志装饰器

    Args:
        operation_name: 操作名称
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            with PerformanceLogger(logger, f"{operation_name} - {func.__name__}"):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# 预定义的日志记录器
neural_logger = setup_logger("NeuralSomaRouter", "INFO")
queue_logger = setup_logger("SynapticQueue", "INFO")
worker_logger = setup_logger("AxonWorker", "INFO")
audit_logger = setup_logger("AuditAgent", "INFO")


def set_global_log_level(level: str) -> None:
    """
    设置全局日志级别

    Args:
        level: 日志级别
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 更新根日志记录器级别
    logging.getLogger().setLevel(log_level)

    # 更新所有现有日志记录器级别
    for name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            logger.setLevel(log_level)


def create_logger_context(context: Dict[str, Any]) -> logging.LoggerAdapter:
    """
    创建带上下文的日志记录器

    Args:
        context: 上下文信息

    Returns:
        logging.LoggerAdapter: 带上下文的日志记录器
    """
    class ContextAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            context_str = ' '.join([f"{k}={v}" for k, v in self.extra.items()])
            return f"[{context_str}] {msg}", kwargs

    logger = logging.getLogger("ContextLogger")
    return ContextAdapter(logger, context)
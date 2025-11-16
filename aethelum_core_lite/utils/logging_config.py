#!/usr/bin/env python3
"""
日志配置工具

提供统一的日志配置，支持文件和控制台输出
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_debug_logging(name: str = None, log_dir: str = None):
    """
    设置DEBUG级别的日志记录，包含文件和控制台输出

    Args:
        name: logger名称，如果为None则使用调用者的模块名
        log_dir: 日志目录，如果为None则使用项目根目录下的logs文件夹

    Returns:
        logger: 配置好的logger对象
    """
    # 获取调用者的模块名
    if name is None:
        frame = sys._getframe(1)
        name = frame.f_globals.get('__name__', 'Unknown')

    # 设置日志目录
    if log_dir is None:
        # 获取项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        log_dir = os.path.join(project_root, 'logs')

    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 创建logger
    logger = logging.getLogger(name)

    # 避免重复添加handler - 如果已经有handlers，直接返回
    if logger.handlers:
        return logger

    # 日志格式 - 包含详细信息用于追踪脉冲
    detailed_format = (
        '%(asctime)s - %(name)s - %(levelname)s - '
        '[%(threadName)s:%(thread)d] - '
        '[PID:%(process)d] - '
        'File:%(filename)s:%(lineno)d - '
        'Func:%(funcName)s() - '
        'MSG:%(message)s'
    )

    simple_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 1. 文件Handler - DEBUG级别，记录所有详细信息（包括业务日志）
    log_file = os.path.join(log_dir, f"debug_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=50*1024*1024,  # 50MB
        backupCount=10,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(detailed_format))

    # 2. 控制台Handler - INFO级别，只显示重要信息（配置日志和错误/警告）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(simple_format))

    # 添加handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # 设置logger级别
    logger.setLevel(logging.DEBUG)

    # 防止日志传播到根logger，避免重复记录
    logger.propagate = False

    # 记录初始化信息
    logger.info(f"日志系统初始化完成 - 文件: {log_file}")
    logger.debug(f"Logger: {name}, Level: DEBUG, Handlers: 2 (文件+控制台)")

    return logger


def get_logger(name: str = None):
    """
    获取配置好的logger

    Args:
        name: logger名称

    Returns:
        logger: 配置好的logger对象
    """
    if name is None:
        name = __name__

    logger = logging.getLogger(name)

    # 如果logger还没有handlers，进行初始化
    if not logger.handlers:
        setup_debug_logging(name)
    else:
        # 确保logger的propagate设置正确
        logger.propagate = False

    return logger


def log_impulse_creation(logger, impulse, context: str = ""):
    """
    记录神经脉冲创建的详细信息

    Args:
        logger: logger对象
        impulse: 神经脉冲对象
        context: 上下文信息
    """
    logger.debug(f"[IMPULSE_CREATE] {context} - "
                f"SessionID: {impulse.session_id}, "
                f"ActionIntent: {impulse.action_intent}, "
                f"SourceAgent: {impulse.source_agent}, "
                f"InputSource: {impulse.input_source}, "
                f"ContentType: {impulse.metadata.get('content_type', 'unknown')}")


def log_impulse_routing(logger, impulse, from_queue: str, to_queue: str):
    """
    记录神经脉冲路由信息

    Args:
        logger: logger对象
        impulse: 神经脉冲对象
        from_queue: 源队列
        to_queue: 目标队列
    """
    logger.debug(f"[IMPULSE_ROUTING] "
                f"SessionID: {impulse.session_id}, "
                f"From: {from_queue} -> To: {to_queue}, "
                f"CurrentSource: {impulse.source_agent}, "
                f"Metadata: {len(impulse.metadata)} items")


def log_queue_stats(logger, router):
    """
    记录队列统计信息

    Args:
        logger: logger对象
        router: 路由器对象
    """
    try:
        stats = router.get_stats()
        queue_sizes = router.get_queue_sizes()

        logger.debug(f"[QUEUE_STATS] "
                    f"TotalImpulses: {stats['total_impulses_processed']}, "
                    f"QueueCount: {stats['queue_count']}, "
                    f"WorkerCount: {stats['worker_count']}")

        for queue_name, size in queue_sizes.items():
            logger.debug(f"  Queue[{queue_name}]: {size} items")

    except Exception as e:
        logger.error(f"记录队列统计信息失败: {e}")
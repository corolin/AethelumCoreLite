"""
API模块

提供RESTful API接口用于指标查询，支持API密钥认证。
"""

from .metrics_api import (
    MetricsAPIServer,
    app,
    set_router_instance,
    set_api_key
)

__all__ = [
    'MetricsAPIServer',
    'app',
    'set_router_instance',
    'set_api_key'
]

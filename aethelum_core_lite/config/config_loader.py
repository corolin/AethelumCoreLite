"""
配置加载器

从TOML配置文件中加载系统配置。
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Python 3.10 fallback
from pathlib import Path
import warnings


@dataclass
class MonitoringConfig:
    """监控配置"""
    enable_prometheus: bool = False
    enable_tracing: bool = False
    enable_metrics_api: bool = False
    prometheus_port: int = 8000
    prometheus_host: str = "127.0.0.1"
    jaeger_host: str = "localhost"
    jaeger_port: int = 6831
    tracing_sample_rate: float = 0.1


@dataclass
class SystemConfig:
    """系统配置"""
    worker_mode: str = "async"
    max_workers: int = 100
    queue_size: int = 10000


@dataclass
class APIConfig:
    """API配置"""
    metrics_api_host: str = "127.0.0.1"
    metrics_api_port: int = 8080
    enable_cors: bool = False
    api_key: Optional[str] = None  # API密钥（可选，建议生产环境设置）


@dataclass
class PerformanceConfig:
    """性能配置"""
    async_io_concurrency: int = 1000
    hook_timeout: float = 30.0


class ConfigLoader:
    """配置加载器"""

    @classmethod
    def _validate_config_path(cls, config_path: str) -> Path:
        """验证配置文件路径安全性

        防止路径遍历攻击：
        - 验证文件扩展名为 .toml
        - 检查路径是否在允许的范围内
        - 使用 resolve() 解析相对路径和符号链接

        Args:
            config_path: 配置文件路径

        Returns:
            Path: 验证后的路径对象

        Raises:
            ValueError: 路径不安全时
        """
        path = Path(config_path).resolve()

        # 确保是相对路径或绝对路径，但必须是.toml文件
        if path.suffix and path.suffix != '.toml':
            raise ValueError(
                f"配置文件必须是 .toml 格式: {path.suffix}"
            )

        # 检查路径是否在允许的范围内（可选：限制在当前工作目录）
        cwd = Path.cwd().resolve()
        try:
            path.relative_to(cwd)
        except ValueError:
            # 路径不在当前目录下，允许但要警告
            warnings.warn(
                f"配置文件不在当前工作目录下: {path}",
                stacklevel=2
            )

        return path

    @classmethod
    def _validate_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置内容的完整性和合法性

        验证规则：
        1. 端口范围：1024-65535
        2. 采样率：0.0-1.0
        3. 工作模式："async" 或 "thread"
        4. 数值范围：max_workers > 0, queue_size > 0, async_io_concurrency > 0
        5. hook_timeout > 0

        Args:
            config: 配置字典

        Returns:
            Dict[str, Any]: 验证后的配置

        Raises:
            ValueError: 配置不合法时
        """
        errors: List[str] = []

        # 验证 system 配置
        system = config.get("system", {})

        # 验证 worker_mode
        worker_mode = system.get("worker_mode", "async")
        if worker_mode not in ["async", "thread"]:
            errors.append(
                f"system.worker_mode 必须是 'async' 或 'thread'，当前值: {worker_mode}"
            )

        # 验证 max_workers
        max_workers = system.get("max_workers", 100)
        if not isinstance(max_workers, int) or max_workers <= 0:
            errors.append(
                f"system.max_workers 必须是正整数，当前值: {max_workers}"
            )

        # 验证 queue_size
        queue_size = system.get("queue_size", 10000)
        if not isinstance(queue_size, int) or queue_size <= 0:
            errors.append(
                f"system.queue_size 必须是正整数，当前值: {queue_size}"
            )

        # 验证 monitoring 配置
        monitoring = config.get("monitoring", {})

        # 验证端口范围
        for port_key in ["prometheus_port", "jaeger_port"]:
            port = monitoring.get(port_key)
            if port is not None:
                if not isinstance(port, int) or not (1024 <= port <= 65535):
                    errors.append(
                        f"monitoring.{port_key} 必须在 1024-65535 范围内，当前值: {port}"
                    )

        # 验证采样率
        sample_rate = monitoring.get("tracing_sample_rate", 0.1)
        if not isinstance(sample_rate, (int, float)) or not (0.0 <= sample_rate <= 1.0):
            errors.append(
                f"monitoring.tracing_sample_rate 必须在 0.0-1.0 范围内，当前值: {sample_rate}"
            )

        # 验证 api 配置
        api = config.get("api", {})
        metrics_api_port = api.get("metrics_api_port", 8080)
        if metrics_api_port is not None:
            if not isinstance(metrics_api_port, int) or not (1024 <= metrics_api_port <= 65535):
                errors.append(
                    f"api.metrics_api_port 必须在 1024-65535 范围内，当前值: {metrics_api_port}"
                )

        # 验证 performance 配置
        performance = config.get("performance", {})

        async_io_concurrency = performance.get("async_io_concurrency", 1000)
        if not isinstance(async_io_concurrency, int) or async_io_concurrency <= 0:
            errors.append(
                f"performance.async_io_concurrency 必须是正整数，当前值: {async_io_concurrency}"
            )

        hook_timeout = performance.get("hook_timeout", 30.0)
        if not isinstance(hook_timeout, (int, float)) or hook_timeout <= 0:
            errors.append(
                f"performance.hook_timeout 必须是正数，当前值: {hook_timeout}"
            )

        # 如果有错误，抛出异常
        if errors:
            error_msg = "配置验证失败:\n" + "\n".join(f"  - {err}" for err in errors)
            raise ValueError(error_msg)

        return config

    @classmethod
    def load_from_file(cls, config_path: str = "config.toml") -> dict:
        """从文件加载配置"""
        # 添加路径验证
        path = cls._validate_config_path(config_path)

        if not path.exists():
            return cls._get_default_config()

        with open(path, 'rb') as f:
            config = tomllib.load(f)

        # 添加配置验证
        config = cls._validate_config(config)

        return config

    @classmethod
    def _get_default_config(cls) -> dict:
        """获取默认配置"""
        return {
            "system": {
                "worker_mode": "async",
                "max_workers": 100,
                "queue_size": 10000
            },
            "monitoring": {
                "enable_prometheus": False,
                "enable_tracing": False,
                "enable_metrics_api": False,
                "prometheus_port": 8000,
                "prometheus_host": "127.0.0.1",
                "jaeger_host": "localhost",
                "jaeger_port": 6831,
                "tracing_sample_rate": 0.1
            },
            "api": {
                "metrics_api_host": "127.0.0.1",
                "metrics_api_port": 8080,
                "enable_cors": False,
                "api_key": None  # 默认不设置，仅依赖本地网络安全
            },
            "performance": {
                "async_io_concurrency": 1000,
                "hook_timeout": 30.0
            }
        }

    @classmethod
    def get_monitoring_config(cls, config: dict) -> MonitoringConfig:
        """获取监控配置"""
        monitoring = config.get("monitoring", {})
        return MonitoringConfig(**monitoring)

    @classmethod
    def get_system_config(cls, config: dict) -> SystemConfig:
        """获取系统配置"""
        system = config.get("system", {})
        return SystemConfig(**system)

    @classmethod
    def get_api_config(cls, config: dict) -> APIConfig:
        """获取API配置"""
        api = config.get("api", {})
        return APIConfig(**api)

    @classmethod
    def get_performance_config(cls, config: dict) -> PerformanceConfig:
        """获取性能配置"""
        performance = config.get("performance", {})
        return PerformanceConfig(**performance)

"""
配置管理模块测试
"""

import pytest
import tempfile
import os
from pathlib import Path

from aethelum_core_lite.config import ConfigLoader, MonitoringConfig, SystemConfig


class TestConfigLoader:
    """配置加载器测试"""

    def test_get_default_config(self):
        """测试获取默认配置"""
        config = ConfigLoader._get_default_config()

        assert "system" in config
        assert "monitoring" in config
        assert "api" in config
        assert "performance" in config

        assert config["system"]["worker_mode"] == "async"
        assert config["monitoring"]["enable_prometheus"] == False
        assert config["monitoring"]["enable_tracing"] == False

    def test_load_from_nonexistent_file(self):
        """测试从不存在的文件加载"""
        config = ConfigLoader.load_from_file("nonexistent.toml")
        assert config is not None
        assert "system" in config

    def test_load_from_file(self):
        """测试从文件加载配置"""
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[system]
worker_mode = "async"
max_workers = 50

[monitoring]
enable_prometheus = true
prometheus_port = 9091
""")
            temp_path = f.name

        try:
            config = ConfigLoader.load_from_file(temp_path)
            assert config["system"]["worker_mode"] == "async"
            assert config["system"]["max_workers"] == 50
            assert config["monitoring"]["enable_prometheus"] == True
            assert config["monitoring"]["prometheus_port"] == 9091
        finally:
            os.unlink(temp_path)

    def test_get_monitoring_config(self):
        """测试获取监控配置"""
        config = {
            "monitoring": {
                "enable_prometheus": True,
                "enable_tracing": False,
                "prometheus_port": 8000,
                "prometheus_host": "127.0.0.1"
            }
        }

        monitoring_config = ConfigLoader.get_monitoring_config(config)
        assert isinstance(monitoring_config, MonitoringConfig)
        assert monitoring_config.enable_prometheus == True
        assert monitoring_config.enable_tracing == False
        assert monitoring_config.prometheus_port == 8000
        assert monitoring_config.prometheus_host == "127.0.0.1"

    def test_get_system_config(self):
        """测试获取系统配置"""
        config = {
            "system": {
                "worker_mode": "async",
                "max_workers": 100
            }
        }

        system_config = ConfigLoader.get_system_config(config)
        assert isinstance(system_config, SystemConfig)
        assert system_config.worker_mode == "async"
        assert system_config.max_workers == 100

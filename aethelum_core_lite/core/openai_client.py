"""
OpenAI兼容客户端

提供对OpenAI旧版本API和其他OpenAI兼容服务的封装支持。
"""

import json
import time
import logging
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    raise ImportError("OpenAI库未安装！请安装：pip install openai")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    raise ImportError("requests库未安装！请安装：pip install requests")


@dataclass
class OpenAIConfig:
    """OpenAI客户端配置"""
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-3.5-turbo"
    max_retries: int = 3
    timeout: int = 30
    organization: Optional[str] = None

    # 审查模型特定配置
    audit_model: str = "gpt-3.5-turbo"  # 专门用于审查的模型
    audit_temperature: float = 0.0  # 审查使用低温度
    audit_max_tokens: int = 150  # 审查响应的最大token数

    # GLM模型特定配置
    thinking_type: str = "disabled"  # GLM深度思考模式: "enabled" 或 "disabled"


class OpenAICompatClient:
    """OpenAI兼容客户端"""

    def __init__(self, config: OpenAIConfig):
        """
        初始化OpenAI兼容客户端

        Args:
            config: OpenAI配置
        """
        self.config = config
        self.logger = logging.getLogger("OpenAICompatClient")

        if OPENAI_AVAILABLE:
            try:
                # 尝试使用新版openai库 (v1.0+)
                if hasattr(openai, 'OpenAI'):
                    self.client = openai.OpenAI(
                        api_key=config.api_key,
                        base_url=config.base_url,
                        organization=config.organization,
                        max_retries=config.max_retries,
                        timeout=config.timeout
                    )
                    self.client_version = "v1.0+"
                else:
                    # 使用旧版openai库
                    self.client = openai.ChatCompletion
                    openai.api_key = config.api_key
                    openai.base_url = config.base_url
                    if config.organization:
                        openai.organization = config.organization
                    self.client_version = "v0.x"

                self.logger.info(f"OpenAI客户端初始化成功 (版本: {self.client_version})")
                self.is_available = True

            except Exception as e:
                self.logger.error(f"OpenAI客户端初始化失败: {e}")
                raise RuntimeError(f"OpenAI客户端初始化失败: {e}")
        else:
            raise RuntimeError("OpenAI库不可用！请确保已正确安装 openai 库")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建聊天补全

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数

        Returns:
            Dict: API响应
        """
        if not self.is_available:
            raise RuntimeError("OpenAI客户端不可用！无法调用API")

        try:
            import time
            model_to_use = model or self.config.model

            if self.client_version == "v1.0+":
                # 新版openai库
                create_start = time.time()
                self.logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] 调用openai库chat.completions.create，模型: {model_to_use}")

                # 为GLM模型添加thinking参数
                thinking_type = getattr(self.config, 'thinking_type', None)
                extra_body = {}

                if thinking_type:
                    extra_body['thinking'] = {"type": thinking_type}
                    self.logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] GLM深度思考模式: {thinking_type}")
                elif "glm" in model_to_use.lower():
                    # GLM模型默认禁用深度思考模式
                    extra_body['thinking'] = {"type": "disabled"}
                    self.logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] GLM深度思考模式: disabled (默认)")

                response = self.client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                    **kwargs
                )
                create_end = time.time()
                self.logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] openai库调用完成，耗时: {(create_end - create_start):.3f}秒")

                # 转换为统一格式
                return {
                    "choices": [
                        {
                            "message": {
                                "content": response.choices[0].message.content,
                                "role": response.choices[0].message.role
                            },
                            "finish_reason": response.choices[0].finish_reason
                        }
                    ],
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0
                    },
                    "model": response.model,
                    "id": response.id
                }

            else:
                # 旧版openai库
                response = self.client.create(
                    model=model_to_use,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )

                return response

        except Exception as e:
            self.logger.error(f"OpenAI API调用失败: {e}")
            return {"error": str(e), "choices": []}

  
    
    def is_healthy(self) -> bool:
        """检查客户端健康状态"""
        if not self.is_available:
            return False

        try:
            # 发送一个简单的测试请求
            response = self.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            return "error" not in response and len(response.get("choices", [])) > 0
        except:
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "is_available": self.is_available,
            "client_version": getattr(self, 'client_version', 'unknown'),
            "model": self.config.model,
            "audit_model": self.config.audit_model,
            "base_url": self.config.base_url,
            "healthy": self.is_healthy()
        }


class OpenAIClientManager:
    """OpenAI客户端管理器"""

    def __init__(self):
        self.clients: Dict[str, OpenAICompatClient] = {}
        self.default_client_name = "default"
        self.logger = logging.getLogger("OpenAIClientManager")

    def add_client(self, name: str, config: OpenAIConfig) -> bool:
        """
        添加OpenAI客户端

        Args:
            name: 客户端名称
            config: 客户端配置

        Returns:
            bool: 是否添加成功
        """
        try:
            client = OpenAICompatClient(config)
            self.clients[name] = client
            self.logger.info(f"OpenAI客户端 '{name}' 添加成功")
            return True
        except Exception as e:
            self.logger.error(f"添加OpenAI客户端 '{name}' 失败: {e}")
            return False

    def get_client(self, name: Optional[str] = None) -> Optional[OpenAICompatClient]:
        """
        获取OpenAI客户端

        Args:
            name: 客户端名称，None表示使用默认客户端

        Returns:
            OpenAICompatClient: 客户端实例
        """
        client_name = name or self.default_client_name
        return self.clients.get(client_name)

    def set_default(self, name: str) -> bool:
        """
        设置默认客户端

        Args:
            name: 客户端名称

        Returns:
            bool: 是否设置成功
        """
        if name in self.clients:
            self.default_client_name = name
            self.logger.info(f"默认客户端设置为 '{name}'")
            return True
        return False

    def remove_client(self, name: str) -> bool:
        """
        移除OpenAI客户端

        Args:
            name: 客户端名称

        Returns:
            bool: 是否移除成功
        """
        if name in self.clients:
            del self.clients[name]
            self.logger.info(f"OpenAI客户端 '{name}' 已移除")

            # 如果删除的是默认客户端，重新选择默认
            if name == self.default_client_name and self.clients:
                self.default_client_name = next(iter(self.clients))
            return True
        return False

    def list_clients(self) -> List[str]:
        """列出所有客户端名称"""
        return list(self.clients.keys())

    def get_all_status(self) -> Dict[str, Any]:
        """获取所有客户端状态"""
        status = {}
        for name, client in self.clients.items():
            status[name] = {
                "is_default": name == self.default_client_name,
                "model_info": client.get_model_info()
            }
        return status


# 全局客户端管理器实例
openai_manager = OpenAIClientManager()


def create_openai_client(
    name: str = "default",
    api_key: str = "",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-3.5-turbo",
    **kwargs
) -> bool:
    """
    便捷函数：创建OpenAI客户端

    Args:
        name: 客户端名称
        api_key: API密钥
        base_url: API基础URL
        model: 模型名称
        **kwargs: 其他配置参数

    Returns:
        bool: 是否创建成功
    """
    config = OpenAIConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        **kwargs
    )

    success = openai_manager.add_client(name, config)
    if success:
        openai_manager.set_default(name)

    return success


def get_openai_client(name: Optional[str] = None) -> Optional[OpenAICompatClient]:
    """
    便捷函数：获取OpenAI客户端

    Args:
        name: 客户端名称

    Returns:
        OpenAICompatClient: 客户端实例
    """
    return openai_manager.get_client(name)
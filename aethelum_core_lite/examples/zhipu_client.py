"""
智谱AI官方SDK客户端实现
基于zai-sdk的智谱AI客户端，支持深度思考模式配置
"""

import time
import json
import logging
from typing import List, Dict, Any, Optional

try:
    from zai import ZhipuAiClient
    ZAI_SDK_AVAILABLE = True
except ImportError:
    ZAI_SDK_AVAILABLE = False
    ZhipuAiClient = None

logger = logging.getLogger(__name__)


class ZhipuConfig:
    """智谱AI客户端配置"""

    def __init__(self, api_key: str, model: str = "glm-4.5-flash", audit_model: str = "glm-4.5-flash",
                 audit_temperature: float = 0.0, audit_max_tokens: int = 1000,
                 timeout: int = 120, thinking_type: str = "disabled", **kwargs):
        self.api_key = api_key
        self.model = model
        self.audit_model = audit_model
        self.audit_temperature = audit_temperature
        self.audit_max_tokens = audit_max_tokens
        self.timeout = timeout
        self.thinking_type = thinking_type  # GLM深度思考模式: "enabled" 或 "disabled"

        # 设置其他可能的属性
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


class ZhipuSDKClient:
    """基于智谱AI官方SDK的客户端"""

    def __init__(self, config: ZhipuConfig):
        """
        初始化智谱AI客户端

        Args:
            config: 智谱AI配置
        """
        self.config = config
        self.is_available = False
        self.client = None

        if not ZAI_SDK_AVAILABLE:
            raise RuntimeError("智谱AI SDK (zai-sdk) 未安装！请运行: pip install zai-sdk")

        try:
            self.client = ZhipuAiClient(api_key=config.api_key)
            self.is_available = True
            logger.info(f"智谱AI客户端初始化成功，模型: {config.model}")
        except Exception as e:
            logger.error(f"智谱AI客户端初始化失败: {e}")
            raise RuntimeError(f"智谱AI客户端初始化失败: {e}")

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
            raise RuntimeError("智谱AI客户端不可用！无法调用API")

        try:
            model_to_use = model or self.config.model
            start_time = time.time()

            logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] 调用智谱AI SDK，模型: {model_to_use}")

            # 构建请求参数
            request_params = {
                "model": model_to_use,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # 添加thinking参数
            thinking_type = getattr(self.config, 'thinking_type', 'disabled')
            request_params["thinking"] = {"type": thinking_type}
            logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] GLM深度思考模式: {thinking_type}")

            # 调用智谱AI SDK
            response = self.client.chat.completions.create(**request_params)

            end_time = time.time()
            logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] 智谱AI SDK调用完成，耗时: {(end_time - start_time):.3f}秒")

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
                "id": response.id,
                "reasoning_content": getattr(response.choices[0].message, 'reasoning_content', None)
            }

        except Exception as e:
            logger.error(f"智谱AI API调用失败: {e}")
            return {"error": str(e), "choices": []}

    def is_healthy(self) -> bool:
        """检查客户端健康状态"""
        return self.is_available

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model": self.config.model,
            "audit_model": self.config.audit_model,
            "thinking_type": getattr(self.config, 'thinking_type', 'disabled'),
            "max_tokens": self.config.audit_max_tokens,
            "temperature": self.config.audit_temperature
        }


class ZhipuClientManager:
    """智谱AI客户端管理器"""

    def __init__(self):
        self.clients: Dict[str, ZhipuSDKClient] = {}
        self.default_client_name: str = "default"

    def add_client(self, name: str, config: ZhipuConfig) -> bool:
        """
        添加智谱AI客户端

        Args:
            name: 客户端名称
            config: 客户端配置

        Returns:
            bool: 是否添加成功
        """
        try:
            client = ZhipuSDKClient(config)
            self.clients[name] = client
            logger.debug(f"智谱AI客户端 '{name}' 添加成功")
            return True
        except Exception as e:
            logger.error(f"添加智谱AI客户端 '{name}' 失败: {e}")
            return False

    def get_client(self, name: Optional[str] = None) -> Optional[ZhipuSDKClient]:
        """
        获取智谱AI客户端

        Args:
            name: 客户端名称，None表示使用默认客户端

        Returns:
            ZhipuSDKClient: 客户端实例
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
            logger.debug(f"默认客户端设置为 '{name}'")
            return True
        return False

    def remove_client(self, name: str) -> bool:
        """
        移除智谱AI客户端

        Args:
            name: 客户端名称

        Returns:
            bool: 是否移除成功
        """
        if name in self.clients:
            del self.clients[name]
            logger.debug(f"智谱AI客户端 '{name}' 已移除")
            return True
        return False

    def list_clients(self) -> List[str]:
        """列出所有客户端名称"""
        return list(self.clients.keys())

    def get_default_client(self) -> Optional[ZhipuSDKClient]:
        """获取默认客户端"""
        return self.get_client()

    @classmethod
    def create_from_config(cls, config) -> 'ZhipuClientManager':
        """
        从配置创建智谱AI客户端管理器

        Args:
            config: 配置对象（支持ZhipuConfig或OpenAIConfig兼容格式）

        Returns:
            ZhipuClientManager: 智谱AI客户端管理器
        """
        manager = cls()

        # 创建智谱AI配置
        zhipu_config = ZhipuConfig(
            api_key=getattr(config, 'api_key', ''),
            model=getattr(config, 'model', 'glm-4.5-flash'),
            audit_model=getattr(config, 'audit_model', 'glm-4.5-flash'),
            audit_temperature=getattr(config, 'audit_temperature', 0.0),
            audit_max_tokens=getattr(config, 'audit_max_tokens', 1000),
            timeout=getattr(config, 'timeout', 120),
            thinking_type=getattr(config, 'thinking_type', 'disabled')
        )

        # 添加客户端
        manager.add_client("default", zhipu_config)

        return manager
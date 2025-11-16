"""
OpenAI配置模板文件

使用方法：
1. 复制此文件为 config.py
2. 填写您的API密钥
3. 在 main.py 中导入：from .config import OPENAI_CONFIG
"""

from ..core.openai_client import OpenAIConfig

# ⚠️ 请在此处填写您的OpenAI API密钥
OPENAI_CONFIG = OpenAIConfig(
    api_key="sk-your-api-key-here",  # 🔑 在这里填写您的API密钥
    base_url="https://api.openai.com/v1",
    model="gpt-3.5-turbo",
    audit_model="gpt-3.5-turbo",
    audit_temperature=0.0,
    audit_max_tokens=150
)

# 配置说明：
# api_key: OpenAI API密钥（必需）
# base_url: API基础URL，支持OpenAI兼容接口
# model: 默认对话模型
# audit_model: 内容审查专用模型
# audit_temperature: 审查时的温度参数（0.0表示更确定性）
# audit_max_tokens: 审查响应的最大token数

# 获取API密钥：https://platform.openai.com/api-keys
"""
智谱AI配置模板文件

使用方法：
1. 复制此文件为 config.py
2. 填写您的API密钥
3. 在 main.py 中导入：from .config import ZHIPU_CONFIG
"""

from ..examples.zhipu_client import ZhipuConfig

# ⚠️ 请在此处填写您的智谱AI API密钥
ZHIPU_CONFIG = ZhipuConfig(
    api_key="d5e7cc39b9d516b4dd41e998a9a5cd9e.nLS37mMMPyfk3wSq",  # ⚠️ 请在此处填写您的智谱AI API密钥
    model="glm-4.5-flash",
    audit_model="glm-4.5-flash",
    audit_temperature=0.0,
    audit_max_tokens=1000,  # 大幅增加token限制以处理长提示词
    timeout=120,  # 增加超时时间到120秒以处理复杂提示词
    thinking_type="disabled"  # 禁用GLM深度思考模式以提高响应速度
)

# 可选：保留OpenAI配置作为备用（如果需要）
try:
    # from ..core.openai_client import OpenAIConfig  # 已移除OpenAI依赖
    OPENAI_CONFIG = None
except ImportError:
    OPENAI_CONFIG = None

# 配置说明：
# api_key: 智谱AI API密钥（必需）
# model: 默认对话模型
# audit_model: 内容审查专用模型
# audit_temperature: 审查时的温度参数（0.0表示更确定性）
# audit_max_tokens: 审查响应的最大token数
# thinking_type: GLM深度思考模式，"enabled" 或 "disabled"

# 获取API密钥：https://open.bigmodel.cn/
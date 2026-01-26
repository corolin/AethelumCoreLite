"""
模拟 AI 服务用于示例演示

本模块提供模拟的 AI 客户端，不依赖任何真实的 AI API。
用于展示 AethelumCoreLite 框架的核心功能，无需配置 API keys。
"""

import time
import random
from typing import Dict, Any, List


class MockAIClient:
    """
    模拟 AI 客户端

    提供模拟的内容审核、处理和对话功能，用于示例演示。
    不需要真实的 API keys，开箱即用。
    """

    def __init__(self, response_delay: float = 0.1):
        """
        初始化模拟客户端

        Args:
            response_delay: 模拟响应延迟（秒），默认 0.1 秒
        """
        self.response_delay = response_delay
        self.request_count = 0

        # 预定义的模拟响应
        self.audit_responses = [
            "内容安全，符合规范",
            "发现潜在风险：内容涉及敏感话题",
            "建议修改：表述不够准确",
            "审核通过：内容质量良好",
            "内容合规，可以发布",
            "需要人工复核：边界情况"
        ]

        self.processing_responses = [
            "已处理您的请求",
            "任务完成，结果已生成",
            "处理成功：数据已更新",
            "操作完成：状态已同步",
            "计算完成：结果已缓存"
        ]

        self.chat_responses = [
            "这是一个很好的问题！让我为您详细分析。",
            "根据我的理解，建议您从以下几个方面考虑...",
            "这个问题涉及多个层面，我来逐一解释。",
            "很好的观点！我认为还可以进一步探讨...",
            "让我为您提供一个更全面的解决方案。"
        ]

    def audit_content(self, content: str) -> Dict[str, Any]:
        """
        模拟内容审核

        Args:
            content: 待审核的内容

        Returns:
            审核结果字典，包含：
            - safe: 是否安全
            - result: 审核结果文本
            - confidence: 置信度 (0-1)
            - request_id: 请求ID
        """
        self.request_count += 1
        time.sleep(self.response_delay)

        # 模拟审核逻辑：简单基于长度判断
        is_safe = len(content) < 1000
        audit_result = random.choice(self.audit_responses)

        return {
            "safe": is_safe,
            "result": audit_result,
            "confidence": round(random.uniform(0.8, 0.99), 3),
            "request_id": self.request_count,
            "content_length": len(content)
        }

    def process_content(self, content: str) -> Dict[str, Any]:
        """
        模拟内容处理

        Args:
            content: 待处理的内容

        Returns:
            处理结果字典，包含：
            - success: 是否成功
            - result: 处理结果文本
            - processed_content: 处理后的内容
            - request_id: 请求ID
        """
        self.request_count += 1
        time.sleep(self.response_delay)

        processing_result = random.choice(self.processing_responses)

        return {
            "success": True,
            "result": processing_result,
            "processed_content": f"[已处理] {content}",
            "request_id": self.request_count,
            "original_length": len(content),
            "processed_length": len(content) + 10
        }

    def chat_completion(self, messages: List[Dict[str, str]]) -> str:
        """
        模拟对话补全

        Args:
            messages: 消息列表，格式为 [{"role": "...", "content": "..."}]

        Returns:
            AI 响应文本
        """
        self.request_count += 1
        time.sleep(self.response_delay)

        # 从最后一条消息中提取关键词（模拟）
        if messages:
            last_message = messages[-1].get("content", "")
            if "你好" in last_message or "hello" in last_message.lower():
                return "您好！很高兴为您服务，有什么可以帮助您的吗？"
            elif "谢谢" in last_message or "thank" in last_message.lower():
                return "不客气！如果还有其他问题，随时可以问我。"

        return random.choice(self.chat_responses)

    def batch_audit(self, contents: List[str]) -> List[Dict[str, Any]]:
        """
        批量审核内容

        Args:
            contents: 待审核的内容列表

        Returns:
            审核结果列表
        """
        results = []
        for content in contents:
            result = self.audit_content(content)
            results.append(result)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """
        获取客户端统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_requests": self.request_count,
            "avg_delay": self.response_delay,
            "estimated_total_time": self.request_count * self.response_delay
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self.request_count = 0

    def set_response_delay(self, delay: float) -> None:
        """
        设置响应延迟

        Args:
            delay: 新的延迟时间（秒）
        """
        self.response_delay = delay


class MockStreamingClient:
    """
    模拟流式响应客户端

    用于演示流式处理场景。
    """

    def __init__(self, response_delay: float = 0.05, chunk_size: int = 10):
        """
        初始化流式客户端

        Args:
            response_delay: 每个块的延迟（秒）
            chunk_size: 每个块的大小
        """
        self.response_delay = response_delay
        self.chunk_size = chunk_size
        self.request_count = 0

    def stream_chat(self, message: str):
        """
        模拟流式对话响应

        Args:
            message: 输入消息

        Yields:
            响应文本片段
        """
        self.request_count += 1

        # 生成一个完整的响应
        full_response = (
            f"这是对消息 '{message[:20]}...' 的流式响应。"
            "我将分块返回内容，模拟真实的流式API行为。"
        )

        # 分块返回
        for i in range(0, len(full_response), self.chunk_size):
            chunk = full_response[i:i + self.chunk_size]
            time.sleep(self.response_delay)
            yield chunk

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_streaming_requests": self.request_count,
            "chunk_size": self.chunk_size,
            "avg_delay_per_chunk": self.response_delay
        }

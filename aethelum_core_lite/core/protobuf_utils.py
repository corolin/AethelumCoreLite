"""
ProtoBuf工具模块

提供ProtoBuf序列化/反序列化和消息处理功能。
"""

import json
import base64
from typing import Any, Dict, Optional, Union
from google.protobuf import json_format, message
from google.protobuf.any_pb2 import Any

# 兼容protobuf新旧版本的ParseError导入
try:
    from google.protobuf.json_pb2 import ParseError
except ImportError:
    # protobuf 4.0+ 中 ParseError 已移动到 json_format 模块
    ParseError = json_format.ParseError

# ProtoBuf消息类（需要先编译schema）
# 注意：必须先编译protobuf_schema.proto
# 编译命令：protoc --python_out=. protobuf_schema.proto

try:
    # 尝试导入编译后的proto模块
    from . import protobuf_schema_pb2
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    raise RuntimeError("ProtoBuf模块未编译！请先编译protobuf_schema.proto：protoc --python_out=. protobuf_schema.proto")


class ProtoBufManager:
    """ProtoBuf消息管理器"""

    @staticmethod
    def is_available() -> bool:
        """检查ProtoBuf是否可用"""
        return PROTOBUF_AVAILABLE

    @staticmethod
    def create_text_content(text: str, content_type: str = "text/plain", language: str = "zh") -> Any:
        """创建文本内容消息 - 为了兼容性保留"""
        request_content = protobuf_schema_pb2.RequestContent()
        request_content.user_input = text
        request_content.content_type = "text"
        return request_content

    @staticmethod
    def create_request_content(
        user_input: str = "",
        content_type: str = "input",
        caesar_shift: str = "",
        nonce: str = "",
        request_id: Optional[str] = None
    ) -> Any:
        """创建统一的请求内容消息"""
        request_content = protobuf_schema_pb2.RequestContent()
        request_content.user_input = user_input
        request_content.content_type = content_type

        # 审计相关字段
        if caesar_shift:
            request_content.caesar_shift = caesar_shift
        if nonce:
            request_content.nonce = nonce
        if request_id:
            request_content.request_id = request_id
        else:
            import uuid
            request_content.request_id = str(uuid.uuid4())

        return request_content

    @staticmethod
    def create_business_response(
        response_content: str,
        model_name: str = "unknown",
        user_input: str = ""
    ) -> Any:
        """创建业务响应消息"""
        request_content = protobuf_schema_pb2.RequestContent()
        request_content.user_input = user_input
        request_content.response_content = response_content
        request_content.model_name = model_name
        request_content.content_type = "output"

        import uuid
        request_content.request_id = str(uuid.uuid4())

        return request_content

    @staticmethod
    def create_neural_impulse(
        session_id: str,
        action_intent: str,
        source_agent: str,
        input_source: str,
        content: Any,
        metadata: Dict[str, Any],
        routing_history: list,
        timestamp: int
    ) -> Any:
        """创建神经脉冲消息"""
        impulse = protobuf_schema_pb2.NeuralImpulse()
        impulse.session_id = session_id
        impulse.action_intent = action_intent
        impulse.source_agent = source_agent
        impulse.input_source = input_source
        impulse.timestamp = timestamp

        # 处理内容 - 现在使用统一的RequestContent
        if hasattr(content, 'SerializeToString'):
            impulse.content.CopyFrom(content)
        elif isinstance(content, str):
            # 如果是字符串，创建RequestContent
            request_content = ProtoBufManager.create_request_content(user_input=content, content_type="input")
            impulse.content.CopyFrom(request_content)
        else:
            # 其他类型，使用JSON序列化后存储
            json_content = json.dumps(content, ensure_ascii=False)
            request_content = ProtoBufManager.create_request_content(user_input=json_content, content_type="json")
            impulse.content.CopyFrom(request_content)

        # 处理元数据
        if metadata:
            for key, value in metadata.items():
                metadata_item = impulse.metadata.add()
                metadata_item.key = key
                metadata_item.value = json.dumps(value, ensure_ascii=False)

        # 处理路由历史
        if routing_history:
            impulse.routing_history.extend(routing_history)

        return impulse

    @staticmethod
    def pack_any(message: Any) -> Any:
        """将消息包装为Any类型"""
        any_msg = Any()
        any_msg.Pack(message)
        return any_msg

    @staticmethod
    def unpack_any(any_msg: Any, expected_type: type) -> Any:
        """从Any类型解包消息"""
        if expected_type == str:
            # 期望返回字符串，从RequestContent的user_input字段获取
            unpacked = protobuf_schema_pb2.RequestContent()
            any_msg.Unpack(unpacked)
            return unpacked.user_input if unpacked.user_input else unpacked.response_content or ""
        else:
            # 其他类型直接解包
            unpacked = expected_type()
            any_msg.Unpack(unpacked)
            return unpacked

    @staticmethod
    def to_dict(proto_message: Any) -> Dict[str, Any]:
        """将ProtoBuf消息转换为字典"""
        try:
            return json_format.MessageToDict(proto_message)
        except Exception as e:
            raise RuntimeError(f"ProtoBuf消息转字典失败: {e}")

    @staticmethod
    def from_dict(message_dict: Dict[str, Any], message_type: type) -> Any:
        """从字典创建ProtoBuf消息"""
        try:
            return json_format.ParseDict(message_dict, message_type())
        except Exception as e:
            raise RuntimeError(f"字典转ProtoBuf消息失败: {e}")


def create_neural_impulse_proto(
    session_id: str,
    action_intent: str,
    source_agent: str,
    input_source: str,
    content: Any,
    metadata: Dict[str, Any],
    routing_history: list,
    timestamp: int
) -> Any:
    """创建神经脉冲ProtoBuf消息的便捷函数"""
    return ProtoBufManager.create_neural_impulse(
        session_id=session_id,
        action_intent=action_intent,
        source_agent=source_agent,
        input_source=input_source,
        content=content,
        metadata=metadata,
        routing_history=routing_history,
        timestamp=timestamp
    )


def extract_content_from_impulse(neural_impulse_proto: Any, expected_type: Optional[type] = None) -> Any:
    """从神经脉冲ProtoBuf中提取内容"""
    if neural_impulse_proto.HasField('content'):
        content = neural_impulse_proto.content

        if expected_type:
            # 如果期望特定类型，先包装为Any再解包
            any_msg = Any()
            any_msg.Pack(content)
            return ProtoBufManager.unpack_any(any_msg, expected_type)
        else:
            # 直接返回RequestContent
            return content
    else:
        return None
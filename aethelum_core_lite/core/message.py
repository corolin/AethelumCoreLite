"""
神经脉冲消息包 (NeuralImpulse)

定义了在神经网络中传递的信息包格式。
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Union
from .protobuf_utils import ProtoBufManager, create_neural_impulse_proto, extract_content_from_impulse


class NeuralImpulse:
    """
    神经脉冲 - 在神经元间传递的信息包

    基于设计文档的MessagePackage格式，增加了InputSource字段来表明消息来源
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        action_intent: str = "Q_AUDIT_INPUT",
        source_agent: str = "SYSTEM",
        input_source: str = "USER",
        content: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        routing_history: Optional[List[str]] = None
    ):
        """
        初始化神经脉冲

        Args:
            session_id: 会话ID，用于追踪
            action_intent: 下一个处理队列名称（路由键）
            source_agent: 上一个处理该消息的Agent标识符
            input_source: 消息来源标识（USER, SYSTEM, API等）
            content: 消息内容，支持ProtoBuf格式或普通文本
            metadata: 元数据字典
            routing_history: 消息流经的Agent序列
        """
        self.session_id: str = session_id or str(uuid.uuid4())
        self.action_intent: str = action_intent
        self.source_agent: str = source_agent
        self.input_source: str = input_source  # 新增字段，表明消息包来源
        self.content: Any = content
        self.metadata: Dict[str, Any] = metadata or {}
        self.routing_history: List[str] = routing_history or []
        self.timestamp: float = time.time()

    def add_to_history(self, agent_name: str) -> None:
        """添加Agent到路由历史"""
        if agent_name not in self.routing_history:
            self.routing_history.append(agent_name)

    def update_source(self, new_source: str) -> None:
        """更新源Agent"""
        self.source_agent = new_source
        self.add_to_history(new_source)

    def reroute_to(self, new_intent: str) -> None:
        """重新路由到指定队列"""
        self.action_intent = new_intent

    def get_info(self) -> Dict[str, Any]:
        """获取脉冲摘要信息"""
        return {
            "session_id": self.session_id,
            "action_intent": self.action_intent,
            "source_agent": self.source_agent,
            "input_source": self.input_source,
            "routing_history": self.routing_history,
            "timestamp": self.timestamp
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "action_intent": self.action_intent,
            "source_agent": self.source_agent,
            "input_source": self.input_source,
            "content": self.content,
            "metadata": self.metadata,
            "routing_history": self.routing_history,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NeuralImpulse':
        """从字典创建神经脉冲"""
        return cls(
            session_id=data.get("session_id"),
            action_intent=data.get("action_intent", "Q_AUDIT_INPUT"),
            source_agent=data.get("source_agent", "SYSTEM"),
            input_source=data.get("input_source", "USER"),
            content=data.get("content"),
            metadata=data.get("metadata"),
            routing_history=data.get("routing_history", [])
        )

    def __str__(self) -> str:
        """字符串表示"""
        content_preview = str(self.content)[:50] + "..." if len(str(self.content)) > 50 else str(self.content)
        return f"NeuralImpulse(id={self.session_id[:8]}..., intent={self.action_intent}, from={self.source_agent}, content={content_preview})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"NeuralImpulse(session_id='{self.session_id}', action_intent='{self.action_intent}', source_agent='{self.source_agent}', input_source='{self.input_source}')"

    # ProtoBuf相关方法
    def set_protobuf_content(self, proto_message: Any) -> None:
        """
        设置ProtoBuf内容

        Args:
            proto_message: ProtoBuf消息对象
        """
        if not ProtoBufManager.is_available():
            raise RuntimeError("ProtoBuf不可用！请先编译protobuf_schema.proto")

        self.content = ProtoBufManager.pack_any(proto_message)
        self.metadata['content_type'] = 'protobuf'

    def get_protobuf_content(self, expected_type: Optional[type] = None) -> Any:
        """
        获取ProtoBuf内容

        Args:
            expected_type: 期望的ProtoBuf消息类型

        Returns:
            ProtoBuf消息对象或解析后的内容
        """
        
        if self.metadata.get('content_type') == 'protobuf':
            content_obj = self.content

            if expected_type:
                # 如果期望特定类型
                if expected_type == str:
                    # 期望字符串，从user_input或response_content获取
                    # 首先解包为RequestContent
                    from .protobuf_schema_pb2 import RequestContent
                    request_content = None

                    if hasattr(content_obj, 'Is') and content_obj.Is(RequestContent.DESCRIPTOR):
                        # Any类型，需要解包
                        request_content = RequestContent()
                        content_obj.Unpack(request_content)
                    elif hasattr(content_obj, 'user_input'):
                        # 已经是RequestContent类型
                        request_content = content_obj

                    if request_content:
                        if hasattr(request_content, 'response_content') and request_content.response_content:
                            return request_content.response_content
                        elif hasattr(request_content, 'user_input') and request_content.user_input:
                            return request_content.user_input
                        else:
                            return str(request_content)
                    else:
                        return str(content_obj)

                else:
                    # 期望其他ProtoBuf类型
                    from .protobuf_schema_pb2 import RequestContent
                    request_content = None

                    
                    if hasattr(content_obj, 'Is') and content_obj.Is(RequestContent.DESCRIPTOR):
                        # Any类型，需要解包
                        request_content = RequestContent()
                        content_obj.Unpack(request_content)

                        if expected_type == RequestContent:
                            return request_content
                        else:
                            # 转换为其他类型
                            from google.protobuf.any_pb2 import Any
                            any_msg = Any()
                            any_msg.Pack(request_content)
                            unpacked = expected_type()
                            any_msg.Unpack(unpacked)
                            return unpacked
                    elif hasattr(content_obj, 'user_input'):
                        # 已经是RequestContent类型
                        if expected_type == RequestContent:
                            return content_obj
                        else:
                            from google.protobuf.any_pb2 import Any
                            any_msg = Any()
                            any_msg.Pack(content_obj)
                            unpacked = expected_type()
                            any_msg.Unpack(unpacked)
                            return unpacked
                    else:
                        # 直接解包
                        unpacked = expected_type()
                        content_obj.Unpack(unpacked)
                        return unpacked
            else:
                # 没有指定期望类型，尝试解包为RequestContent
                from .protobuf_schema_pb2 import RequestContent
                if hasattr(content_obj, 'Is') and content_obj.Is(RequestContent.DESCRIPTOR):
                    request_content = RequestContent()
                    content_obj.Unpack(request_content)
                    return request_content
                elif hasattr(content_obj, 'user_input'):
                    return content_obj
                else:
                    return content_obj
        else:
            # 普通内容直接返回
            return self.content

    def to_protobuf(self) -> Any:
        """
        转换为ProtoBuf格式

        Returns:
            NeuralImpulseProto消息对象
        """
        return create_neural_impulse_proto(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.content,
            metadata=self.metadata,
            routing_history=self.routing_history,
            timestamp=int(self.timestamp)
        )

    @classmethod
    def from_protobuf(cls, proto_impulse: Any) -> 'NeuralImpulse':
        """
        从ProtoBuf创建神经脉冲

        Args:
            proto_impulse: NeuralImpulseProto消息对象

        Returns:
            NeuralImpulse实例
        """
        if not ProtoBufManager.is_available():
            raise RuntimeError("ProtoBuf不可用！请先编译protobuf_schema.proto")

        # 转换ProtoBuf消息为字典
        impulse_dict = ProtoBufManager.to_dict(proto_impulse)

        # 创建NeuralImpulse实例
        impulse = cls(
            session_id=impulse_dict.get('session_id'),
            action_intent=impulse_dict.get('action_intent', 'Q_AUDIT_INPUT'),
            source_agent=impulse_dict.get('source_agent', 'SYSTEM'),
            input_source=impulse_dict.get('input_source', 'USER'),
            content=extract_content_from_impulse(proto_impulse),
            metadata=impulse_dict.get('metadata', {}),
            routing_history=impulse_dict.get('routing_history', [])
        )

        # 设置内容类型为protobuf
        impulse.metadata['content_type'] = 'protobuf'

        return impulse

    def set_text_content(self, text: str, content_type: str = "text/plain", language: str = "zh") -> None:
        """
        设置文本内容（ProtoBuf格式）

        Args:
            text: 文本内容
            content_type: 内容类型
            language: 语言代码
        """
        text_content = ProtoBufManager.create_text_content(text, content_type, language)
        self.set_protobuf_content(text_content)

    def get_text_content(self) -> str:
        """
        获取文本内容

        Returns:
            str: 文本内容
        """
        content = self.get_protobuf_content()

        # 如果是RequestContent类型，按优先级获取文本内容
        if hasattr(content, 'user_input'):
            # 优先从response_content获取（AI的响应），其次从user_input获取（用户输入）
            if hasattr(content, 'response_content') and content.response_content:
                return content.response_content
            elif content.user_input:
                return content.user_input
            else:
                return str(content)
        else:
            return str(content)

    def copy(self) -> 'NeuralImpulse':
        """
        创建神经脉冲的深拷贝

        Returns:
            NeuralImpulse: 新的神经脉冲实例
        """
        # 深拷贝所有属性
        import copy
        new_impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=copy.deepcopy(self.content) if self.content else None,
            metadata=copy.deepcopy(self.metadata),
            routing_history=copy.deepcopy(self.routing_history)
        )
        new_impulse.timestamp = self.timestamp
        return new_impulse

    def create_error_response(self, error_message: str, error_source: str = "Unknown",
                            original_session_id: str = None) -> 'NeuralImpulse':
        """
        创建错误响应的神经脉冲

        Args:
            error_message: 错误消息
            error_source: 错误来源
            original_session_id: 原始会话ID

        Returns:
            NeuralImpulse: 新的错误响应神经脉冲
        """
        import copy
        error_impulse = NeuralImpulse(
            session_id=f"error-{self.session_id[:8]}-{str(uuid.uuid4())[:8]}",
            action_intent="Q_ERROR_HANDLER",
            source_agent=error_source,
            input_source="SYSTEM",
            content=f"Error: {error_message}",
            metadata=copy.deepcopy(self.metadata)
        )

        # 添加错误相关元数据
        error_impulse.metadata['error_type'] = 'processing_error'
        error_impulse.metadata['error_message'] = error_message
        error_impulse.metadata['error_source'] = error_source
        error_impulse.metadata['original_session_id'] = original_session_id or self.session_id
        error_impulse.metadata['original_impulse_id'] = self.session_id
        error_impulse.metadata['error_timestamp'] = time.time()

        # 复制路由历史
        error_impulse.routing_history = copy.deepcopy(self.routing_history)
        error_impulse.routing_history.append(f"ERROR:{error_source}")

        return error_impulse
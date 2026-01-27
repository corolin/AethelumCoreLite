"""
神经脉冲消息包 (NeuralImpulse)

定义了在树神经系统中传递的信息包格式。
"""

import time
import uuid
import json
import zlib
import gzip
import hashlib
from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum
from dataclasses import dataclass, field
from .protobuf_utils import ProtoBufManager, create_neural_impulse_proto, extract_content_from_impulse


# 安全限制常量
MAX_JSON_SIZE = 10 * 1024 * 1024  # 10MB - 防止 DoS
MAX_STRING_LENGTH = 1024 * 1024  # 1MB - 单个字符串最大长度
MAX_NESTING_DEPTH = 100  # 最大嵌套深度


def _safe_json_loads(json_str: str) -> Dict[str, Any]:
    """安全的 JSON 解析，防止反序列化攻击

    Args:
        json_str: JSON 字符串

    Returns:
        解析后的字典

    Raises:
        ValueError: 数据过大或格式无效
        json.JSONDecodeError: JSON 解析错误
    """
    # 检查输入大小
    if len(json_str.encode('utf-8')) > MAX_JSON_SIZE:
        raise ValueError(
            f"JSON data too large: {len(json_str.encode('utf-8'))} bytes "
            f"(max: {MAX_JSON_SIZE} bytes)"
        )

    # 使用标准 JSON 解析器（Python 的 json.loads 是安全的，不会执行任意代码）
    # 但我们仍然需要限制数据大小来防止 DoS
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON data: {e.msg}",
            e.doc,
            e.pos
        )

    # 验证返回类型
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    return data


class MessagePriority(Enum):
    """消息优先级枚举"""
    CRITICAL = 0  # 关键消息，最高优先级
    HIGH = 1      # 高优先级
    NORMAL = 2    # 普通优先级
    LOW = 3       # 低优先级
    BACKGROUND = 4  # 后台任务，最低优先级


class MessageStatus(Enum):
    """消息状态枚举"""
    CREATED = "created"          # 已创建
    QUEUED = "queued"            # 已入队
    PROCESSING = "processing"    # 处理中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 处理失败
    EXPIRED = "expired"          # 已过期
    CANCELLED = "cancelled"      # 已取消


class CompressionType(Enum):
    """压缩类型枚举"""
    NONE = "none"                # 无压缩
    ZLIB = "zlib"                # ZLIB压缩
    GZIP = "gzip"                # GZIP压缩


@dataclass
class MessageValidationResult:
    """消息验证结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class NeuralImpulse:
    """
    神经脉冲 - 在神经元间传递的信息包

    基于设计文档的MessagePackage格式，增加了InputSource字段来表明消息来源
    增加了优先级、过期时间、压缩、验证和版本控制等功能
    """

    # 当前消息格式版本
    CURRENT_VERSION = "1.0.0"

    def __init__(
        self,
        session_id: Optional[str] = None,
        action_intent: str = "Q_AUDIT_INPUT",
        source_agent: str = "SYSTEM",
        input_source: str = "USER",
        content: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        routing_history: Optional[List[str]] = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        expires_at: Optional[float] = None,
        compression: CompressionType = CompressionType.NONE,
        version: str = CURRENT_VERSION,
        status: MessageStatus = MessageStatus.CREATED
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
            priority: 消息优先级
            expires_at: 消息过期时间（Unix时间戳）
            compression: 内容压缩类型
            version: 消息格式版本
            status: 消息状态
        """
        self.session_id: str = session_id or str(uuid.uuid4())
        self.action_intent: str = action_intent
        self.source_agent: str = source_agent
        self.input_source: str = input_source  # 新增字段，表明消息包来源
        self.content: Any = content
        self.metadata: Dict[str, Any] = metadata or {}
        self.routing_history: List[str] = routing_history or []
        self.timestamp: float = time.time()
        self.priority: MessagePriority = priority
        self.expires_at: Optional[float] = expires_at
        self.compression: CompressionType = compression
        self.version: str = version
        self.status: MessageStatus = status
        self._content_hash: Optional[str] = None
        self._compressed_content: Optional[bytes] = None

        # 如果需要压缩，立即压缩内容
        if self.compression != CompressionType.NONE and self.content is not None:
            self._compress_content()

    def add_to_history(self, agent_name: str) -> None:
        """添加Agent到路由历史"""
        if agent_name not in self.routing_history:
            self.routing_history.append(agent_name)

    def update_source(self, new_source: str) -> None:
        """更新源Agent"""
        self.source_agent = new_source
        self.add_to_history(new_source)

    def reroute_to_queue(self, new_intent: str) -> None:
        """重新路由到指定队列"""
        self.action_intent = new_intent

    def set_status(self, status: MessageStatus) -> None:
        """设置消息状态"""
        self.status = status
        self.metadata['status_updated_at'] = time.time()

    def is_expired(self) -> bool:
        """检查消息是否已过期"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def get_ttl(self) -> Optional[float]:
        """获取剩余生存时间（秒）"""
        if self.expires_at is None:
            return None
        ttl = self.expires_at - time.time()
        return ttl if ttl > 0 else 0

    def set_priority(self, priority: MessagePriority) -> None:
        """设置消息优先级"""
        self.priority = priority
        self.metadata['priority_updated_at'] = time.time()

    def get_info(self) -> Dict[str, Any]:
        """获取脉冲摘要信息"""
        return {
            "session_id": self.session_id,
            "action_intent": self.action_intent,
            "source_agent": self.source_agent,
            "input_source": self.input_source,
            "routing_history": self.routing_history,
            "timestamp": self.timestamp,
            "priority": self.priority.name,
            "expires_at": self.expires_at,
            "compression": self.compression.name,
            "version": self.version,
            "status": self.status.name,
            "is_expired": self.is_expired(),
            "ttl": self.get_ttl()
        }

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        # 获取内容，如果是压缩的则先解压
        content = self.get_content()
        
        return {
            "session_id": self.session_id,
            "action_intent": self.action_intent,
            "source_agent": self.source_agent,
            "input_source": self.input_source,
            "content": content,
            "metadata": self.metadata,
            "routing_history": self.routing_history,
            "timestamp": self.timestamp,
            "priority": self.priority.name,
            "expires_at": self.expires_at,
            "compression": self.compression.name,
            "version": self.version,
            "status": self.status.name,
            "content_hash": self._content_hash
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NeuralImpulse':
        """从字典创建神经脉冲"""
        # 处理枚举类型
        priority = MessagePriority.NORMAL
        if "priority" in data and isinstance(data["priority"], str):
            try:
                priority = MessagePriority[data["priority"]]
            except KeyError:
                pass

        compression = CompressionType.NONE
        if "compression" in data and isinstance(data["compression"], str):
            try:
                compression = CompressionType[data["compression"]]
            except KeyError:
                pass

        status = MessageStatus.CREATED
        if "status" in data and isinstance(data["status"], str):
            try:
                status = MessageStatus[data["status"]]
            except KeyError:
                pass

        impulse = cls(
            session_id=data.get("session_id"),
            action_intent=data.get("action_intent", "Q_AUDIT_INPUT"),
            source_agent=data.get("source_agent", "SYSTEM"),
            input_source=data.get("input_source", "USER"),
            content=data.get("content"),
            metadata=data.get("metadata"),
            routing_history=data.get("routing_history", []),
            priority=priority,
            expires_at=data.get("expires_at"),
            compression=compression,
            version=data.get("version", cls.CURRENT_VERSION),
            status=status
        )

        # 设置时间戳
        if "timestamp" in data:
            impulse.timestamp = data["timestamp"]

        # 设置内容哈希
        if "content_hash" in data:
            impulse._content_hash = data["content_hash"]

        return impulse

    def to_json(self, indent: Optional[int] = None) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'NeuralImpulse':
        """从JSON字符串创建神经脉冲（使用安全的 JSON 解析）"""
        data = _safe_json_loads(json_str)
        return cls.from_dict(data)

    def _compress_content(self) -> None:
        """压缩内容并计算哈希（仅一次）"""
        if self.content is None:
            return

        # 将内容序列化为JSON字符串
        content_str = json.dumps(self.content, ensure_ascii=False)
        content_bytes = content_str.encode('utf-8')

        # 先计算哈希（在压缩前）
        if self._content_hash is None:
            self._content_hash = hashlib.sha256(content_bytes).hexdigest()

        # 根据压缩类型进行压缩
        if self.compression == CompressionType.ZLIB:
            self._compressed_content = zlib.compress(content_bytes)
        elif self.compression == CompressionType.GZIP:
            # 使用 gzip 模块进行 GZIP 格式压缩（RFC 1952）
            self._compressed_content = gzip.compress(content_bytes, compresslevel=9)
        else:
            self._compressed_content = content_bytes

    def _decompress_content(self) -> Any:
        """解压内容"""
        if self._compressed_content is None:
            return self.content

        # 根据压缩类型进行解压
        if self.compression == CompressionType.ZLIB:
            content_bytes = zlib.decompress(self._compressed_content)
        elif self.compression == CompressionType.GZIP:
            # 使用 gzip 模块进行 GZIP 格式解压
            content_bytes = gzip.decompress(self._compressed_content)
        else:
            content_bytes = self._compressed_content

        # 将字节转换为JSON字符串，然后解析为对象（使用安全解析）
        content_str = content_bytes.decode('utf-8')

        # 检查内容大小（防止 DoS）
        if len(content_str.encode('utf-8')) > MAX_JSON_SIZE:
            raise ValueError(
                f"Compressed content too large after decompression: "
                f"{len(content_str.encode('utf-8'))} bytes (max: {MAX_JSON_SIZE} bytes)"
            )

        return json.loads(content_str)

    def get_content(self) -> Any:
        """获取内容（自动处理压缩）"""
        if self.compression != CompressionType.NONE and self._compressed_content is not None:
            return self._decompress_content()
        return self.content

    def set_content(self, content: Any, compress: Optional[bool] = None) -> None:
        """设置内容（可选压缩）"""
        self.content = content
        self._compressed_content = None
        self._content_hash = None

        # 如果指定了压缩参数，则更新压缩设置
        if compress is not None:
            if compress:
                if self.compression == CompressionType.NONE:
                    self.compression = CompressionType.ZLIB
            else:
                self.compression = CompressionType.NONE

        # 如果需要压缩，立即压缩内容
        if self.compression != CompressionType.NONE and self.content is not None:
            self._compress_content()

    def get_content_hash(self) -> Optional[str]:
        """获取内容哈希

        优化：如果已有哈希则直接返回，否则计算并缓存
        """
        if self._content_hash is None and self.content is not None:
            # 计算并缓存内容哈希
            content_str = json.dumps(self.content, ensure_ascii=False)
            content_bytes = content_str.encode('utf-8')
            self._content_hash = hashlib.sha256(content_bytes).hexdigest()
        return self._content_hash

    def validate(self, validator: Optional[Callable[['NeuralImpulse'], MessageValidationResult]] = None) -> MessageValidationResult:
        """
        验证消息

        Args:
            validator: 自定义验证函数

        Returns:
            MessageValidationResult: 验证结果
        """
        result = MessageValidationResult(is_valid=True)

        # 基本验证
        if not self.session_id:
            result.is_valid = False
            result.errors.append("会话ID不能为空")

        if not self.action_intent:
            result.is_valid = False
            result.errors.append("动作意图不能为空")

        if not self.source_agent:
            result.is_valid = False
            result.errors.append("源代理不能为空")

        if not self.input_source:
            result.is_valid = False
            result.errors.append("输入源不能为空")

        # 检查过期时间
        if self.expires_at is not None and self.is_expired():
            result.warnings.append("消息已过期")

        # 检查版本兼容性
        if self.version != self.CURRENT_VERSION:
            result.warnings.append(f"消息版本({self.version})与当前版本({self.CURRENT_VERSION})不匹配")

        # 检查内容哈希
        content_hash = self.get_content_hash()
        if self._content_hash and content_hash and self._content_hash != content_hash:
            result.is_valid = False
            result.errors.append("内容哈希不匹配，内容可能被篡改")

        # 如果提供了自定义验证器，则使用它
        if validator:
            custom_result = validator(self)
            if not custom_result.is_valid:
                result.is_valid = False
            result.errors.extend(custom_result.errors)
            result.warnings.extend(custom_result.warnings)

        return result

    def __str__(self) -> str:
        """字符串表示"""
        content_preview = str(self.get_content())[:50] + "..." if len(str(self.get_content())) > 50 else str(self.get_content())
        return f"NeuralImpulse(id={self.session_id[:8]}..., intent={self.action_intent}, from={self.source_agent}, priority={self.priority.name}, status={self.status.name}, content={content_preview})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return f"NeuralImpulse(session_id='{self.session_id}', action_intent='{self.action_intent}', source_agent='{self.source_agent}', input_source='{self.input_source}', priority={self.priority.name}, status={self.status.name})"

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

        # 重置压缩内容
        self._compressed_content = None
        self._content_hash = None

        # 如果需要压缩，立即压缩内容
        if self.compression != CompressionType.NONE:
            self._compress_content()

    def get_protobuf_content(self, expected_type: Optional[type] = None) -> Any:
        """
        获取ProtoBuf内容

        Args:
            expected_type: 期望的ProtoBuf消息类型

        Returns:
            ProtoBuf消息对象或解析后的内容
        """
        # 获取内容（自动处理压缩）
        content_obj = self.get_content()
        
        if self.metadata.get('content_type') == 'protobuf':
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
            return content_obj

    def to_protobuf(self) -> Any:
        """
        转换为ProtoBuf格式

        Returns:
            NeuralImpulseProto消息对象
        """
        # 获取内容（自动处理压缩）
        content = self.get_content()
        
        # 将CompressionType枚举转换为对应的整数
        compression_map = {
            CompressionType.NONE: 0,
            CompressionType.ZLIB: 1,
            CompressionType.GZIP: 2
        }
        compression_value = compression_map.get(self.compression, 0)
        
        # 将MessageStatus枚举转换为对应的整数
        status_map = {
            MessageStatus.CREATED: 0,
            MessageStatus.QUEUED: 1,
            MessageStatus.PROCESSING: 2,
            MessageStatus.COMPLETED: 3,
            MessageStatus.FAILED: 4,
            MessageStatus.EXPIRED: 5,
            MessageStatus.CANCELLED: 6
        }
        status_value = status_map.get(self.status, 0)
        
        return create_neural_impulse_proto(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=content,
            metadata=self.metadata,
            routing_history=self.routing_history,
            timestamp=int(self.timestamp),
            priority=self.priority.value,
            expires_at=int(self.expires_at) if self.expires_at else None,
            compression=compression_value,
            version=self.version,
            status=status_value
        )

    @classmethod
    def from_protobuf(cls, proto_impulse: Any) -> 'NeuralImpulse':
        """
        从ProtoBuf创建神经脉冲（带安全验证）

        Args:
            proto_impulse: NeuralImpulseProto消息对象

        Returns:
            NeuralImpulse实例

        Raises:
            ValueError: 消息过大或验证失败
            RuntimeError: ProtoBuf 不可用
        """
        if not ProtoBufManager.is_available():
            raise RuntimeError("ProtoBuf不可用！请先编译protobuf_schema.proto")

        # 安全检查1: 验证消息大小（防止 DoS）
        if hasattr(proto_impulse, 'ByteSize'):
            proto_size = proto_impulse.ByteSize()
            if proto_size > MAX_JSON_SIZE:  # 使用相同的限制（10MB）
                raise ValueError(
                    f"ProtoBuf message too large: {proto_size} bytes "
                    f"(max: {MAX_JSON_SIZE} bytes)"
                )

        # 安全检查2: 验证必要字段
        required_fields = ['session_id', 'action_intent']
        for field in required_fields:
            if not hasattr(proto_impulse, field) or not getattr(proto_impulse, field):
                raise ValueError(f"Missing required ProtoBuf field: {field}")

        # 转换ProtoBuf消息为字典
        try:
            impulse_dict = ProtoBufManager.to_dict(proto_impulse)
        except Exception as e:
            raise ValueError(f"Failed to parse ProtoBuf message: {repr(e)}")

        # 处理枚举类型
        priority = MessagePriority.NORMAL
        if "priority" in impulse_dict and impulse_dict["priority"] is not None:
            try:
                priority = MessagePriority(impulse_dict["priority"])
            except ValueError:
                pass

        compression = CompressionType.NONE
        if "compression" in impulse_dict and impulse_dict["compression"] is not None:
            try:
                # 将整数转换为对应的CompressionType枚举
                compression_int = impulse_dict["compression"]
                compression_map = {
                    0: CompressionType.NONE,
                    1: CompressionType.ZLIB,
                    2: CompressionType.GZIP
                }
                compression = compression_map.get(compression_int, CompressionType.NONE)
            except (ValueError, TypeError):
                pass

        status = MessageStatus.CREATED
        if "status" in impulse_dict and impulse_dict["status"] is not None:
            try:
                # 将整数转换为对应的MessageStatus枚举
                status_int = impulse_dict["status"]
                status_map = {
                    0: MessageStatus.CREATED,
                    1: MessageStatus.QUEUED,
                    2: MessageStatus.PROCESSING,
                    3: MessageStatus.COMPLETED,
                    4: MessageStatus.FAILED,
                    5: MessageStatus.EXPIRED,
                    6: MessageStatus.CANCELLED
                }
                status = status_map.get(status_int, MessageStatus.CREATED)
            except (ValueError, TypeError):
                pass

        # 创建NeuralImpulse实例
        impulse = cls(
            session_id=impulse_dict.get('session_id'),
            action_intent=impulse_dict.get('action_intent', 'Q_AUDIT_INPUT'),
            source_agent=impulse_dict.get('source_agent', 'SYSTEM'),
            input_source=impulse_dict.get('input_source', 'USER'),
            content=extract_content_from_impulse(proto_impulse),
            metadata=impulse_dict.get('metadata', {}),
            routing_history=impulse_dict.get('routing_history', []),
            priority=priority,
            expires_at=impulse_dict.get('expires_at'),
            compression=compression,
            version=impulse_dict.get('version', cls.CURRENT_VERSION),
            status=status
        )

        # 设置时间戳
        if "timestamp" in impulse_dict:
            impulse.timestamp = impulse_dict["timestamp"]

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
            content=copy.deepcopy(self.get_content()) if self.get_content() else None,
            metadata=copy.deepcopy(self.metadata),
            routing_history=copy.deepcopy(self.routing_history),
            priority=self.priority,
            expires_at=self.expires_at,
            compression=self.compression,
            version=self.version,
            status=self.status
        )
        new_impulse.timestamp = self.timestamp
        new_impulse._content_hash = self._content_hash
        new_impulse._compressed_content = self._compressed_content
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
        from .protobuf_schema_pb2 import ErrorInfo
        
        # 创建ErrorInfo对象
        error_info = ErrorInfo()
        error_info.error_code = 500  # 默认错误代码
        error_info.error_message = error_message
        error_info.error_source = error_source
        
        error_impulse = NeuralImpulse(
            session_id=original_session_id or self.session_id,
            action_intent="error_response",
            source_agent=error_source,
            input_source="SYSTEM",
            content=error_info,
            metadata=copy.deepcopy(self.metadata),
            priority=MessagePriority.HIGH,  # 错误消息使用高优先级
            status=MessageStatus.FAILED
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

    def create_response(self, response_content: Any, action_intent: str = None,
                       source_agent: str = None, priority: MessagePriority = None) -> 'NeuralImpulse':
        """
        创建响应神经脉冲

        Args:
            response_content: 响应内容
            action_intent: 下一个动作意图
            source_agent: 响应源代理
            priority: 响应优先级

        Returns:
            NeuralImpulse: 新的响应神经脉冲
        """
        import copy
        response_impulse = NeuralImpulse(
            session_id=f"resp-{self.session_id[:8]}-{str(uuid.uuid4())[:8]}",
            action_intent=action_intent or "response",  # 默认使用"response"而不是self.action_intent
            source_agent=source_agent or self.source_agent,
            input_source="SYSTEM",
            content=response_content,
            metadata=copy.deepcopy(self.metadata),
            routing_history=copy.deepcopy(self.routing_history),
            priority=priority or self.priority,
            status=MessageStatus.CREATED
        )

        # 添加响应相关元数据
        response_impulse.metadata['response_to'] = self.session_id
        response_impulse.metadata['response_timestamp'] = time.time()

        return response_impulse

    def to_bytes(self) -> bytes:
        """
        将神经脉冲序列化为字节

        Returns:
            bytes: 序列化后的字节数据
        """
        # 使用JSON序列化，然后压缩
        json_str = self.to_json()
        json_bytes = json_str.encode('utf-8')
        return zlib.compress(json_bytes)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'NeuralImpulse':
        """
        从字节数据反序列化神经脉冲

        Args:
            data: 序列化后的字节数据

        Returns:
            NeuralImpulse: 反序列化后的神经脉冲
        """
        # 解压缩，然后使用JSON反序列化
        json_bytes = zlib.decompress(data)
        json_str = json_bytes.decode('utf-8')
        return cls.from_json(json_str)

    def estimate_size(self) -> int:
        """
        估算神经脉冲的大小（字节）

        Returns:
            int: 估算的大小（字节）
        """
        # 序列化为JSON并计算大小
        json_str = self.to_json()
        return len(json_str.encode('utf-8'))

    def is_compressed(self) -> bool:
        """
        检查内容是否已压缩

        Returns:
            bool: 是否已压缩
        """
        return self.compression != CompressionType.NONE and self._compressed_content is not None

    def get_compression_ratio(self) -> Optional[float]:
        """
        获取压缩比

        Returns:
            Optional[float]: 压缩比（压缩后大小/原始大小），如果未压缩则返回None
        """
        if not self.is_compressed():
            return None

        # 计算原始大小
        content_str = json.dumps(self.content, ensure_ascii=False)
        original_size = len(content_str.encode('utf-8'))

        # 计算压缩后大小
        compressed_size = len(self._compressed_content)

        return compressed_size / original_size if original_size > 0 else 1.0
        
    reroute_to = reroute_to_queue  # 保持向后兼容，别名为 reroute_to_queue

    def change_source_agent(self, new_source_agent: str) -> None:
        """
        更改源代理并记录路由历史

        Args:
            new_source_agent: 新的源代理名称
        """
        # 保存原始源代理到路由历史
        if self.source_agent not in self.routing_history:
            self.routing_history.append(self.source_agent)

        # 更新源代理
        self.source_agent = new_source_agent

        # 添加路由记录
        self.routing_history.append(f"changed_source_to:{new_source_agent}")
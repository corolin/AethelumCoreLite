"""
ProtoBuf工具模块

提供ProtoBuf序列化/反序列化和消息处理功能。
"""

import json
import base64
import time
from typing import Any, Dict, List, Optional, Union

# ProtoBuf 相关模块（protobuf 是核心依赖，会自动安装）
from google.protobuf import any_pb2
from google.protobuf.json_format import MessageToDict, Parse
import google.protobuf.json_format as json_format
from google.protobuf.message import Message
from google.protobuf.struct_pb2 import Struct, Value
from google.protobuf.json_format import ParseError
from . import protobuf_schema_pb2

from .protobuf_schema_pb2 import (
    NeuralImpulseProto,
    RequestContent,
    TextContent,
    BinaryContent,
    StructuredContent,
    ErrorInfo
)

PROTOBUF_AVAILABLE = True


class ProtoBufManager:
    """ProtoBuf消息管理器"""
    
    # 类级别的缓存，用于序列化结果
    _serialization_cache = {}
    _cache_max_size = 1000
    _cache_hit_count = 0
    _cache_miss_count = 0

    @staticmethod
    def is_available() -> bool:
        """检查ProtoBuf是否可用"""
        return PROTOBUF_AVAILABLE
    
    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'cache_size': len(ProtoBufManager._serialization_cache),
            'max_size': ProtoBufManager._cache_max_size,
            'hit_count': ProtoBufManager._cache_hit_count,
            'miss_count': ProtoBufManager._cache_miss_count,
            'hit_rate': (
                ProtoBufManager._cache_hit_count / 
                max(1, ProtoBufManager._cache_hit_count + ProtoBufManager._cache_miss_count)
            )
        }
    
    @staticmethod
    def clear_cache():
        """清空缓存"""
        ProtoBufManager._serialization_cache.clear()
        ProtoBufManager._cache_hit_count = 0
        ProtoBufManager._cache_miss_count = 0
    
    @staticmethod
    def _get_cache_key(data: Any) -> str:
        """生成缓存键"""
        if isinstance(data, str):
            return f"str_{hash(data)}"
        elif hasattr(data, 'SerializeToString'):
            return f"pb_{hash(data.SerializeToString())}"
        else:
            return f"json_{hash(str(data))}"

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
        request_id: Optional[str] = None,
        model_name: str = "",
        processing_time: int = 0,
        token_count: int = 0,
        audit_result: str = "",
        audit_score: str = "",
        audit_metadata: Dict[str, str] = None,
        is_sensitive: bool = False,
        encryption_method: str = "",
        **kwargs
    ) -> Any:
        """创建统一的请求内容消息"""
        request_content = protobuf_schema_pb2.RequestContent()
        request_content.user_input = user_input
        request_content.content_type = content_type

        # 基础字段
        if request_id:
            request_content.request_id = request_id
        if model_name:
            request_content.model_name = model_name
        request_content.processing_time = processing_time
        request_content.token_count = token_count
        
        # 审计相关字段
        if caesar_shift:
            request_content.caesar_shift = caesar_shift
        if nonce:
            request_content.nonce = nonce
        if audit_result:
            request_content.audit_result = audit_result
        if audit_score:
            request_content.audit_score = audit_score
        if audit_metadata:
            for key, value in audit_metadata.items():
                request_content.audit_metadata[key] = value
        request_content.is_sensitive = is_sensitive
        
        # 加密相关字段
        if encryption_method:
            request_content.encryption_method = encryption_method

        # 处理其他关键字段
        for key, value in kwargs.items():
            if hasattr(request_content, key):
                setattr(request_content, key, value)

        return request_content

    @staticmethod
    def create_business_response(
        response_content: str,
        model_name: str = "unknown",
        user_input: str = "",
        request_id: Optional[str] = None,
        processing_time: int = 0,
        token_count: int = 0,
        audit_result: str = "",
        audit_score: str = "",
        **kwargs
    ) -> Any:
        """创建业务响应消息"""
        request_content = protobuf_schema_pb2.RequestContent()
        request_content.user_input = user_input
        request_content.response_content = response_content
        request_content.model_name = model_name
        request_content.content_type = "output"
        request_content.processing_time = processing_time
        request_content.token_count = token_count
        
        if request_id:
            request_content.request_id = request_id
        if audit_result:
            request_content.audit_result = audit_result
        if audit_score:
            request_content.audit_score = audit_score
            
        # 处理其他字段
        for key, value in kwargs.items():
            if hasattr(request_content, key):
                setattr(request_content, key, value)

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
        timestamp: int,
        priority: int = 2,
        expires_at: int = 0,
        compression: int = 0,
        version: str = "1.0",
        status: int = 0,
        content_hash: str = "",
        correlation_id: str = "",
        parent_session_id: str = "",
        child_session_ids: list = None,
        batch_id: str = "",
        batch_index: int = 0,
        batch_total: int = 0,
        validation_info: Optional[Any] = None,
        performance_stats: Optional[Any] = None,
        compatibility_info: Optional[Any] = None,
        is_encrypted: bool = False,
        encryption_key_id: str = "",
        requires_audit: bool = False,
        audit_level: str = "low",
        audit_trail: list = None,
        max_retry_count: int = 3,
        current_retry_count: int = 0,
        last_retry_time: int = 0,
        retry_strategy: str = "exponential",
        resource_limits: Dict[str, str] = None
    ) -> Any:
        """创建神经脉冲消息"""
        impulse = protobuf_schema_pb2.NeuralImpulseProto()
        impulse.session_id = session_id
        impulse.action_intent = action_intent
        impulse.source_agent = source_agent
        impulse.input_source = input_source
        
        # 处理元数据
        if metadata:
            for key, value in metadata.items():
                impulse.metadata[key] = json.dumps(value, ensure_ascii=False)

        # 处理路由历史
        if routing_history:
            impulse.routing_history.extend(routing_history)
            
        # 处理时间戳，如果未提供则使用当前时间
        if timestamp is None:
            impulse.timestamp = int(time.time())
        else:
            impulse.timestamp = timestamp
            
        # 基础字段
        impulse.priority = priority
        impulse.expires_at = expires_at if expires_at is not None else 0
        impulse.status = status
        impulse.version = version
        impulse.content_hash = content_hash
        
        # 处理compression参数，确保它是整数
        if isinstance(compression, str):
            compression_map = {"none": 0, "zlib": 1, "gzip": 2}
            impulse.compression = compression_map.get(compression.lower(), 0)
        else:
            impulse.compression = compression
            
        # 扩展字段
        impulse.correlation_id = correlation_id
        impulse.parent_session_id = parent_session_id
        if child_session_ids:
            impulse.child_session_ids.extend(child_session_ids)
        impulse.batch_id = batch_id
        impulse.batch_index = batch_index
        impulse.batch_total = batch_total
        
        # 验证和兼容性字段
        if validation_info:
            impulse.validation_info.CopyFrom(validation_info)
        if performance_stats:
            impulse.performance_stats.CopyFrom(performance_stats)
        if compatibility_info:
            impulse.compatibility_info.CopyFrom(compatibility_info)
            
        # 安全和审计字段
        impulse.is_encrypted = is_encrypted
        impulse.encryption_key_id = encryption_key_id
        impulse.requires_audit = requires_audit
        impulse.audit_level = audit_level
        if audit_trail:
            impulse.audit_trail.extend(audit_trail)
            
        # 资源管理字段
        impulse.max_retry_count = max_retry_count
        impulse.current_retry_count = current_retry_count
        impulse.last_retry_time = last_retry_time
        impulse.retry_strategy = retry_strategy
        if resource_limits:
            for key, value in resource_limits.items():
                impulse.resource_limits[key] = value

        # 处理内容
        if hasattr(content, 'SerializeToString'):
            impulse.content.CopyFrom(ProtoBufManager.pack_any(content))
        elif isinstance(content, str):
            request_content = ProtoBufManager.create_request_content(user_input=content, content_type="input")
            impulse.content.CopyFrom(ProtoBufManager.pack_any(request_content))
        else:
            json_content = json.dumps(content, ensure_ascii=False)
            request_content = ProtoBufManager.create_request_content(user_input=json_content, content_type="json")
            impulse.content.CopyFrom(ProtoBufManager.pack_any(request_content))

        return impulse

    @staticmethod
    def pack_any(message: Any) -> Any:
        """将消息包装为Any类型"""
        any_msg = any_pb2.Any()
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
    metadata: Dict[str, Any] = None,
    routing_history: list = None,
    timestamp: int = None,
    priority: int = 2,
    expires_at: int = 0,
    compression: int = 0,
    version: str = "1.0",
    status: int = 0,
    content_hash: str = ""
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
        timestamp=timestamp,
        priority=priority,
        expires_at=expires_at,
        compression=compression,
        version=version,
        status=status,
        content_hash=content_hash
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


class MessageValidator:
    """消息验证器"""
    
    @staticmethod
    def validate_neural_impulse(impulse: Any) -> tuple[bool, list]:
        """
        验证神经脉冲消息的完整性
        
        Returns:
            tuple: (是否有效, 错误消息列表)
        """
        errors = []
        
        # 基础字段验证
        if not impulse.session_id:
            errors.append("session_id不能为空")
        if not impulse.action_intent:
            errors.append("action_intent不能为空")
        if not impulse.source_agent:
            errors.append("source_agent不能为空")
            
        # 时间戳验证
        if impulse.timestamp <= 0:
            errors.append("timestamp必须为正数")
            
        # 优先级验证
        if not (0 <= impulse.priority <= 4):
            errors.append("priority必须在0-4范围内")
            
        # 状态验证
        if not (0 <= impulse.status <= 6):
            errors.append("status必须在0-6范围内")
            
        # 内容哈希验证（如果设置了）
        if impulse.content_hash:
            calculated_hash = ProtoBufManager.calculate_content_hash(impulse)
            if calculated_hash != impulse.content_hash:
                errors.append(f"内容哈希不匹配：期望{impulse.content_hash}，实际{calculated_hash}")
                
        # 过期时间验证
        if impulse.expires_at > 0 and impulse.expires_at < int(time.time()):
            errors.append("消息已过期")
            
        return len(errors) == 0, errors
    
    @staticmethod
    def calculate_content_hash(impulse: Any) -> str:
        """计算消息内容哈希"""
        import hashlib
        
        # 使用内容和其他关键字段生成哈希
        content_str = ""
        if impulse.HasField('content'):
            content_str = impulse.content.SerializeToString().hex()
            
        hash_input = f"{impulse.session_id}{impulse.action_intent}{content_str}{impulse.timestamp}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


class BatchProcessor:
    """批量处理器"""
    
    @staticmethod
    def serialize_batch(impulses: list) -> bytes:
        """批量序列化神经脉冲"""
        import gzip
        
        batch_data = []
        for impulse in impulses:
            serialized = impulse.SerializeToString()
            batch_data.append(serialized)
            
        # 压缩批量数据
        combined_data = b''.join(batch_data)
        return gzip.compress(combined_data)
    
    @staticmethod
    def deserialize_batch(data: bytes) -> list:
        """批量反序列化神经脉冲"""
        import gzip
        
        # 解压缩数据
        combined_data = gzip.decompress(data)
        
        # 分割和反序列化每个消息
        impulses = []
        offset = 0
        while offset < len(combined_data):
            # 读取消息长度（前4字节）
            if offset + 4 > len(combined_data):
                break
            msg_length = int.from_bytes(combined_data[offset:offset+4], byteorder='big')
            offset += 4
            
            # 读取消息内容
            if offset + msg_length > len(combined_data):
                break
            msg_data = combined_data[offset:offset+msg_length]
            offset += msg_length
            
            # 反序列化消息
            impulse = protobuf_schema_pb2.NeuralImpulseProto()
            impulse.ParseFromString(msg_data)
            impulses.append(impulse)
            
        return impulses
    
    @staticmethod
    def serialize_batch_with_length(impulses: list) -> bytes:
        """带长度标记的批量序列化"""
        batch_data = []
        for impulse in impulses:
            serialized = impulse.SerializeToString()
            # 添加长度前缀
            length_bytes = len(serialized).to_bytes(4, byteorder='big')
            batch_data.append(length_bytes + serialized)
            
        return b''.join(batch_data)


# 性能优化的序列化函数，支持缓存
def serialize_with_cache(impulse: Any) -> bytes:
    """带缓存的序列化"""
    cache_key = ProtoBufManager._get_cache_key(impulse)
    
    # 检查缓存
    if cache_key in ProtoBufManager._serialization_cache:
        ProtoBufManager._cache_hit_count += 1
        return ProtoBufManager._serialization_cache[cache_key]
    
    # 缓存未命中，执行序列化
    ProtoBufManager._cache_miss_count += 1
    serialized = impulse.SerializeToString()
    
    # 更新缓存（如果缓存未满，使用LRU策略）
    if len(ProtoBufManager._serialization_cache) >= ProtoBufManager._cache_max_size:
        # 移除最旧的条目（简单的LRU实现）
        oldest_key = next(iter(ProtoBufManager._serialization_cache))
        del ProtoBufManager._serialization_cache[oldest_key]
    
    ProtoBufManager._serialization_cache[cache_key] = serialized
    return serialized


class PerformanceOptimizer:
    """性能优化器"""
    
    @staticmethod
    def compress_content(data: bytes, method: str = "gzip") -> bytes:
        """压缩内容"""
        if method == "gzip":
            import gzip
            return gzip.compress(data)
        elif method == "zlib":
            import zlib
            return zlib.compress(data)
        else:
            return data
    
    @staticmethod
    def decompress_content(data: bytes, method: str = "gzip") -> bytes:
        """解压缩内容"""
        if method == "gzip":
            import gzip
            return gzip.decompress(data)
        elif method == "zlib":
            import zlib
            return zlib.decompress(data)
        else:
            return data
    
    @staticmethod
    def optimize_for_size(impulse: Any) -> Any:
        """优化消息大小"""
        # 移除空字段
        if not impulse.content_hash:
            impulse.content_hash = ""
        if not impulse.correlation_id:
            impulse.correlation_id = ""
        if not impulse.parent_session_id:
            impulse.parent_session_id = ""
            
        # 压缩长字符串字段
        if len(impulse.metadata) > 10:
            # 将metadata转换为压缩格式
            import json
            metadata_json = json.dumps(dict(impulse.metadata))
            compressed = PerformanceOptimizer.compress_content(metadata_json.encode())
            # 存储到扩展字段
            impulse.metadata["_compressed_metadata"] = compressed.hex()
            
        return impulse
    
    @staticmethod
    def measure_serialization_time(impulse: Any, iterations: int = 1000) -> Dict[str, float]:
        """测量序列化性能"""
        import time
        
        # 测试标准序列化
        start_time = time.time()
        for _ in range(iterations):
            standard_result = impulse.SerializeToString()
        standard_time = (time.time() - start_time) / iterations
        
        # 测试缓存序列化
        start_time = time.time()
        for _ in range(iterations):
            cache_result = serialize_with_cache(impulse)
        cache_time = (time.time() - start_time) / iterations
        
        # 测试批量序列化
        batch_impulses = [impulse] * 10
        start_time = time.time()
        for _ in range(iterations // 10):
            batch_result = BatchProcessor.serialize_batch_with_length(batch_impulses)
        batch_time = (time.time() - start_time) / (iterations // 10) / 10
        
        return {
            'standard_time': standard_time,
            'cache_time': cache_time,
            'batch_time': batch_time,
            'cache_speedup': standard_time / max(cache_time, 0.000001),
            'batch_speedup': standard_time / max(batch_time, 0.000001)
        }


class MemoryManager:
    """内存管理器"""
    
    def __init__(self, max_memory_mb: int = 100):
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.current_memory_usage = 0
        self.memory_pools = {}
        
    def allocate_for_serialization(self, estimated_size: int) -> bool:
        """分配序列化内存"""
        if self.current_memory_usage + estimated_size > self.max_memory_bytes:
            # 触发内存清理
            self._cleanup_memory()
            
        if self.current_memory_usage + estimated_size > self.max_memory_bytes:
            return False
            
        self.current_memory_usage += estimated_size
        return True
    
    def deallocate_memory(self, size: int):
        """释放内存"""
        self.current_memory_usage = max(0, self.current_memory_usage - size)
    
    def _cleanup_memory(self):
        """清理内存"""
        # 清理ProtoBufManager缓存
        if len(ProtoBufManager._serialization_cache) > 100:
            # 保留最常用的100个条目
            items = list(ProtoBufManager._serialization_cache.items())
            ProtoBufManager._serialization_cache = dict(items[:100])
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存统计"""
        return {
            'current_usage_bytes': self.current_memory_usage,
            'max_usage_bytes': self.max_memory_bytes,
            'usage_percentage': (self.current_memory_usage / self.max_memory_bytes) * 100,
            'cache_size': len(ProtoBufManager._serialization_cache)
        }


# 全局内存管理器实例
_global_memory_manager = MemoryManager()

def get_memory_manager() -> MemoryManager:
    """获取全局内存管理器"""
    return _global_memory_manager


def create_validation_info(is_valid: bool, validation_errors: list = None, 
                         schema_version: str = "1.0") -> Any:
    """创建验证信息"""
    validation_info = protobuf_schema_pb2.ValidationInfo()
    validation_info.is_valid = is_valid
    if validation_errors:
        validation_info.validation_errors.extend(validation_errors)
    validation_info.schema_version = schema_version
    validation_info.validation_timestamp = int(time.time())
    return validation_info


def create_performance_stats(creation_time: int = None) -> Any:
    """创建性能统计信息"""
    stats = protobuf_schema_pb2.PerformanceStats()
    current_time = int(time.time())
    stats.creation_time = creation_time or current_time
    stats.processing_start_time = current_time
    return stats


def create_compatibility_info(min_version: str = "1.0", max_version: str = "1.0") -> Any:
    """创建兼容性信息"""
    info = protobuf_schema_pb2.CompatibilityInfo()
    info.min_compatible_version = min_version
    info.max_compatible_version = max_version
    return info


class CompatibilityManager:
    """兼容性管理器"""
    
    VERSION_MAPPINGS = {
        "1.0": {
            "fields": ["session_id", "action_intent", "source_agent", "input_source", 
                      "content", "metadata", "routing_history", "timestamp"],
            "new_fields": ["priority", "expires_at", "compression", "version", "status", "content_hash"]
        },
        "1.1": {
            "fields": ["session_id", "action_intent", "source_agent", "input_source", 
                      "content", "metadata", "routing_history", "timestamp", "priority", 
                      "expires_at", "compression", "version", "status", "content_hash"],
            "new_fields": ["correlation_id", "parent_session_id", "child_session_ids", 
                          "batch_id", "batch_index", "batch_total"]
        },
        "1.2": {
            "fields": ["session_id", "action_intent", "source_agent", "input_source", 
                      "content", "metadata", "routing_history", "timestamp", "priority", 
                      "expires_at", "compression", "version", "status", "content_hash",
                      "correlation_id", "parent_session_id", "child_session_ids", 
                      "batch_id", "batch_index", "batch_total"],
            "new_fields": ["validation_info", "performance_stats", "compatibility_info",
                          "is_encrypted", "encryption_key_id", "requires_audit", 
                          "audit_level", "audit_trail", "max_retry_count", 
                          "current_retry_count", "last_retry_time", "retry_strategy",
                          "resource_limits"]
        }
    }
    
    @staticmethod
    def upgrade_message(impulse: Any, target_version: str = "1.2") -> Any:
        """升级消息到目标版本"""
        current_version = impulse.version or "1.0"
        
        if current_version == target_version:
            return impulse
            
        # 根据版本差异进行升级
        upgrade_path = CompatibilityManager._get_upgrade_path(current_version, target_version)
        
        for step_version in upgrade_path:
            impulse = CompatibilityManager._apply_upgrade_step(impulse, step_version)
            
        impulse.version = target_version
        return impulse
    
    @staticmethod
    def _get_upgrade_path(current: str, target: str) -> list:
        """获取升级路径"""
        versions = sorted(CompatibilityManager.VERSION_MAPPINGS.keys())
        current_index = versions.index(current) if current in versions else -1
        target_index = versions.index(target) if target in versions else len(versions) - 1
        
        if current_index >= target_index:
            return []
            
        return versions[current_index + 1:target_index + 1]
    
    @staticmethod
    def _apply_upgrade_step(impulse: Any, version: str) -> Any:
        """应用升级步骤"""
        if version in CompatibilityManager.VERSION_MAPPINGS:
            mapping = CompatibilityManager.VERSION_MAPPINGS[version]
            
            # 初始化新字段为默认值
            for field in mapping.get("new_fields", []):
                if not hasattr(impulse, field) or getattr(impulse, field) is None:
                    default_value = CompatibilityManager._get_default_value(field)
                    if default_value is not None:
                        setattr(impulse, field, default_value)
                        
        return impulse
    
    @staticmethod
    def _get_default_value(field_name: str) -> Any:
        """获取字段默认值"""
        defaults = {
            "priority": 2,
            "expires_at": 0,
            "compression": 0,
            "version": "1.0",
            "status": 0,
            "content_hash": "",
            "correlation_id": "",
            "parent_session_id": "",
            "child_session_ids": [],
            "batch_id": "",
            "batch_index": 0,
            "batch_total": 0,
            "is_encrypted": False,
            "encryption_key_id": "",
            "requires_audit": False,
            "audit_level": "low",
            "audit_trail": [],
            "max_retry_count": 3,
            "current_retry_count": 0,
            "last_retry_time": 0,
            "retry_strategy": "exponential",
            "resource_limits": {}
        }
        return defaults.get(field_name)
    
    @staticmethod
    def downgrade_message(impulse: Any, target_version: str) -> Any:
        """降级消息到目标版本"""
        current_version = impulse.version or "1.2"
        
        if current_version == target_version:
            return impulse
            
        # 获取降级路径
        versions = sorted(CompatibilityManager.VERSION_MAPPINGS.keys(), reverse=True)
        
        for version in versions:
            if version <= current_version and version > target_version:
                impulse = CompatibilityManager._apply_downgrade_step(impulse, version)
                
        impulse.version = target_version
        return impulse
    
    @staticmethod
    def _apply_downgrade_step(impulse: Any, version: str) -> Any:
        """应用降级步骤"""
        if version in CompatibilityManager.VERSION_MAPPINGS:
            mapping = CompatibilityManager.VERSION_MAPPINGS[version]
            
            # 移除新字段
            for field in mapping.get("new_fields", []):
                if hasattr(impulse, field):
                    # 将重要信息保存到metadata中
                    CompatibilityManager._preserve_field_info(impulse, field)
                    # 重置字段为默认值
                    default_value = CompatibilityManager._get_default_value(field)
                    if default_value is not None:
                        setattr(impulse, field, default_value)
                        
        return impulse
    
    @staticmethod
    def _preserve_field_info(impulse: Any, field_name: str):
        """在metadata中保留字段信息"""
        import json
        
        field_value = getattr(impulse, field_name)
        if field_value and field_value != CompatibilityManager._get_default_value(field_name):
            # 将字段值保存到metadata中
            metadata_key = f"downgraded_{field_name}"
            if isinstance(field_value, (list, dict)):
                impulse.metadata[metadata_key] = json.dumps(field_value, ensure_ascii=False)
            else:
                impulse.metadata[metadata_key] = str(field_value)


class MessageTransformer:
    """消息转换器"""
    
    @staticmethod
    def transform_to_dict(impulse: Any) -> Dict[str, Any]:
        """将消息转换为字典格式"""
        result = {
            'session_id': impulse.session_id,
            'action_intent': impulse.action_intent,
            'source_agent': impulse.source_agent,
            'input_source': impulse.input_source,
            'metadata': dict(impulse.metadata),
            'routing_history': list(impulse.routing_history),
            'timestamp': impulse.timestamp,
            'priority': impulse.priority,
            'expires_at': impulse.expires_at,
            'compression': impulse.compression,
            'version': impulse.version,
            'status': impulse.status,
            'content_hash': impulse.content_hash
        }
        
        # 扩展字段
        if hasattr(impulse, 'correlation_id'):
            result['correlation_id'] = impulse.correlation_id
        if hasattr(impulse, 'parent_session_id'):
            result['parent_session_id'] = impulse.parent_session_id
        if hasattr(impulse, 'child_session_ids'):
            result['child_session_ids'] = list(impulse.child_session_ids)
        if hasattr(impulse, 'batch_id'):
            result['batch_id'] = impulse.batch_id
        if hasattr(impulse, 'batch_index'):
            result['batch_index'] = impulse.batch_index
        if hasattr(impulse, 'batch_total'):
            result['batch_total'] = impulse.batch_total
            
        # 转换内容
        if impulse.HasField('content'):
            content = extract_content_from_impulse(impulse)
            if hasattr(content, 'user_input'):
                result['content'] = {
                    'user_input': content.user_input,
                    'response_content': content.response_content,
                    'content_type': content.content_type,
                    'language': getattr(content, 'language', ''),
                    'model_name': getattr(content, 'model_name', ''),
                    'processing_time': getattr(content, 'processing_time', 0),
                    'token_count': getattr(content, 'token_count', 0)
                }
            else:
                result['content'] = {'raw': str(content)}
                
        return result
    
    @staticmethod
    def transform_from_dict(data: Dict[str, Any]) -> Any:
        """从字典创建消息"""
        # 基础字段
        session_id = data.get('session_id', '')
        action_intent = data.get('action_intent', '')
        source_agent = data.get('source_agent', '')
        input_source = data.get('input_source', '')
        metadata = data.get('metadata', {})
        routing_history = data.get('routing_history', [])
        timestamp = data.get('timestamp', int(time.time()))
        priority = data.get('priority', 2)
        expires_at = data.get('expires_at', 0)
        compression = data.get('compression', 0)
        version = data.get('version', '1.2')
        status = data.get('status', 0)
        content_hash = data.get('content_hash', '')
        
        # 扩展字段
        correlation_id = data.get('correlation_id', '')
        parent_session_id = data.get('parent_session_id', '')
        child_session_ids = data.get('child_session_ids', [])
        batch_id = data.get('batch_id', '')
        batch_index = data.get('batch_index', 0)
        batch_total = data.get('batch_total', 0)
        
        # 创建内容
        content_data = data.get('content', {})
        if isinstance(content_data, dict) and 'user_input' in content_data:
            content = ProtoBufManager.create_request_content(
                user_input=content_data.get('user_input', ''),
                response_content=content_data.get('response_content', ''),
                content_type=content_data.get('content_type', 'text'),
                model_name=content_data.get('model_name', ''),
                processing_time=content_data.get('processing_time', 0),
                token_count=content_data.get('token_count', 0)
            )
        else:
            content = str(content_data)
            
        # 创建消息
        return ProtoBufManager.create_neural_impulse(
            session_id=session_id,
            action_intent=action_intent,
            source_agent=source_agent,
            input_source=input_source,
            content=content,
            metadata=metadata,
            routing_history=routing_history,
            timestamp=timestamp,
            priority=priority,
            expires_at=expires_at,
            compression=compression,
            version=version,
            status=status,
            content_hash=content_hash,
            correlation_id=correlation_id,
            parent_session_id=parent_session_id,
            child_session_ids=child_session_ids,
            batch_id=batch_id,
            batch_index=batch_index,
            batch_total=batch_total
        )
    
    @staticmethod
    def transform_to_json(impulse: Any) -> str:
        """将消息转换为JSON字符串"""
        data = MessageTransformer.transform_to_dict(impulse)
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    @staticmethod
    def transform_from_json(json_str: str) -> Any:
        """从JSON字符串创建消息"""
        data = json.loads(json_str)
        return MessageTransformer.transform_from_dict(data)
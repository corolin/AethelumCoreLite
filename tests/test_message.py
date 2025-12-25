import unittest
import time
from datetime import datetime
from aethelum_core_lite.core.message import NeuralImpulse, MessageStatus, MessagePriority, CompressionType
from aethelum_core_lite.core.protobuf_schema_pb2 import NeuralImpulseProto, RequestContent, ErrorInfo
from aethelum_core_lite.core.protobuf_utils import create_neural_impulse_proto


class TestNeuralImpulse(unittest.TestCase):
    """测试NeuralImpulse类的功能"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.session_id = "test_session_123"
        self.action_intent = "test_action"
        self.source_agent = "test_agent"
        self.input_source = "test_input"
        self.test_content = "This is a test message"
        
    def test_neural_impulse_creation(self):
        """测试NeuralImpulse对象的创建"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content
        )
        
        self.assertEqual(impulse.session_id, self.session_id)
        self.assertEqual(impulse.action_intent, self.action_intent)
        self.assertEqual(impulse.source_agent, self.source_agent)
        self.assertEqual(impulse.input_source, self.input_source)
        self.assertEqual(impulse.get_text_content(), self.test_content)
        
    def test_neural_impulse_priority(self):
        """测试NeuralImpulse的优先级功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content,
            priority=MessagePriority.HIGH
        )
        
        self.assertEqual(impulse.priority, MessagePriority.HIGH)
        
    def test_neural_impulse_expires_at(self):
        """测试NeuralImpulse的过期时间功能"""
        expires_at = int(time.time()) + 3600  # 1小时后过期
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content,
            expires_at=expires_at
        )
        
        self.assertEqual(impulse.expires_at, expires_at)
        
    def test_neural_impulse_to_protobuf(self):
        """测试NeuralImpulse转换为protobuf"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content,
            priority=MessagePriority.HIGH
        )
        
        proto = impulse.to_protobuf()
        self.assertIsInstance(proto, NeuralImpulseProto)
        self.assertEqual(proto.session_id, self.session_id)
        self.assertEqual(proto.action_intent, self.action_intent)
        self.assertEqual(proto.source_agent, self.source_agent)
        self.assertEqual(proto.input_source, self.input_source)
        self.assertEqual(proto.priority, MessagePriority.HIGH.value)
        
    def test_neural_impulse_from_protobuf(self):
        """测试从protobuf创建NeuralImpulse"""
        # 创建protobuf对象
        proto = create_neural_impulse_proto(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content,
            priority=MessagePriority.HIGH.value
        )
        
        # 从protobuf创建NeuralImpulse
        impulse = NeuralImpulse.from_protobuf(proto)
        
        self.assertEqual(impulse.session_id, self.session_id)
        self.assertEqual(impulse.action_intent, self.action_intent)
        self.assertEqual(impulse.source_agent, self.source_agent)
        self.assertEqual(impulse.input_source, self.input_source)
        self.assertEqual(impulse.priority, MessagePriority.HIGH)
        
    def test_neural_impulse_serialization(self):
        """测试NeuralImpulse的序列化和反序列化"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content,
            priority=MessagePriority.HIGH
        )
        
        # 序列化为字节
        serialized = impulse.to_bytes()
        self.assertIsInstance(serialized, bytes)
        
        # 从字节反序列化
        deserialized = NeuralImpulse.from_bytes(serialized)
        
        self.assertEqual(deserialized.session_id, impulse.session_id)
        self.assertEqual(deserialized.action_intent, impulse.action_intent)
        self.assertEqual(deserialized.source_agent, impulse.source_agent)
        self.assertEqual(deserialized.input_source, impulse.input_source)
        self.assertEqual(deserialized.priority, impulse.priority)
        self.assertEqual(deserialized.get_text_content(), impulse.get_text_content())
        
    def test_neural_impulse_validation(self):
        """测试NeuralImpulse的验证功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content
        )
        
        # 有效的消息应该通过验证
        result = impulse.validate()
        self.assertTrue(result.is_valid)
        
        # 无效的消息应该验证失败
        impulse.session_id = ""  # 空session_id
        result = impulse.validate()
        self.assertFalse(result.is_valid)
        
    def test_neural_impulse_status(self):
        """测试NeuralImpulse的状态功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content
        )
        
        # 默认状态应该是CREATED
        self.assertEqual(impulse.status, MessageStatus.CREATED)
        
        # 更改状态
        impulse.set_status(MessageStatus.PROCESSING)
        self.assertEqual(impulse.status, MessageStatus.PROCESSING)
        
        impulse.set_status(MessageStatus.COMPLETED)
        self.assertEqual(impulse.status, MessageStatus.COMPLETED)
        
    def test_neural_impulse_routing(self):
        """测试NeuralImpulse的路由功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content
        )
        
        # 添加路由历史
        impulse.add_to_history("agent1")
        impulse.add_to_history("agent2")
        
        # 检查路由历史
        self.assertIn("agent1", impulse.routing_history)
        self.assertIn("agent2", impulse.routing_history)
        
        # 重新路由
        impulse.reroute_to("agent3")
        self.assertEqual(impulse.source_agent, "agent3")
        
    def test_neural_impulse_metadata(self):
        """测试NeuralImpulse的元数据功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content
        )
        
        # 添加元数据
        impulse.metadata["key1"] = "value1"
        impulse.metadata["key2"] = "value2"
        
        # 检查元数据
        self.assertEqual(impulse.metadata["key1"], "value1")
        self.assertEqual(impulse.metadata["key2"], "value2")
        
    def test_neural_impulse_error_handling(self):
        """测试NeuralImpulse的错误处理功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content
        )
        
        # 创建错误响应
        error_response = impulse.create_error_response(
            error_message="Test error",
            error_source="test"
        )
        
        self.assertEqual(error_response.session_id, self.session_id)
        self.assertEqual(error_response.action_intent, "error_response")
        self.assertEqual(error_response.status, MessageStatus.FAILED)
        
        # 检查错误内容
        error_content = error_response.get_protobuf_content()
        self.assertIsInstance(error_content, ErrorInfo)
        self.assertEqual(error_content.error_code, 500)
        self.assertEqual(error_content.error_message, "Test error")
        self.assertEqual(error_content.error_source, "test")
        
    def test_neural_impulse_response_creation(self):
        """测试NeuralImpulse的响应创建功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content
        )
        
        # 创建响应
        response = impulse.create_response(
            response_content="This is a response",
            source_agent="response_agent"
        )
        
        # 检查响应的session_id是否以"resp-"开头并包含原始session_id的前8个字符
        self.assertTrue(response.session_id.startswith("resp-"))
        self.assertIn(self.session_id[:8], response.session_id)
        self.assertEqual(response.action_intent, "response")
        self.assertEqual(response.source_agent, "response_agent")
        self.assertEqual(response.get_text_content(), "This is a response")
        
    def test_neural_impulse_copy(self):
        """测试NeuralImpulse的复制功能"""
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=self.test_content,
            priority=MessagePriority.HIGH
        )
        
        # 复制对象
        copied_impulse = impulse.copy()
        
        # 检查复制的对象
        self.assertEqual(copied_impulse.session_id, impulse.session_id)
        self.assertEqual(copied_impulse.action_intent, impulse.action_intent)
        self.assertEqual(copied_impulse.source_agent, impulse.source_agent)
        self.assertEqual(copied_impulse.input_source, impulse.input_source)
        self.assertEqual(copied_impulse.priority, impulse.priority)
        self.assertEqual(copied_impulse.get_text_content(), impulse.get_text_content())
        
        # 确保是不同的对象
        self.assertIsNot(copied_impulse, impulse)
        
    def test_neural_impulse_compression(self):
        """测试NeuralImpulse的压缩功能"""
        # 创建一个较大的内容
        large_content = "A" * 1000  # 1000个字符
        
        impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=large_content
        )
        
        # 检查压缩状态
        self.assertEqual(impulse.compression, CompressionType.NONE)  # 默认不压缩
        
        # 创建一个启用了压缩的神经脉冲
        compressed_impulse = NeuralImpulse(
            session_id=self.session_id,
            action_intent=self.action_intent,
            source_agent=self.source_agent,
            input_source=self.input_source,
            content=large_content,
            compression=CompressionType.GZIP
        )
        
        # 检查压缩状态
        self.assertEqual(compressed_impulse.compression, CompressionType.GZIP)
        
        # 检查内容哈希
        self.assertIsNotNone(compressed_impulse.content_hash)
        
        # 检查内容是否正确存储
        self.assertEqual(compressed_impulse.get_text_content(), large_content)


if __name__ == '__main__':
    unittest.main()
#!/usr/bin/env python3
"""
自定义 Hook 示例 - AethelumCoreLite Hook 机制演示

本示例展示如何创建和使用自定义 Hook，使用 Mock AI 服务。

演示功能：
1. Logging Hook - 日志记录
2. Validation Hook - 数据验证
3. Transform Hook - 数据转换
4. Metrics Hook - 指标收集
5. Cache Hook - 缓存机制
6. Error Handling Hook - 错误处理

注意：本示例使用模拟 AI 服务，开箱即用，不需要真实 API keys。
"""

import sys
import os
import time
import logging
import hashlib
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.examples.mock_ai_service import MockAIClient


def setup_logging():
    """设置日志"""
    logger = logging.getLogger("CustomHookExample")

    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    return logger


# ==================== 自定义 Hook 类 ====================

class LoggingHook:
    """日志 Hook - 详细记录消息处理过程"""

    def __init__(self):
        self.logger = logging.getLogger("LoggingHook")
        self.message_count = 0

    def before_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理前记录"""
        self.message_count += 1
        content = impulse.get_text_content()
        self.logger.info(f"[Hook #{self.message_count}] 处理前 | 队列: {source_queue} | 内容: '{content[:30]}...'")

        # 添加处理标记
        impulse.metadata['logged_at'] = time.time()

        return impulse

    def after_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理后记录"""
        content = impulse.get_text_content()
        process_time = time.time() - impulse.metadata.get('logged_at', time.time())

        self.logger.info(f"[Hook #{self.message_count}] 处理后 | 耗时: {process_time:.3f}s | 结果: '{content[:30]}...'")

        return impulse


class ValidationHook:
    """验证 Hook - 验证消息内容和格式"""

    def __init__(self):
        self.logger = logging.getLogger("ValidationHook")
        self.validation_stats = {
            'total_validated': 0,
            'passed': 0,
            'failed': 0
        }

    def before_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理前验证"""
        self.validation_stats['total_validated'] += 1

        content = impulse.get_text_content()

        # 验证规则
        is_valid = True
        errors = []

        # 检查内容长度
        if len(content) == 0:
            is_valid = False
            errors.append("内容为空")

        # 检查内容是否过长
        if len(content) > 1000:
            is_valid = False
            errors.append("内容过长")

        # 检查是否包含敏感词
        sensitive_words = ['密码', 'secret', '机密']
        if any(word in content for word in sensitive_words):
            is_valid = False
            errors.append("包含敏感词")

        # 记录验证结果
        impulse.metadata['validated'] = is_valid
        impulse.metadata['validation_errors'] = errors

        if is_valid:
            self.validation_stats['passed'] += 1
            self.logger.info(f"✓ 验证通过: '{content[:30]}...'")
        else:
            self.validation_stats['failed'] += 1
            self.logger.warning(f"✗ 验证失败: {', '.join(errors)}")

        return impulse

    def get_stats(self) -> Dict[str, Any]:
        """获取验证统计"""
        return self.validation_stats.copy()


class TransformHook:
    """转换 Hook - 自动转换和增强消息内容"""

    def __init__(self):
        self.logger = logging.getLogger("TransformHook")
        self.transform_count = 0

    def before_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理前转换"""
        self.transform_count += 1
        content = impulse.get_text_content()

        # 转换规则
        original_content = content

        # 去除首尾空格
        content = content.strip()

        # 统一标点符号
        content = content.replace('，', ',').replace('。', '.')

        # 添加时间戳（如果没有）
        if '[时间]' not in content:
            content = f"[时间:{time.strftime('%H:%M:%S')}] {content}"

        # 如果内容有变化，更新它
        if content != original_content:
            impulse.set_text_content(content)
            self.logger.info(f"🔄 转换: '{original_content[:20]}...' → '{content[:20]}...'")
            impulse.metadata['transformed'] = True
        else:
            impulse.metadata['transformed'] = False

        return impulse


class CacheHook:
    """缓存 Hook - 缓存重复请求"""

    def __init__(self, cache_size: int = 100):
        self.logger = logging.getLogger("CacheHook")
        self.cache = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0
        }
        self.cache_size = cache_size

    def before_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理前检查缓存"""
        content = impulse.get_text_content()

        # 生成内容哈希作为缓存键
        content_hash = hashlib.md5(content.encode()).hexdigest()

        if content_hash in self.cache:
            # 缓存命中
            self.cache_stats['hits'] += 1
            cached_response = self.cache[content_hash]

            impulse.set_text_content(cached_response)
            impulse.metadata['cached'] = True
            impulse.metadata['cache_hit'] = True

            self.logger.info(f"💾 缓存命中: '{content[:30]}...'")

            # 直接标记为完成，跳过后续处理
            impulse.action_intent = "Done"
        else:
            # 缓存未命中
            self.cache_stats['misses'] += 1
            impulse.metadata['cached'] = False
            impulse.metadata['cache_hit'] = False
            impulse.metadata['content_hash'] = content_hash

        return impulse

    def after_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理后更新缓存"""
        # 如果是缓存未命中的请求，缓存结果
        if not impulse.metadata.get('cache_hit', False):
            content_hash = impulse.metadata.get('content_hash')
            response_content = impulse.get_text_content()

            if content_hash and response_content:
                # 限制缓存大小
                if len(self.cache) >= self.cache_size:
                    # 移除最旧的缓存项（简单的 FIFO）
                    oldest_key = next(iter(self.cache))
                    del self.cache[oldest_key]

                self.cache[content_hash] = response_content
                self.logger.debug(f"缓存已更新: {content_hash}")

        return impulse

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = self.cache_stats['hits'] / total if total > 0 else 0

        return {
            'cache_size': len(self.cache),
            'hits': self.cache_stats['hits'],
            'misses': self.cache_stats['misses'],
            'hit_rate': hit_rate
        }


class MetricsHook:
    """指标 Hook - 收集详细的处理指标"""

    def __init__(self):
        self.logger = logging.getLogger("MetricsHook")
        self.metrics = {
            'message_lengths': [],
            'processing_times': [],
            'queue_stats': {}
        }

    def before_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理前记录"""
        impulse.metadata['hook_start_time'] = time.time()

        # 记录消息长度
        content_length = len(impulse.get_text_content())
        self.metrics['message_lengths'].append(content_length)

        # 记录队列统计
        if source_queue not in self.metrics['queue_stats']:
            self.metrics['queue_stats'][source_queue] = 0
        self.metrics['queue_stats'][source_queue] += 1

        return impulse

    def after_process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """处理后记录"""
        # 计算处理时间
        start_time = impulse.metadata.get('hook_start_time', time.time())
        processing_time = time.time() - start_time
        self.metrics['processing_times'].append(processing_time)

        self.logger.debug(f"指标: 长度={len(impulse.get_text_content())}, 耗时={processing_time:.3f}s")

        return impulse

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        total_messages = len(self.metrics['message_lengths'])

        if total_messages == 0:
            return {'total_messages': 0}

        return {
            'total_messages': total_messages,
            'avg_length': sum(self.metrics['message_lengths']) / total_messages,
            'min_length': min(self.metrics['message_lengths']),
            'max_length': max(self.metrics['message_lengths']),
            'avg_processing_time': sum(self.metrics['processing_times']) / len(self.metrics['processing_times']),
            'queue_stats': self.metrics['queue_stats'].copy()
        }


# ==================== 主函数 ====================

def main():
    """主函数"""
    logger = setup_logging()

    logger.info("=" * 70)
    logger.info("AethelumCoreLite 自定义 Hook 示例")
    logger.info("=" * 70)
    logger.info("Hook 类型:")
    logger.info("  • Logging Hook - 详细日志")
    logger.info("  • Validation Hook - 数据验证")
    logger.info("  • Transform Hook - 内容转换")
    logger.info("  • Cache Hook - 结果缓存")
    logger.info("  • Metrics Hook - 指标收集")
    logger.info("=" * 70)

    mock_ai = MockAIClient(response_delay=0.03)
    logger.info("✅ Mock AI 服务已初始化")

    router = None

    try:
        # 1. 创建路由器
        router = NeuralSomaRouter()
        logger.info("✅ 神经路由器创建完成")

        # 2. 创建自定义 Hook 实例
        logging_hook = LoggingHook()
        validation_hook = ValidationHook()
        transform_hook = TransformHook()
        cache_hook = CacheHook(cache_size=50)
        metrics_hook = MetricsHook()

        logger.info("✅ 自定义 Hook 已创建")

        # 3. 创建业务处理器
        def business_handler(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
            """业务处理"""
            content = impulse.get_text_content()

            # 使用 Mock AI 处理
            result = mock_ai.process_content(content)

            impulse.set_text_content(result['result'])
            impulse.update_source("BusinessAgent")
            impulse.reroute_to("Q_AUDIT_OUTPUT")

            return impulse

        # 4. 创建响应处理器
        response_events = {}
        collected_responses = {}

        def response_handler(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
            """响应处理"""
            content = impulse.get_text_content()
            collected_responses[impulse.session_id] = content

            if impulse.session_id in response_events:
                response_events[impulse.session_id].set()

            impulse.action_intent = "Done"
            return impulse

        # 5. 注册 Hook
        # 在审核输入队列注册多个 Hook
        router.register_hook("Q_AUDIT_INPUT", "pre_process", logging_hook.before_process)
        router.register_hook("Q_AUDIT_INPUT", "pre_process", validation_hook.before_process)
        router.register_hook("Q_AUDIT_INPUT", "pre_process", transform_hook.before_process)
        router.register_hook("Q_AUDIT_INPUT", "pre_process", cache_hook.before_process)

        router.register_hook("Q_AUDIT_INPUT", "post_process", cache_hook.after_process)
        router.register_hook("Q_AUDIT_INPUT", "post_process", metrics_hook.after_process)

        logger.info("✅ Hook 已注册到队列")

        # 6. 设置系统
        router.auto_setup(
            business_handler=business_handler,
            response_handler=response_handler
        )

        logger.info("✅ 神经系统设置完成")

        # 7. 等待系统稳定
        time.sleep(1)

        # 8. 发送测试消息
        test_messages = [
            "你好，请介绍一下自己",
            "验证测试：这条消息符合验证规则",
            "你好，请介绍一下自己",  # 重复消息，测试缓存
            "过短",  # 验证失败
            "这是一条包含密码的敏感消息",  # 验证失败
            "请帮我处理这条消息",
            "请帮我处理这条消息",  # 重复，测试缓存
            "正常消息内容",
        ]

        logger.info(f"\n📤 发送 {len(test_messages)} 条测试消息...\n")

        # 创建 Event 对象
        for i, message in enumerate(test_messages):
            session_id = f"hook-session-{i:03d}"
            response_events[session_id] = threading.Event()

        # 发送消息
        for i, message in enumerate(test_messages, 1):
            session_id = f"hook-session-{i:03d}"

            impulse = NeuralImpulse(
                session_id=session_id,
                action_intent="Q_AUDIT_INPUT",
                source_agent="Gateway",
                input_source="USER",
                content=message
            )

            logger.info(f"[{i}/{len(test_messages)}] 发送: '{message}'")
            router.inject_input(impulse)

        # 9. 等待处理完成
        logger.info("\n⏳ 等待处理完成...")
        time.sleep(5)

        # 10. 显示结果
        logger.info("\n" + "=" * 70)
        logger.info("📊 处理结果:")
        logger.info("=" * 70)

        for session_id, response in collected_responses.items():
            logger.info(f"  {session_id}: {response}")

        # 11. 显示 Hook 统计
        logger.info("\n" + "-" * 70)
        logger.info("📈 Hook 统计:")
        logger.info("-" * 70)

        # Validation Hook 统计
        validation_stats = validation_hook.get_stats()
        logger.info(f"\n验证 Hook:")
        logger.info(f"  - 总验证数: {validation_stats['total_validated']}")
        logger.info(f"  - 通过: {validation_stats['passed']}")
        logger.info(f"  - 失败: {validation_stats['failed']}")

        # Cache Hook 统计
        cache_stats = cache_hook.get_stats()
        logger.info(f"\n缓存 Hook:")
        logger.info(f"  - 缓存大小: {cache_stats['cache_size']}")
        logger.info(f"  - 命中: {cache_stats['hits']}")
        logger.info(f"  - 未命中: {cache_stats['misses']}")
        logger.info(f"  - 命中率: {cache_stats['hit_rate']:.1%}")

        # Metrics Hook 统计
        metrics_summary = metrics_hook.get_summary()
        logger.info(f"\n指标 Hook:")
        logger.info(f"  - 总消息数: {metrics_summary['total_messages']}")
        logger.info(f"  - 平均长度: {metrics_summary['avg_length']:.1f}字符")
        logger.info(f"  - 最短: {metrics_summary['min_length']}字符")
        logger.info(f"  - 最长: {metrics_summary['max_length']}字符")
        logger.info(f"  - 平均处理时间: {metrics_summary['avg_processing_time']:.3f}秒")
        logger.info(f"  - 队列统计: {metrics_summary['queue_stats']}")

        logger.info("\n" + "=" * 70)
        logger.info("✅ 自定义 Hook 示例完成！")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"运行出错: {e}")
        import traceback
        logger.debug(f"错误详情:\n{traceback.format_exc()}")
    finally:
        if router is not None:
            router.stop()
            logger.info("✅ 神经系统已停止")


if __name__ == "__main__":
    main()

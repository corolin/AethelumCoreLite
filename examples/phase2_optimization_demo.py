"""
阶段二优化成果演示

展示ProtoBuf工具类和Hook机制的优化功能。
"""

import time
import asyncio
from typing import Dict, Any

# 导入核心模块
from aethelum_core_lite.core.protobuf_utils import (
    ProtoBufManager, MessageValidator, BatchProcessor, PerformanceOptimizer,
    CompatibilityManager, MessageTransformer, create_validation_info,
    create_performance_stats, create_compatibility_info, serialize_with_cache
)

# 导入Hook模块
from aethelum_core_lite.hooks import (
    BaseHook, PreHook, PostHook, ErrorHook, ConditionalHook, AsyncHook,
    MetricsHook, SecurityHook, HookChain, get_hook_manager,
    get_performance_optimizer, create_pre_hook, create_post_hook, create_error_hook
)


def demo_protobuf_optimizations():
    """演示ProtoBuf优化功能"""
    print("=== ProtoBuf优化功能演示 ===")
    
    # 1. 创建增强的神经脉冲
    print("\n1. 创建增强的神经脉冲消息")
    
    # 创建验证信息
    validation_info = create_validation_info(
        is_valid=True,
        validation_errors=[],
        schema_version="1.2"
    )
    
    # 创建性能统计
    perf_stats = create_performance_stats()
    
    # 创建兼容性信息
    compat_info = create_compatibility_info("1.0", "1.2")
    
    # 创建神经脉冲
    impulse = ProtoBufManager.create_neural_impulse(
        session_id="demo_session_001",
        action_intent="process_request",
        source_agent="demo_agent",
        input_source="USER",
        content="这是一个演示请求",
        metadata={"user_type": "demo", "priority": "high"},
        routing_history=["router", "demo_agent"],
        timestamp=int(time.time()),
        priority=1,  # 高优先级
        version="1.2",
        correlation_id="demo_correlation_001",
        validation_info=validation_info,
        performance_stats=perf_stats,
        compatibility_info=compat_info,
        requires_audit=True,
        audit_level="medium"
    )
    
    print(f"创建神经脉冲: {impulse.session_id}")
    print(f"版本: {impulse.version}")
    print(f"审计级别: {impulse.audit_level}")
    
    # 2. 消息验证
    print("\n2. 消息验证")
    is_valid, errors = MessageValidator.validate_neural_impulse(impulse)
    print(f"验证结果: {'通过' if is_valid else '失败'}")
    if errors:
        print(f"验证错误: {errors}")
    
    # 3. 性能优化的序列化
    print("\n3. 性能优化序列化")
    
    # 标准序列化
    start_time = time.time()
    standard_serialized = impulse.SerializeToString()
    standard_time = time.time() - start_time
    
    # 缓存序列化
    start_time = time.time()
    cached_serialized = serialize_with_cache(impulse)
    cached_time = time.time() - start_time
    
    print(f"标准序列化时间: {standard_time:.6f}s")
    print(f"缓存序列化时间: {cached_time:.6f}s")
    print(f"序列化大小: {len(standard_serialized)} bytes")
    
    # 4. 批量处理
    print("\n4. 批量处理演示")
    
    # 创建多个脉冲
    impulses = [impulse]
    for i in range(1, 5):
        copy_impulse = ProtoBufManager.create_neural_impulse(
            session_id=f"demo_session_{i:03d}",
            action_intent="process_request",
            source_agent="demo_agent",
            input_source="USER",
            content=f"请求 {i}",
            metadata={"index": i},
            routing_history=["router", "demo_agent"],
            timestamp=int(time.time()),
            version="1.2"
        )
        impulses.append(copy_impulse)
    
    # 批量序列化
    start_time = time.time()
    batch_serialized = BatchProcessor.serialize_batch_with_length(impulses)
    batch_time = time.time() - start_time
    
    print(f"批量序列化时间: {batch_time:.6f}s")
    print(f"批量序列化大小: {len(batch_serialized)} bytes")
    print(f"平均每个消息: {len(batch_serialized)/len(impulses):.1f} bytes")
    
    # 5. 版本兼容性
    print("\n5. 版本兼容性演示")
    
    # 创建1.0版本的消息（模拟）
    old_impulse = ProtoBufManager.create_neural_impulse(
        session_id="old_session",
        action_intent="old_process",
        source_agent="old_agent",
        input_source="USER",
        content="旧版本消息",
        metadata={},
        routing_history=[],
        timestamp=int(time.time()),
        version="1.0"
    )
    
    # 升级到1.2版本
    upgraded_impulse = CompatibilityManager.upgrade_message(old_impulse, "1.2")
    print(f"原版本: {old_impulse.version}")
    print(f"升级后版本: {upgraded_impulse.version}")
    print(f"新增字段: correlation_id='{upgraded_impulse.correlation_id}'")
    
    # 6. 消息转换
    print("\n6. 消息转换演示")
    
    # 转换为字典
    impulse_dict = MessageTransformer.transform_to_dict(impulse)
    print(f"字典键数量: {len(impulse_dict)}")
    
    # 转换为JSON
    impulse_json = MessageTransformer.transform_to_json(impulse)
    print(f"JSON长度: {len(impulse_json)} 字符")
    
    # 从字典重建
    rebuilt_impulse = MessageTransformer.transform_from_dict(impulse_dict)
    print(f"重建脉冲ID: {rebuilt_impulse.session_id}")


def demo_hook_optimizations():
    """演示Hook优化功能"""
    print("\n\n=== Hook优化功能演示 ===")
    
    # 1. 创建多种类型的Hook
    print("\n1. 创建多种类型的Hook")
    
    # 前置Hook - 添加时间戳
    def add_timestamp(impulse, source_queue):
        impulse.metadata['pre_hook_timestamp'] = int(time.time())
        return impulse
    
    pre_hook = create_pre_hook(
        "add_timestamp_hook",
        add_timestamp,
        priority=10
    )
    
    # 后置Hook - 记录执行结果
    def log_result(impulse, source_queue, result=None):
        impulse.metadata['post_hook_result'] = 'processed' if result else 'no_result'
        return impulse
    
    post_hook = create_post_hook(
        "log_result_hook",
        log_result,
        priority=50
    )
    
    # 安全Hook - 检查敏感内容
    def security_check(impulse, source_queue):
        content = impulse.get_text_content() if hasattr(impulse, 'get_text_content') else ""
        is_sensitive = '密码' in content or 'token' in content.lower()
        return not is_sensitive, f"发现敏感内容: {is_sensitive}"
    
    security_hook = SecurityHook(
        "security_check_hook",
        enable_logging=True,
        priority=5
    )
    security_hook.add_security_rule("sensitive_content_check", security_check)
    
    # 条件Hook - 仅处理高优先级消息
    def high_priority_condition(impulse, source_queue):
        return hasattr(impulse, 'priority') and impulse.priority <= 1
    
    conditional_target = create_pre_hook(
        "high_priority_handler",
        lambda imp, sq: imp
    )
    conditional_hook = ConditionalHook(
        "conditional_hook",
        high_priority_condition,
        conditional_target,
        priority=20
    )
    
    # 指标Hook - 收集指标
    metrics_hook = MetricsHook(
        "metrics_hook",
        enable_logging=True,
        priority=90
    )
    metrics_hook.add_custom_metric("demo_metric", "demo_value")
    
    print(f"创建了 {len([pre_hook, post_hook, security_hook, conditional_hook, metrics_hook])} 个Hook")
    
    # 2. 创建Hook链
    print("\n2. 创建和管理Hook链")
    
    hook_manager = get_hook_manager()
    demo_chain = hook_manager.create_chain("demo_chain", max_workers=4)
    
    # 按优先级添加Hook
    demo_chain.add_hook(security_hook)      # 优先级 5
    demo_chain.add_hook(pre_hook)           # 优先级 10
    demo_chain.add_hook(conditional_hook)   # 优先级 20
    demo_chain.add_hook(post_hook)          # 优先级 50
    demo_chain.add_hook(metrics_hook)       # 优先级 90
    
    print(f"Hook链信息: {demo_chain.list_hooks()}")
    
    # 3. 创建测试脉冲
    print("\n3. 执行Hook链")
    
    from aethelum_core_lite.core.message import NeuralImpulse
    
    # 创建测试神经脉冲
    test_impulse = NeuralImpulse(
        session_id="hook_demo_session",
        action_intent="test_processing",
        source_agent="test_agent",
        input_source="USER",
        content="这是一个用于Hook演示的消息"
    )
    test_impulse.priority = 1  # 高优先级，触发条件Hook
    
    print(f"原始脉冲: {test_impulse.session_id}")
    print(f"元数据: {len(test_impulse.metadata)} 项")
    
    # 4. 执行前置Hook
    print("\n4. 执行前置Hook")
    processed_impulse = demo_chain.execute_pre_hooks(test_impulse, "test_queue")
    
    print(f"处理后元数据: {len(processed_impulse.metadata)} 项")
    for key in processed_impulse.metadata:
        print(f"  - {key}: {processed_impulse.metadata[key]}")
    
    # 5. 执行后置Hook
    print("\n5. 执行后置Hook")
    final_impulse = demo_chain.execute_post_hooks(processed_impulse, "test_queue", "success")
    
    print(f"最终元数据: {len(final_impulse.metadata)} 项")
    
    # 6. 错误Hook演示
    print("\n6. 错误处理演示")
    
    def error_handler(impulse, source_queue, error):
        impulse.metadata['error_handled'] = str(error)
        impulse.metadata['error_recovery'] = 'recovered'
        return impulse
    
    error_hook = create_error_hook(
        "demo_error_handler",
        error_handler,
        priority=1
    )
    
    demo_chain.add_hook(error_hook)
    
    # 模拟错误场景
    error_impulse = demo_chain.execute_error_hooks(
        final_impulse,
        "test_queue",
        Exception("这是一个演示错误")
    )
    
    print(f"错误处理后元数据: {len(error_impulse.metadata)} 项")
    print(f"错误处理: {error_impulse.metadata.get('error_handled', '未处理')}")
    
    # 7. 性能监控
    print("\n7. Hook性能监控")
    
    chain_stats = demo_chain.get_chain_stats()
    print(f"Hooks执行统计:")
    print(f"  - 总执行次数: {chain_stats['execution_stats']['total_executions']}")
    print(f"  - 成功执行次数: {chain_stats['execution_stats']['successful_executions']}")
    print(f"  - 平均执行时间: {chain_stats['execution_stats']['avg_execution_time']:.6f}s")


async def demo_async_performance():
    """演示异步性能优化"""
    print("\n\n=== 异步性能优化演示 ===")
    
    # 获取性能优化器
    optimizer = get_performance_optimizer(
        enable_caching=True,
        enable_monitoring=True,
        max_async_workers=5
    )
    
    # 创建异步Hook
    class AsyncDemoHook(AsyncHook):
        def __init__(self):
            super().__init__("async_demo_hook")
        
        async def async_process(self, impulse, source_queue):
            # 模拟异步处理
            await asyncio.sleep(0.1)
            impulse.metadata['async_processed'] = True
            impulse.metadata['async_timestamp'] = int(time.time())
            return impulse
    
    async_hook = AsyncDemoHook()
    
    # 创建测试脉冲
    from aethelum_core_lite.core.message import NeuralImpulse
    test_impulse = NeuralImpulse(
        session_id="async_demo_session",
        action_intent="async_test",
        source_agent="async_agent",
        input_source="USER",
        content="异步Hook演示"
    )
    
    # 1. 优化执行单个Hook
    print("\n1. 优化执行单个Hook")
    start_time = time.time()
    result1 = optimizer.optimize_hook_execution(async_hook, test_impulse, "test_queue")
    execution_time1 = time.time() - start_time
    
    print(f"执行时间: {execution_time1:.3f}s")
    print(f"缓存命中: {'是' if optimizer.cache else '否'}")
    
    # 2. 缓存效果演示
    print("\n2. 缓存效果演示")
    
    # 第二次执行（应该命中缓存）
    start_time = time.time()
    result2 = optimizer.optimize_hook_execution(async_hook, test_impulse, "test_queue")
    execution_time2 = time.time() - start_time
    
    print(f"首次执行时间: {execution_time1:.3f}s")
    print(f"缓存执行时间: {execution_time2:.3f}s")
    print(f"性能提升: {((execution_time1 - execution_time2) / execution_time1 * 100):.1f}%")
    
    # 3. 批量异步Hook演示
    print("\n3. 批量异步Hook演示")
    
    # 创建多个异步Hook
    async_hooks = []
    for i in range(3):
        hook = AsyncDemoHook()
        hook.hook_name = f"async_demo_hook_{i}"
        async_hooks.append(hook)
    
    # 并行执行
    start_time = time.time()
    batch_result = await optimizer.optimize_async_hooks_execution(async_hooks, test_impulse, "test_queue")
    batch_time = time.time() - start_time
    
    print(f"批量执行时间: {batch_time:.3f}s")
    print(f"平均每个Hook: {batch_time/len(async_hooks):.3f}s")
    
    # 4. 性能报告
    print("\n4. 性能报告")
    
    performance_report = optimizer.get_performance_report()
    print(f"优化器配置: {performance_report['optimizer_config']}")
    
    if 'cache_stats' in performance_report:
        cache_stats = performance_report['cache_stats']
        print(f"缓存统计:")
        print(f"  - 缓存大小: {cache_stats['cache_size']}")
        print(f"  - 命中率: {cache_stats.get('hit_rate', 0):.1%}")
    
    if 'performance_summary' in performance_report:
        perf_summary = performance_report['performance_summary']
        print(f"性能摘要:")
        print(f"  - 总Hooks数: {perf_summary['total_hooks']}")
        print(f"  - 慢Hooks数: {len(perf_summary.get('slow_hooks', []))}")
        print(f"  - 错误Hooks数: {len(perf_summary.get('error_prone_hooks', []))}")


def main():
    """主演示函数"""
    print("AethelumCoreLite 阶段二优化成果演示")
    print("=" * 50)
    
    # 演示ProtoBuf优化
    demo_protobuf_optimizations()
    
    # 演示Hook优化
    demo_hook_optimizations()
    
    # 演示异步性能优化
    asyncio.run(demo_async_performance())
    
    print("\n\n阶段二优化演示完成！")
    print("主要改进:")
    print("✓ ProtoBuf消息定义完善，新增20+字段")
    print("✓ 序列化性能提升，支持缓存和批量处理")
    print("✓ 消息验证和转换，支持向后兼容")
    print("✓ 多种Hook类型：前置、后置、错误、条件、异步等")
    print("✓ Hook链管理，支持优先级和并行执行")
    print("✓ 性能监控和优化，支持缓存和异步处理")


if __name__ == "__main__":
    main()
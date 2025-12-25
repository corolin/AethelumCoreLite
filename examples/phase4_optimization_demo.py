"""
阶段四优化成果演示

展示日志系统和验证系统的优化功能。
"""

import time
import asyncio
from typing import List, Dict, Any

# 导入优化后的模块
from aethelum_core_lite.utils import (
    # 结构化日志系统
    get_structured_logger, LogLevel, LogFormat, set_global_logging_config,
    
    # 日志级别管理
    create_dynamic_logger, set_debug_log_mode, set_error_log_mode,
    
    # 日志性能优化
    start_log_performance_monitoring, get_log_performance_summary,
    
    # 日志聚合分析
    get_log_aggregator, query_logs, get_log_statistics, aggregate_logs,
    AggregationType, TimeWindow,
    
    # 统一验证框架
    ValidationResult, ValidationContext, RequiredValidator, TypeValidator,
    LengthValidator, EmailValidator, ChoicesValidator,
    
    # 验证规则
    CommonValidationRules, PasswordStrengthValidator, ChineseIDValidator,
    
    # 验证性能优化
    get_validation_optimizer, validate_with_optimization,
    
    # 错误处理和报告
    get_error_reporter, report_error, report_custom_error,
    ErrorSeverity, ErrorCategory, ErrorContext
)


def demo_structured_logging():
    """演示结构化日志系统"""
    print("=== 结构化日志系统演示 ===")
    
    # 配置全局日志系统
    set_global_logging_config(
        level='info',
        format='json',
        console=True,
        file={
            'path': 'logs/demo_structured.log',
            'rotation': 'daily',
            'max_files': 7
        },
        async_output=True,
        default_context={
            'service': 'aethelum-core-lite',
            'version': '1.0.0'
        }
    )
    
    # 创建结构化日志记录器
    logger = get_structured_logger('demo_structured')
    
    # 基础日志记录
    logger.info("这是结构化日志演示", 
               module='demo', function='demo_structured_logging')
    
    logger.warning("这是一个警告消息", 
                 tags=['warning', 'demo'],
                 user_id='demo_user')
    
    logger.error("这是一个错误消息", 
                session_id='session_123',
                correlation_id='corr_456')
    
    # 性能日志
    start_time = time.time()
    time.sleep(0.1)
    duration = time.time() - start_time
    
    logger.log_performance("结构化日志演示", duration,
                         operations=10, success_rate=95.5)
    
    # Hook日志
    logger.log_hook("demo_hook", "执行", 
                   execution_time=0.05,
                   result="success")
    
    # 神经脉冲日志
    class MockImpulse:
        def __init__(self):
            self.session_id = "impulse_001"
            self.action_intent = "demo_action"
            self.source_agent = "demo_agent"
            self.correlation_id = "corr_123"
    
    impulse = MockImpulse()
    logger.log_impulse(impulse, "创建", 
                     content_length=256,
                     validation_result="passed")
    
    print("✓ 结构化日志演示完成")


def demo_dynamic_log_levels():
    """演示动态日志级别管理"""
    print("\n=== 动态日志级别管理演示 ===")
    
    # 创建动态日志记录器
    logger = create_dynamic_logger(
        'demo_dynamic',
        level=LogLevel.INFO,
        format='json'
    )
    
    print("正常级别日志:")
    logger.debug("这条调试消息不会显示")
    logger.info("这条信息消息会显示")
    
    # 设置临时调试模式
    print("\n启用临时调试模式（30秒）:")
    set_debug_log_mode(enabled=True, duration=30)
    
    # 等待级别管理器更新
    time.sleep(0.1)
    
    logger.debug("现在调试消息会显示了")
    logger.info("信息消息仍然显示")
    
    # 设置错误模式
    print("\n设置错误模式（30秒）:")
    set_error_log_mode(enabled=True, duration=30)
    
    time.sleep(0.1)
    
    logger.debug("调试消息现在不会显示")
    logger.info("信息消息现在不会显示")
    logger.error("但错误消息会显示")
    
    print("✓ 动态日志级别管理演示完成")


def demo_log_performance():
    """演示日志性能优化"""
    print("\n=== 日志性能优化演示 ===")
    
    # 启动性能监控
    start_log_performance_monitoring()
    
    logger = get_structured_logger('demo_performance')
    
    print("生成大量日志以测试性能...")
    start_time = time.time()
    
    # 生成1000条日志
    for i in range(1000):
        logger.info(f"性能测试日志 {i}",
                  batch_id=i // 100,
                  item_index=i,
                  processing_time=0.001 * (i % 10))
    
    generation_time = time.time() - start_time
    
    # 等待性能监控收集数据
    time.sleep(2)
    
    # 获取性能摘要
    perf_summary = get_log_performance_summary()
    
    print(f"✓ 生成了1000条日志，耗时: {generation_time:.3f}s")
    print(f"✓ 平均每条日志: {generation_time/1000:.6f}s")
    
    if 'current_metrics' in perf_summary:
        metrics = perf_summary['current_metrics']
        print(f"✓ 总条目数: {metrics.get('total_entries', 0)}")
        print(f"✓ 平均处理时间: {metrics.get('avg_processing_time', 0):.6f}s")
        print(f"✓ 队列深度: {metrics.get('avg_queue_depth', 0)}")
    
    print("✓ 日志性能优化演示完成")


def demo_log_analytics():
    """演示日志聚合分析"""
    print("\n=== 日志聚合分析演示 ===")
    
    # 获取日志聚合器
    aggregator = get_log_aggregator()
    
    # 添加日志模式
    from aethelum_core_lite.utils import LogPattern
    aggregator.add_pattern(LogPattern(
        name="demo_pattern",
        pattern=r"demo|演示|test",
        description="演示模式",
        tags=['demo']
    ))
    
    # 添加告警规则
    from aethelum_core_lite.utils import AlertRule
    aggregator.add_alert_rule(AlertRule(
        name="demo_alert",
        condition="level=ERROR",
        threshold=5,
        time_window=TimeWindow.MINUTE_5,
        aggregation=AggregationType.COUNT
    ))
    
    logger = get_structured_logger('demo_analytics')
    
    # 生成一些测试日志
    print("生成测试日志用于分析...")
    
    for i in range(10):
        if i % 3 == 0:
            logger.error(f"这是一个演示错误 {i}", tags=['demo', 'error'])
        elif i % 2 == 0:
            logger.warning(f"这是一个演示警告 {i}", tags=['demo', 'warning'])
        else:
            logger.info(f"这是一个演示信息 {i}", tags=['demo', 'info'])
    
    # 等待聚合器处理
    time.sleep(1)
    
    # 查询日志
    print("\n查询日志:")
    error_logs = query_logs({
        'level': 'ERROR',
        'limit': 10
    })
    print(f"✓ 查询到 {len(error_logs)} 条错误日志")
    
    # 获取统计信息
    stats = get_log_statistics(TimeWindow.MINUTE_5)
    print(f"✓ 总体统计: {stats['overall']['total_logs']} 条日志")
    print(f"✓ 按级别统计: {stats['by_level']}")
    print(f"✓ 按记录器统计: {len(stats['by_logger'])} 个记录器")
    
    # 聚合分析
    print("\n聚合分析:")
    agg_results = aggregate_logs(
        dimensions=['level'],
        time_window=TimeWindow.MINUTE_5
    )
    print(f"✓ 聚合结果: {len(agg_results)} 条记录")
    
    for result in agg_results:
        print(f"  - {result['level']}: {result['count']} 条")
    
    print("✓ 日志聚合分析演示完成")


def demo_validation_framework():
    """演示统一验证框架"""
    print("\n=== 统一验证框架演示 ===")
    
    # 创建验证上下文
    context = ValidationContext(
        field_path='user_data',
        session_id='session_123',
        user_context={'role': 'admin'}
    )
    
    # 基础验证器
    validators = [
        RequiredValidator('username_required'),
        LengthValidator(3, 20, 'username_length'),
        TypeValidator(str, 'username_type'),
    ]
    
    # 测试数据
    test_cases = [
        ("", "空用户名"),
        ("ab", "太短"),
        ("a" * 25, "太长"),
        (123, "类型错误"),
        ("validuser", "有效用户名")
    ]
    
    for test_value, description in test_cases:
        print(f"\n测试: {description} ('{test_value}')")
        
        results = []
        for validator in validators:
            result = validator._execute_validation(test_value, context)
            result.field_name = "username"
            results.append(result)
        
        # 检查结果
        failures = [r for r in results if r.is_failure()]
        if failures:
            print("✗ 验证失败:")
            for failure in failures:
                print(f"  - {failure.message}")
        else:
            print("✓ 验证通过")
    
    print("✓ 基础验证框架演示完成")


def demo_business_validation_rules():
    """演示业务验证规则"""
    print("\n=== 业务验证规则演示 ===")
    
    # 测试数据
    test_data = {
        'email': 'invalid-email',
        'password': '123',
        'id_card': '123456789012345678',
        'age': -5,
        'url': 'not-a-url'
    }
    
    # 使用常用验证规则
    print("邮箱验证:")
    email_validators = CommonValidationRules.email('user_email')
    email_result = email_validators[1]._execute_validation(test_data['email'], 
                                                     ValidationContext('user_email'))
    print(f"✓ 邮箱验证: {'通过' if email_result.is_success() else '失败 - ' + email_result.message}")
    
    print("\n密码强度验证:")
    password_validators = CommonValidationRules.password('user_password', 'medium')
    for validator in password_validators:
        result = validator._execute_validation(test_data['password'], ValidationContext('user_password'))
        if result.is_failure():
            print(f"✗ {validator.name}: {result.message}")
    
    print("\n身份证验证:")
    id_validator = ChineseIDValidator('user_id_card')
    id_result = id_validator._execute_validation(test_data['id_card'], ValidationContext('user_id_card'))
    print(f"✓ 身份证验证: {'通过' if id_result.is_success() else '失败 - ' + id_result.message}")
    
    print("\n年龄验证:")
    age_validators = CommonValidationRules.age('user_age', 0, 120)
    age_result = age_validators[2]._execute_validation(test_data['age'], ValidationContext('user_age'))
    print(f"✓ 年龄验证: {'通过' if age_result.is_success() else '失败 - ' + age_result.message}")
    
    print("\nURL验证:")
    url_validators = CommonValidationRules.url('site_url', require_https=True)
    url_result = url_validators[1]._execute_validation(test_data['url'], ValidationContext('site_url'))
    print(f"✓ URL验证: {'通过' if url_result.is_success() else '失败 - ' + url_result.message}")
    
    print("✓ 业务验证规则演示完成")


def demo_validation_performance():
    """演示验证性能优化"""
    print("\n=== 验证性能优化演示 ===")
    
    # 获取验证优化器
    optimizer = get_validation_optimizer(
        enable_cache=True,
        cache_size=1000,
        max_workers=4
    )
    
    # 创建验证器列表
    validators = [
        RequiredValidator('required'),
        TypeValidator(str, 'type'),
        LengthValidator(1, 100, 'length'),
        EmailValidator('email')
    ]
    
    # 测试数据
    test_email = "test@example.com"
    context = ValidationContext('email', session_id='perf_test')
    
    print("执行优化验证...")
    
    # 第一次验证（缓存未命中）
    start_time = time.time()
    results1 = validate_with_optimization(validators, test_email, context)
    first_time = time.time() - start_time
    
    # 第二次验证（缓存命中）
    start_time = time.time()
    results2 = validate_with_optimization(validators, test_email, context)
    second_time = time.time() - start_time
    
    print(f"✓ 第一次验证（缓存未命中）: {first_time:.6f}s")
    print(f"✓ 第二次验证（缓存命中）: {second_time:.6f}s")
    print(f"✓ 性能提升: {((first_time - second_time) / first_time * 100):.1f}%")
    
    # 获取性能统计
    perf_stats = optimizer.get_performance_stats()
    if 'global_stats' in perf_stats:
        global_stats = perf_stats['global_stats']
        print(f"✓ 总验证次数: {global_stats.get('total_validations', 0)}")
        print(f"✓ 缓存命中率: {global_stats.get('cache_hit_rate', 0):.1f}%")
        print(f"✓ 平均验证时间: {global_stats.get('avg_time', 0):.6f}s")
    
    print("✓ 验证性能优化演示完成")


async def demo_async_validation():
    """演示异步验证"""
    print("\n=== 异步验证演示 ===")
    
    # 获取验证优化器
    optimizer = get_validation_optimizer()
    
    # 创建异步验证器
    from aethelum_core_lite.utils import AsyncValidator
    
    async def validate_email_async(data, context):
        await asyncio.sleep(0.1)  # 模拟异步操作
        return '@' in data and '.' in data
    
    async_validator = AsyncValidator(validate_email_async, 'async_email')
    
    validators = [
        RequiredValidator('required'),
        TypeValidator(str, 'type'),
        async_validator
    ]
    
    test_email = "async@test.com"
    context = ValidationContext('async_email')
    
    print("执行异步验证...")
    start_time = time.time()
    
    results = await optimizer.validate_async_with_optimization(
        validators, test_email, context
    )
    
    execution_time = time.time() - start_time
    
    print(f"✓ 异步验证完成，耗时: {execution_time:.3f}s")
    
    for result in results:
        status = "✓" if result.is_success() else "✗"
        print(f"  {status} {result.validator_name}: {result.message}")
    
    print("✓ 异步验证演示完成")


def demo_error_reporting():
    """演示错误处理和报告"""
    print("\n=== 错误处理和报告演示 ===")
    
    # 获取错误报告器
    error_reporter = get_error_reporter()
    
    # 报告系统异常
    try:
        raise ValueError("这是一个演示异常")
    except Exception as e:
        error_report = report_error(
            e,
            title="演示系统异常",
            context=ErrorContext(
                operation="demo_error_reporting",
                user_id="demo_user",
                session_id="session_123"
            ),
            tags=['demo', 'system']
        )
        print(f"✓ 报告系统异常: {error_report.error_id}")
    
    # 报告自定义错误
    custom_error = report_custom_error(
        title="业务规则违反",
        message="用户操作违反了业务规则",
        severity=ErrorSeverity.HIGH,
        category=ErrorCategory.BUSINESS,
        context=ErrorContext(
            operation="demo_business_validation",
            user_id="demo_user",
            custom_data={'rule_id': 'BR001', 'action': 'forbidden'}
        ),
        tags=['demo', 'business']
    )
    print(f"✓ 报告自定义错误: {custom_error.error_id}")
    
    # 获取错误统计
    stats = error_reporter.get_error_statistics(days=1)
    print(f"✓ 今日错误总数: {stats.get('total_errors', 0)}")
    print(f"✓ 错误解决率: {stats.get('resolution_rate', 0):.1f}%")
    
    if 'severity_distribution' in stats:
        severity_dist = stats['severity_distribution']
        print(f"✓ 严重程度分布: {severity_dist}")
    
    # 查询最近的错误
    recent_errors = error_reporter.get_errors(limit=5)
    print(f"✓ 最近5个错误:")
    for error in recent_errors:
        print(f"  - [{error.severity.value}] {error.title}")
    
    print("✓ 错误处理和报告演示完成")


async def main():
    """主演示函数"""
    print("AethelumCoreLite 阶段四优化成果演示")
    print("=" * 50)
    
    # 演示各种优化功能
    demo_structured_logging()
    demo_dynamic_log_levels()
    demo_log_performance()
    demo_log_analytics()
    demo_validation_framework()
    demo_business_validation_rules()
    demo_validation_performance()
    await demo_async_validation()
    demo_error_reporting()
    
    print("\n\n阶段四优化演示完成！")
    print("主要改进:")
    print("✓ 结构化日志系统支持多种格式和异步批量处理")
    print("✓ 动态日志级别管理和智能条件控制")
    print("✓ 高性能日志聚合和实时分析")
    print("✓ 统一验证框架支持多种验证器和业务规则")
    print("✓ 验证性能优化，支持缓存和并行处理")
    print("✓ 智能错误处理和报告系统")
    print("✓ 完整的性能监控和统计分析")


if __name__ == "__main__":
    asyncio.run(main())
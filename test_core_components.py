#!/usr/bin/env python3
"""
核心组件测试脚本
测试路由器、队列、工作器的基本功能
"""

import time
import threading
from aethelum_core_lite.core.router import NeuralSomaRouter
from aethelum_core_lite.core.queue import SynapticQueue
from aethelum_core_lite.core.worker import AxonWorker
from aethelum_core_lite.core.message import NeuralImpulse
from aethelum_core_lite.core.hooks import create_default_error_handler, create_default_response_handler


def test_queue():
    """测试队列基本功能"""
    print("=" * 50)
    print("测试队列基本功能")
    print("=" * 50)
    
    try:
        # 创建队列
        queue = SynapticQueue(queue_id="test_queue", max_size=10)
        print(f"✓ 队列创建成功: {queue}")
        
        # 测试队列统计
        stats = queue.get_stats()
        print(f"✓ 队列统计信息: {stats}")
        
        # 创建测试消息
        impulse = NeuralImpulse(
            content="测试消息",
            source_agent="test_agent",
            action_intent="Q_TEST"
        )
        print(f"✓ 神经脉冲创建成功: {impulse}")
        
        # 测试放入消息
        success = queue.put(impulse)
        print(f"✓ 消息放入队列: {success}")
        
        # 测试获取消息
        retrieved_impulse = queue.get(block=False)
        print(f"✓ 从队列获取消息: {retrieved_impulse is not None}")
        
        # 测试队列大小
        print(f"✓ 队列当前大小: {queue.size()}")
        
        return True
    except Exception as e:
        print(f"✗ 队列测试失败: {e}")
        return False


def test_worker():
    """测试工作器基本功能"""
    print("\n" + "=" * 50)
    print("测试工作器基本功能")
    print("=" * 50)
    
    try:
        # 创建队列
        queue = SynapticQueue(queue_id="worker_test_queue")
        
        # 创建测试钩子函数
        def test_hook(impulse, source_queue):
            print(f"  工作器处理消息: {impulse.session_id[:8]}...")
            impulse.action_intent = "Done"  # 设置为完成状态
            return impulse
        
        # 创建工作器
        worker = AxonWorker(
            name="test_worker",
            input_queue=queue,
            hooks=[test_hook]
        )
        print(f"✓ 工作器创建成功: {worker}")
        
        # 启动工作器
        worker.start()
        print(f"✓ 工作器启动成功")
        
        # 创建测试消息
        impulse = NeuralImpulse(
            content="工作器测试消息",
            source_agent="test_agent"
        )
        
        # 放入消息到队列
        queue.put(impulse)
        print("✓ 消息已放入队列")
        
        # 等待处理完成
        time.sleep(1)
        
        # 停止工作器
        worker.stop()
        worker.join(timeout=2)
        print("✓ 工作器停止成功")
        
        # 检查工作器统计
        stats = worker.get_stats()
        print(f"✓ 工作器统计: {stats}")
        
        return True
    except Exception as e:
        print(f"✗ 工作器测试失败: {e}")
        return False


def test_router():
    """测试路由器基本功能"""
    print("\n" + "=" * 50)
    print("测试路由器基本功能")
    print("=" * 50)
    
    try:
        # 创建路由器
        router = NeuralSomaRouter(enable_logging=False)  # 关闭日志以减少输出
        print(f"✓ 路由器创建成功: {router}")
        
        # 测试自动设置
        def test_business_handler(impulse, source_queue):
            print(f"  业务处理器处理: {impulse.session_id[:8]}...")
            impulse.action_intent = "Done"
            return impulse
        
        router.auto_setup(business_handler=test_business_handler)
        print("✓ 路由器自动设置完成")
        
        # 检查强制性队列
        queues = router.list_queues()
        print(f"✓ 创建的队列: {queues}")
        
        # 检查钩子
        hooks = router.list_hooks()
        print(f"✓ 注册的钩子: {hooks}")
        
        # 创建测试消息
        impulse = NeuralImpulse(
            content="路由器测试消息",
            source_agent="test_user"
        )
        
        # 注入消息
        success = router.inject_input(impulse)
        print(f"✓ 消息注入成功: {success}")
        
        # 等待处理完成
        time.sleep(2)
        
        # 检查路由器统计
        stats = router.get_stats()
        print(f"✓ 路由器统计: {stats}")
        
        # 停止路由器
        router.stop()
        print("✓ 路由器停止成功")
        
        return True
    except Exception as e:
        print(f"✗ 路由器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """测试组件集成功能"""
    print("\n" + "=" * 50)
    print("测试组件集成功能")
    print("=" * 50)
    
    try:
        # 创建路由器
        router = NeuralSomaRouter(enable_logging=False)
        
        # 创建自定义业务处理器
        def business_handler(impulse, source_queue):
            print(f"  业务处理: {impulse.get_text_content()}")
            # 创建响应
            response_impulse = impulse.copy()
            response_impulse.content = f"响应: {impulse.get_text_content()}"
            response_impulse.action_intent = "Q_RESPONSE_SINK"
            return response_impulse
        
        # 创建响应处理器
        def response_handler(impulse, source_queue):
            print(f"  响应处理: {impulse.get_text_content()}")
            impulse.action_intent = "Done"
            return impulse
        
        # 设置处理器
        router.auto_setup(
            business_handler=business_handler,
            response_handler=response_handler
        )
        
        # 创建多个测试消息
        test_messages = [
            "你好，世界！",
            "这是一个测试消息",
            "集成测试消息3"
        ]
        
        # 注入消息
        for i, msg in enumerate(test_messages):
            impulse = NeuralImpulse(
                content=f"{msg} (#{i+1})",
                source_agent=f"test_user_{i+1}"
            )
            success = router.inject_input(impulse)
            print(f"✓ 消息 #{i+1} 注入: {success}")
        
        # 等待所有消息处理完成
        print("等待消息处理完成...")
        time.sleep(5)
        
        # 检查最终统计
        stats = router.get_stats()
        print(f"✓ 最终统计: 处理了 {stats['total_impulses_processed']} 个消息")
        
        # 停止路由器
        router.stop()
        print("✓ 集成测试完成")
        
        return True
    except Exception as e:
        print(f"✗ 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("开始核心组件测试")
    print("测试时间:", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    results = []
    
    # 运行各项测试
    results.append(("队列测试", test_queue()))
    results.append(("工作器测试", test_worker()))
    results.append(("路由器测试", test_router()))
    results.append(("集成测试", test_integration()))
    
    # 输出测试结果
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎉 所有核心组件测试通过！")
        return True
    else:
        print("❌ 部分测试失败，需要检查")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
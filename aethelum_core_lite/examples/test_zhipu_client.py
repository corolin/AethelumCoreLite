#!/usr/bin/env python3
"""
智谱客户端测试脚本

测试智谱AI客户端的基本功能，不需要真实的API密钥
"""

import sys
import os
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def test_zhipu_client_import():
    """测试智谱客户端导入"""
    try:
        from aethelum_core_lite.examples.zhipu_client import ZhipuSDKClient, ZhipuConfig
        print("✅ 智谱客户端导入成功")
        return True
    except ImportError as e:
        print(f"❌ 智谱客户端导入失败: {e}")
        return False

def test_zhipu_config():
    """测试智谱配置"""
    try:
        from aethelum_core_lite.examples.zhipu_client import ZhipuConfig
        
        # 创建测试配置
        config = ZhipuConfig(
            api_key="test_key",
            model="glm-4",
            base_url="https://open.bigmodel.cn/api/paas/v4/"
        )
        
        print(f"✅ 智谱配置创建成功: model={config.model}")
        return True
    except Exception as e:
        print(f"❌ 智谱配置创建失败: {e}")
        return False

def test_zhipu_client_creation():
    """测试智谱客户端创建"""
    try:
        from aethelum_core_lite.examples.zhipu_client import ZhipuSDKClient, ZhipuConfig
        
        # 创建测试配置
        config = ZhipuConfig(
            api_key="test_key",
            model="glm-4",
            base_url="https://open.bigmodel.cn/api/paas/v4/"
        )
        
        # 创建客户端（不会立即连接）
        client = ZhipuSDKClient(config)
        print(f"✅ 智谱客户端创建成功: {client}")
        return True
    except Exception as e:
        print(f"❌ 智谱客户端创建失败: {e}")
        return False

def test_config_import():
    """测试配置文件导入"""
    try:
        from aethelum_core_lite.examples.config import ZHIPU_CONFIG
        if ZHIPU_CONFIG:
            print(f"✅ 配置文件导入成功: model={ZHIPU_CONFIG.model}")
        else:
            print("⚠️ 配置文件导入成功，但ZHIPU_CONFIG为None")
        return True
    except Exception as e:
        print(f"❌ 配置文件导入失败: {e}")
        return False

def main():
    """主函数"""
    print("🧪 开始智谱客户端测试")
    print("=" * 50)
    
    tests = [
        ("智谱客户端导入", test_zhipu_client_import),
        ("智谱配置", test_zhipu_config),
        ("智谱客户端创建", test_zhipu_client_creation),
        ("配置文件导入", test_config_import)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🔍 测试: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！智谱客户端基本功能正常。")
    else:
        print("⚠️ 部分测试失败，请检查相关依赖和配置。")

if __name__ == "__main__":
    main()
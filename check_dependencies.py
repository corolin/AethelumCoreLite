#!/usr/bin/env python3
"""
Aethelum Core Lite 依赖检查脚本
独立运行，检查ProtoBuf和OpenAI依赖
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

def check_protobuf():
    """检查ProtoBuf依赖"""
    print("📦 检查ProtoBuf状态...")
    protobuf_available = False
    try:
        # 首先检查protobuf库是否存在
        import google.protobuf
        print("✅ protobuf库已安装")

        # 然后检查编译后的schema文件是否存在
        schema_file = os.path.join(os.path.dirname(__file__), 'aethelum_core_lite/core', 'protobuf_schema_pb2.py')
        if os.path.exists(schema_file):
            print("✅ ProtoBuf schema文件已编译")
            protobuf_available = True
        else:
            print("❌ ProtoBuf schema文件未找到")
    except ImportError as e:
        print(f"❌ protobuf库未安装: {e}")
    except Exception as e:
        print(f"❌ ProtoBuf检查失败: {e}")

    return protobuf_available

def check_openai():
    """检查OpenAI依赖"""
    print("🔍 检查OpenAI状态...")
    openai_available = False
    try:
        import openai
        print("✅ OpenAI库已安装")
        openai_available = True
    except ImportError as e:
        print(f"❌ OpenAI库未安装: {e}")
    except Exception as e:
        print(f"❌ OpenAI检查失败: {e}")

    return openai_available

def check_config():
    """检查OpenAI配置"""
    print("⚙️ 检查OpenAI配置...")
    config_available = False
    try:
        # 尝试从配置文件加载
        config_file = os.path.join(os.path.dirname(__file__), 'aethelum_core_lite/examples/config.py')
        if os.path.exists(config_file):
            print("✅ 配置文件存在")
            # 读取配置文件检查API密钥
            with open(config_file, 'r') as f:
                content = f.read()
                if 'sk-your-api-key-here' in content or 'api_key=""' in content:
                    print("❌ API密钥未配置")
                else:
                    print("✅ API密钥已配置")
                    config_available = True
        else:
            print("❌ 配置文件不存在")
            print("   提示: 请复制 config_template.py 为 config.py")
    except Exception as e:
        print(f"❌ 配置检查失败: {e}")

    return config_available

def main():
    """主检查函数"""
    print("=" * 80)
    print("🚀 Aethelum Core Lite - 依赖检查")
    print("📦 灵壤精核 - 模拟神经网络的通信框架")
    print("=" * 80)
    print()

    # 检查ProtoBuf
    protobuf_ok = check_protobuf()
    print()

    # 检查OpenAI
    openai_ok = check_openai()
    print()

    # 检查配置
    config_ok = check_config()
    print()

    # 总结
    print("=" * 50)
    print("📋 检查结果总结:")
    print()

    if protobuf_ok:
        print("✅ ProtoBuf: 可用")
    else:
        print("❌ ProtoBuf: 不可用 (强制性依赖)")

    if openai_ok:
        print("✅ OpenAI库: 可用")
    else:
        print("❌ OpenAI库: 不可用 (强制性依赖)")

    if config_ok:
        print("✅ OpenAI配置: 可用")
    else:
        print("❌ OpenAI配置: 不可用")

    print()
    if protobuf_ok and openai_ok and config_ok:
        print("🎉 所有依赖检查通过！可以运行示例程序。")
        return True
    else:
        print("❌ 依赖检查失败，请解决上述问题后重新运行。")

        if not protobuf_ok:
            print("\n📝 ProtoBuf安装方法:")
            print("1. 安装protoc编译器:")
            print("   Ubuntu/Debian: sudo apt-get install protobuf-compiler")
            print("   macOS: brew install protobuf")
            print("   Windows: 下载并安装 protoc")
            print("2. 编译schema文件:")
            print("   cd aethelum_core_lite/core")
            print("   protoc --python_out=. protobuf_schema.proto")

        if not openai_ok:
            print("\n📝 OpenAI库安装方法:")
            print("   pip install openai")

        if not config_ok:
            print("\n📝 OpenAI配置方法:")
            print("1. 复制 config_template.py 为 config.py")
            print("2. 在 config.py 中填写您的API密钥")
            print("3. 获取API密钥: https://platform.openai.com/api-keys")

        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
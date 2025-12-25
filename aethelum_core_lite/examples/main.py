"""
Aethelum Core Lite 示例程序主入口

提供统一的示例程序运行界面，包括AI客户端配置和多个示例选择。

使用方法:
    python -m aethelum_core_lite.examples.main

功能特性:
- AI客户端配置（支持智谱AI和OpenAI）
- 多示例菜单选择
- 配置验证和错误处理
- 优雅的退出机制
"""

import sys
import os
import logging
from typing import Optional

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 延迟导入，避免在依赖检查阶段触发模块导入
def import_dependencies():
    """延迟导入依赖项"""
    # from aethelum_core_lite.core.openai_client import OpenAICompatClient, OpenAIConfig  # 已移除OpenAI依赖
    from aethelum_core_lite.examples.zhipu_client import ZhipuSDKClient, ZhipuConfig
    from aethelum_core_lite.examples.agents.audit_agent import AuditAgent
    return OpenAICompatClient, OpenAIConfig, ZhipuSDKClient, ZhipuConfig, AuditAgent


def setup_logging():
    """设置日志"""
    # 默认使用INFO级别日志，减少输出信息
    # 如需查看更详细的调试信息，请将level修改为logging.DEBUG
    logging.basicConfig(
        level=logging.INFO,  # 使用INFO级别日志
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def print_banner():
    """打印程序横幅"""
    print("=" * 80)
    print("🚀 Aethelum Core Lite - 示例程序主入口")
    print("📦 灵壤精核 - 模拟树神经系统的通信框架")
    print("⚡ 支持并发处理 | 🛡️ 内置安全审查 | 🎯 统一架构")
    print("=" * 80)
    print()


def print_menu():
    """打印主菜单"""
    print("📋 请选择要运行的示例程序:")
    print()
    print("🔹 示例程序:")
    print("1. ⚡ 单消息基础示例")
    print("   - 端到端消息处理流程、内容安全审查")
    print("   - 等待响应完成的同步模式")
    print("2. 🚀 并发处理示例")
    print("   - 多线程并发消息处理、自动响应收集")
    print("3. ✨ 高级功能示例")
    print("   - RAG知识增强、性能监控、智能响应分类")
    print("4. 🛡️  内容安全审查示例")
    print("   - 并发安全审查、智能违规识别、自动拒绝回复")
    print()
    print("🔹 系统管理:")
    print("5. ⚙️  重新配置AI客户端")
    print("6. 📊 查看当前配置")
    print()
    print("q. 🚪 退出程序")
    print()
    print("-" * 60)
    print("💡 所有示例都需要AI客户端配置（推荐使用智谱AI）")


class ExampleManager:
    """示例程序管理器"""

    def __init__(self):
        self.ai_client = None  # 延迟初始化，避免导入错误
        self.ai_client_type = None  # 记录客户端类型
        self.logger = logging.getLogger(__name__)

    def get_ai_config(self):
        """获取AI配置（优先使用智谱AI）"""
        # 延迟导入避免在依赖检查阶段触发错误
        OpenAICompatClient, OpenAIConfig, ZhipuSDKClient, ZhipuConfig, _ = import_dependencies()

        # 方法1: 尝试从配置文件加载（优先智谱AI）
        try:
            from .config import ZHIPU_CONFIG, OPENAI_CONFIG
            if ZHIPU_CONFIG and ZHIPU_CONFIG.api_key.strip():
                self.ai_client_type = "zhipu"
                return ZHIPU_CONFIG
            elif OPENAI_CONFIG and OPENAI_CONFIG.api_key.strip():
                self.ai_client_type = "openai"
                return OPENAI_CONFIG
        except ImportError:
            pass

        # 方法2: 使用硬编码配置（用户需要修改）
        print("⚠️  未找到有效的AI配置，使用默认智谱AI配置")
        self.ai_client_type = "zhipu"
        return ZhipuConfig(
            api_key="",  # ⚠️ 请在此处填写您的智谱AI API密钥
            model="glm-4.5-flash",
            audit_model="glm-4.5-flash",
            audit_temperature=0.0,
            audit_max_tokens=1000,
            timeout=120,
            thinking_type="disabled"
        )

    def configure_ai_client(self) -> bool:
        """配置AI客户端（支持智谱AI和OpenAI）"""
        print("\n⚙️  AI客户端配置")
        print("-" * 30)

        # 获取配置
        config = self.get_ai_config()

        # 检查API密钥是否已配置
        if not config.api_key.strip():
            client_type = "智谱AI" if self.ai_client_type == "zhipu" else "OpenAI"
            print(f"❌ 检测到{client_type} API密钥未配置！")
            print("\n📝 请按以下步骤配置：")
            print("1. 编辑文件: aethelum_core_lite/examples/config.py")
            print("2. 在 api_key=\"\" 这一行填写您的API密钥")
            if self.ai_client_type == "zhipu":
                print("3. 获取智谱AI API密钥: https://open.bigmodel.cn/")
            else:
                print("3. 获取OpenAI API密钥: https://platform.openai.com/api-keys")
            print("\n🔄 配置完成后请重新运行程序")
            input("\n按回车键继续...")
            return False

        try:
            client_type = "智谱AI" if self.ai_client_type == "zhipu" else "OpenAI"
            print(f"\n🔧 正在创建{client_type}客户端...")
            print(f"   - API Key: {config.api_key[:10]}...{config.api_key[-4:]}")
            if hasattr(config, 'base_url'):
                print(f"   - Base URL: {config.base_url}")
            print(f"   - 模型: {config.model}")
            print(f"   - 审查模型: {config.audit_model}")

            # 根据类型创建客户端
            if self.ai_client_type == "zhipu":
                self.ai_client = ZhipuSDKClient(config)
            else:
                self.ai_client = OpenAICompatClient(config)

            print(f"✅ {client_type}客户端配置成功！")

            # 测试连接
            print("\n🔄 正在测试连接...")
            if self.ai_client.is_healthy():
                print(f"✅ {client_type}连接测试成功！")
                return True
            else:
                print(f"⚠️  {client_type}连接测试失败，但客户端已创建")
                return True

        except Exception as e:
            client_type = "智谱AI" if self.ai_client_type == "zhipu" else "OpenAI"
            print(f"❌ {client_type}客户端配置失败: {e}")
            self.ai_client = None
            return False

    def check_dependencies(self) -> dict:
        """检查依赖状态"""
        status = {
            "openai": False,
            "zhipu": False,
            "protobuf": False,
            "ai_client": False
        }

        # 检查OpenAI库
        try:
            import openai
            status["openai"] = True
        except ImportError:
            status["openai"] = False

        # 检查智谱AI库
        try:
            from zai import ZhipuAiClient
            status["zhipu"] = True
        except ImportError:
            status["zhipu"] = False

        # 检查ProtoBuf
        try:
            from aethelum_core_lite.core.protobuf_utils import ProtoBufManager
            status["protobuf"] = ProtoBufManager.is_available()
        except ImportError:
            status["protobuf"] = False

        # 检查AI客户端
        status["ai_client"] = self.ai_client is not None and self.ai_client.is_available

        return status

    def show_status(self):
        """显示当前配置状态"""
        print("\n📊 当前配置状态")
        print("-" * 30)

        status = self.check_dependencies()

        # OpenAI库状态
        print(f"OpenAI库: {'✅ 已安装' if status['openai'] else '❌ 未安装'}")

        # 智谱AI库状态
        print(f"智谱AI库: {'✅ 已安装' if status['zhipu'] else '❌ 未安装'}")

        # ProtoBuf状态
        print(f"ProtoBuf: {'✅ 可用' if status['protobuf'] else '❌ 不可用'}")

        # AI客户端状态
        if status["ai_client"]:
            client_type = "智谱AI" if self.ai_client_type == "zhipu" else "OpenAI"
            print(f"AI客户端: ✅ {client_type}已配置且可用")
            if self.ai_client:
                print(f"   - 类型: {client_type}")
                print(f"   - 模型: {self.ai_client.config.model}")
                print(f"   - 审查模型: {self.ai_client.config.audit_model}")
        else:
            print("AI客户端: ❌ 未配置或不可用")

        print()

    def run_single_example(self):
        """运行单消息基础示例"""
        print("\n⚡ 启动单消息基础示例")
        print("=" * 50)

        # 检查AI客户端
        if not self.ai_client or not self.ai_client.is_available:
            print("❌ 单消息示例需要配置AI客户端！")
            print("   请先选择选项5配置AI客户端")
            input("\n按回车键继续...")
            return

        try:
            from aethelum_core_lite.examples.single_example import main as single_main
            single_main()
        except Exception as e:
            print(f"❌ 示例运行失败: {e}")
            self.logger.error(f"单消息示例运行失败: {e}")

    def run_basic_example(self):
        """运行多线程基础示例"""
        print("\n🚀 启动多线程基础示例")
        print("=" * 50)

        # 检查AI客户端
        if not self.ai_client or not self.ai_client.is_available:
            print("❌ 多线程基础示例需要配置AI客户端！")
            print("   请先选择选项5配置AI客户端")
            input("\n按回车键继续...")
            return

        try:
            from aethelum_core_lite.examples.basic_example import main as basic_main
            basic_main()
        except Exception as e:
            print(f"❌ 示例运行失败: {e}")
            self.logger.error(f"多线程基础示例运行失败: {e}")

    def run_advanced_example(self):
        """运行高级功能示例"""
        print("\n✨ 启动高级功能示例")
        print("=" * 50)

        # 检查AI客户端
        if not self.ai_client or not self.ai_client.is_available:
            print("❌ 高级功能示例需要配置AI客户端！")
            print("   请先选择选项5配置AI客户端")
            input("\n按回车键继续...")
            return

        try:
            from aethelum_core_lite.examples.advanced_example import main as advanced_main
            advanced_main()
        except Exception as e:
            print(f"❌ 示例运行失败: {e}")
            self.logger.error(f"高级功能示例运行失败: {e}")

    def run_moral_audit_example(self):
        """运行内容安全审查示例"""
        print("\n🛡️ 启动内容安全审查示例")
        print("=" * 50)

        # 检查AI客户端
        if not self.ai_client or not self.ai_client.is_available:
            print("❌ 内容安全审查示例需要配置AI客户端！")
            print("   请先选择选项5配置AI客户端")
            input("\n按回车键继续...")
            return

        try:
            from aethelum_core_lite.examples.moral_audit_example import main as moral_main
            moral_main()
        except Exception as e:
            print(f"❌ 示例运行失败: {e}")
            self.logger.error(f"内容安全审查示例运行失败: {e}")

    def run(self):
        """运行主程序"""
        setup_logging()

        # 启动时进行依赖检查
        print_banner()
        print("\n🔍 进行依赖检查...")

        # 检查ProtoBuf状态（直接检查，不触发模块导入）
        print("📦 检查ProtoBuf状态...")
        protobuf_available = False
        try:
            # 首先检查protobuf库是否存在
            import google.protobuf
            print("✅ protobuf库已安装")

            # 然后检查编译后的schema文件是否存在
            schema_file = os.path.join(os.path.dirname(__file__), '..', 'core', 'protobuf_schema_pb2.py')
            if os.path.exists(schema_file):
                print("✅ ProtoBuf schema文件已编译")
                protobuf_available = True
            else:
                print("❌ ProtoBuf schema文件未找到")
        except ImportError:
            print("❌ protobuf库未安装")
        except Exception as e:
            print(f"❌ ProtoBuf检查失败: {e}")

        # 如果ProtoBuf不可用，退出程序
        if not protobuf_available:
            print("\n❌ ProtoBuf是Aethelum Core Lite的强制性依赖！")
            print("\n📝 请按以下步骤编译ProtoBuf schema：")
            print("1. 安装protoc编译器:")
            print("   Ubuntu/Debian: sudo apt-get install protobuf-compiler")
            print("   macOS: brew install protobuf")
            print("   Windows: 下载并安装 protoc")
            print("2. 编译schema文件:")
            print("   cd aethelum_core_lite/core")
            print("   protoc --python_out=. protobuf_schema.proto")
            print("\n💡 编译完成后请重新运行程序")
            return
        print()

        # 检查AI库状态
        print("🔍 检查AI库状态...")
        zhipu_available = False
        openai_available = False
        
        try:
            from zai import ZhipuAiClient
            print("✅ 智谱AI库已安装")
            zhipu_available = True
        except ImportError:
            print("❌ 智谱AI库未安装")
            
        try:
            import openai
            print("✅ OpenAI库已安装")
            openai_available = True
        except ImportError:
            print("❌ OpenAI库未安装")

        # 如果至少有一个AI库可用，继续
        if not (zhipu_available or openai_available):
            print("\n❌ 需要至少安装一个AI客户端库！")
            print("\n📝 请安装以下库之一：")
            print("1. 智谱AI库（推荐）: pip install zai-sdk")
            print("2. OpenAI库: pip install openai")
            print("💡 安装完成后请重新运行程序")
            return
        print()

        print("\n🔍 检测AI客户端配置...")

        # 尝试自动加载配置
        try:
            config = self.get_ai_config()
            if not config.api_key.strip():
                client_type = "智谱AI" if self.ai_client_type == "zhipu" else "OpenAI"
                print(f"\n❌ 检测到{client_type} API密钥未配置！")
                print("\n📝 请先配置AI客户端后运行程序：")
                print("\n🔧 配置方法（推荐）：")
                print("1. 复制 config_template.py 为 config.py")
                print("2. 在 config.py 中填写您的API密钥")
                if self.ai_client_type == "zhipu":
                    print("\n💡 获取智谱AI API密钥: https://open.bigmodel.cn/")
                else:
                    print("\n💡 获取OpenAI API密钥: https://platform.openai.com/api-keys")
                print("\n🔄 配置完成后请重新运行程序")
                return

            # 尝试创建客户端
            client_type = "智谱AI" if self.ai_client_type == "zhipu" else "OpenAI"
            print(f"🔧 正在初始化{client_type}客户端...")
            
            if self.ai_client_type == "zhipu":
                self.ai_client = ZhipuSDKClient(config)
            else:
                self.ai_client = OpenAICompatClient(config)

            # 测试客户端健康状态
            print("🔄 测试连接...")
            if self.ai_client.is_healthy():
                print(f"✅ {client_type}客户端配置成功并可用！")
            else:
                print(f"⚠️  {client_type}客户端已创建但连接测试失败")

        except Exception as e:
            print(f"❌ AI客户端初始化失败: {e}")
            print("\n请检查配置是否正确后重新运行程序")
            return

        print("\n🎉 初始化完成！现在可以运行示例程序了。")
        input("\n按回车键进入主菜单...")

        # 配置成功后进入主菜单循环
        while True:
            print_banner()
            print_menu()

            choice = input("请输入选项 (1-6, q): ").strip().lower()

            if choice == '1':
                self.run_single_example()
            elif choice == '2':
                self.run_basic_example()
            elif choice == '3':
                self.run_advanced_example()
            elif choice == '4':
                self.run_moral_audit_example()
            elif choice == '5':
                self.reconfigure_ai_client()
            elif choice == '6':
                self.show_status()
            elif choice == 'q':
                print("\n👋 感谢使用Aethelum Core Lite示例程序！")
                break
            else:
                print("❌ 无效选项，请重新输入！")

            if choice != 'q':
                input("\n按回车键返回主菜单...")

    def reconfigure_ai_client(self):
        """重新配置AI客户端（用于菜单选项5）"""
        print("\n⚙️  重新配置AI客户端")
        print("-" * 30)

        # 重新加载配置
        config = self.get_ai_config()

        if not config.api_key.strip():
            print("❌ API密钥未配置，请先按上述步骤配置！")
            input("\n按回车键继续...")
            return

        try:
            client_type = "智谱AI" if self.ai_client_type == "zhipu" else "OpenAI"
            print(f"\n🔧 重新创建{client_type}客户端...")
            
            if self.ai_client_type == "zhipu":
                self.ai_client = ZhipuSDKClient(config)
            else:
                self.ai_client = OpenAICompatClient(config)

            print(f"✅ {client_type}客户端重新配置成功！")
            print(f"   - API Key: {config.api_key[:10]}...{config.api_key[-4:]}")
            if hasattr(config, 'base_url'):
                print(f"   - Base URL: {config.base_url}")
            print(f"   - 模型: {config.model}")
            print(f"   - 审查模型: {config.audit_model}")

            # 测试连接
            print("\n🔄 测试连接...")
            if self.ai_client.is_healthy():
                print(f"✅ {client_type}连接测试成功！")
            else:
                print(f"⚠️  {client_type}连接测试失败，但客户端已创建")

        except Exception as e:
            print(f"❌ 重新配置失败: {e}")
            self.ai_client = None

        input("\n按回车键继续...")


def main():
    """主函数"""
    try:
        manager = ExampleManager()
        manager.run()
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        logging.error(f"主程序运行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
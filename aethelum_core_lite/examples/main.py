"""
AethelumCoreLite 示例程序主入口

提供统一的示例程序运行界面，使用 Mock AI 服务，无需真实 API keys。

使用方法:
    交互模式: python -m aethelum_core_lite.examples.main
    非交互模式: AETHELUM_NONINTERACTIVE=1 python -m aethelum_core_lite.examples.main
    CI模式: CI=1 python -m aethelum_core_lite.examples.main

功能特性:
- 多示例菜单选择
- 非交互模式支持（CI/CD 友好）
- Mock AI 服务（无需 API keys）
- 优雅的退出机制
"""

import sys
import os
import logging
import subprocess

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def print_banner():
    """打印程序横幅"""
    print("=" * 70)
    print("🚀 AethelumCoreLite - 示例程序主入口（Mock AI 版本）")
    print("📦 模拟树神经系统的通信框架")
    print("⚡ 支持并发处理 | 🛡️ 内置安全审查 | 🎯 统一架构")
    print("=" * 70)
    print()
    print("✨ 所有示例使用 Mock AI 服务，无需真实 API keys，开箱即用！")
    print()


def print_menu():
    """打印主菜单"""
    print("📋 请选择要运行的示例程序:")
    print()
    print("🔹 基础示例:")
    print("1. ⚡ 基础示例 (basic_example.py)")
    print("   - 神经脉冲消息传递")
    print("   - 队列管理和 Worker 处理")
    print("   - 并发消息处理")
    print("   - 线程安全的数据访问")
    print()
    print("2. 🚀 高级示例 (advanced_example.py)")
    print("   - 多个业务 Agent 协同")
    print("   - 优先级队列处理")
    print("   - 自定义 Hook 机制")
    print("   - 性能监控和指标收集")
    print()
    print("3. 📦 批量处理示例 (batch_processing_example.py)")
    print("   - 批量消息发送")
    print("   - 并发处理优化")
    print("   - 进度跟踪")
    print("   - 结果汇总")
    print()
    print("4. 🎣 自定义 Hook 示例 (custom_hook_example.py)")
    print("   - Logging Hook - 详细日志")
    print("   - Validation Hook - 数据验证")
    print("   - Transform Hook - 内容转换")
    print("   - Cache Hook - 结果缓存")
    print("   - Metrics Hook - 指标收集")
    print()
    print("5. 📊 性能演示 (performance_demo.py)")
    print("   - 吞吐量测试")
    print("   - 并发性能测试")
    print("   - 延迟分析")
    print()
    print("q. 🚪 退出程序")
    print()
    print("-" * 70)


def run_example(example_name: str, description: str):
    """运行指定的示例"""
    logger = logging.getLogger("Main")

    logger.info(f"启动示例: {description}")
    logger.info("-" * 70)

    try:
        # 使用 subprocess 运行示例，确保在独立进程中
        if example_name == "basic":
            subprocess.run([sys.executable, "-m", "aethelum_core_lite.examples.basic_example"],
                          check=True)
        elif example_name == "advanced":
            subprocess.run([sys.executable, "-m", "aethelum_core_lite.examples.advanced_example"],
                          check=True)
        elif example_name == "batch":
            subprocess.run([sys.executable, "-m", "aethelum_core_lite.examples.batch_processing_example"],
                          check=True)
        elif example_name == "custom_hook":
            subprocess.run([sys.executable, "-m", "aethelum_core_lite.examples.custom_hook_example"],
                          check=True)
        elif example_name == "performance":
            subprocess.run([sys.executable, "-m", "aethelum_core_lite.examples.performance_demo"],
                          check=True)

        logger.info("-" * 70)
        logger.info(f"✅ 示例 '{description}' 运行完成！")

    except subprocess.CalledProcessError as e:
        logger.error(f"示例运行失败: {e}")
    except KeyboardInterrupt:
        logger.info("\n示例被用户中断")
    except Exception as e:
        logger.error(f"运行出错: {e}")


def run_noninteractive_mode():
    """非交互模式 - 运行基础示例"""
    logger = logging.getLogger("Main")

    logger.info("🤖 非交互模式：运行基础示例")
    print()

    try:
        subprocess.run([sys.executable, "-m", "aethelum_core_lite.examples.basic_example"],
                      check=True)
        logger.info("✅ 非交互模式完成")
    except subprocess.CalledProcessError as e:
        logger.error(f"运行失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\n被用户中断")
        sys.exit(0)


def main():
    """主函数"""
    setup_logging()
    logger = logging.getLogger("Main")

    # 检测非交互模式
    NONINTERACTIVE = os.getenv("AETHELUM_NONINTERACTIVE") == "1" or os.getenv("CI") == "1"

    print_banner()

    if NONINTERACTIVE:
        # 非交互模式
        run_noninteractive_mode()
        return

    # 交互模式
    while True:
        try:
            print_menu()
            choice = input("请输入选项 (1-5 或 q): ").strip().lower()

            if choice == '1':
                run_example("basic", "基础示例")
            elif choice == '2':
                run_example("advanced", "高级示例")
            elif choice == '3':
                run_example("batch", "批量处理示例")
            elif choice == '4':
                run_example("custom_hook", "自定义 Hook 示例")
            elif choice == '5':
                run_example("performance", "性能演示")
            elif choice == 'q':
                print("\n👋 感谢使用 AethelumCoreLite 示例程序！")
                print("📚 更多信息请访问: https://github.com/corolin/AethelumCoreLite")
                break
            else:
                print("\n❌ 无效的选项，请重新选择")

            print()  # 空行分隔
            input("按 Enter 键继续...")  # 暂停，让用户查看结果

        except KeyboardInterrupt:
            print("\n\n👋 程序已退出")
            break
        except Exception as e:
            logger.error(f"发生错误: {e}")
            import traceback
            logger.debug(f"错误详情:\n{traceback.format_exc()}")

            input("按 Enter 键继续...")


if __name__ == "__main__":
    main()

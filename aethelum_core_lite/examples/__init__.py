"""
Aethelum Core Lite 示例程序包

包含多个示例程序，演示框架的各种功能和使用方式。

示例程序:
- main: 主入口程序，提供菜单选择和OpenAI配置
- moral_audit_example: 基础内容安全审查示例
- protobuf_audit_example: ProtoBuf集成示例

使用方法:
    python -m aethelum_core_lite.examples.main
"""

# 不自动导入模块，避免依赖检查问题
def run_examples():
    """运行示例程序的主入口函数"""
    from .main import main
    main()

__all__ = ["run_examples"]
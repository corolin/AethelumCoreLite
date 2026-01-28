#!/usr/bin/env python3
"""
安装发布所需的依赖

使用方法:
    python .gitea/scripts/install_dependencies.py
"""

import subprocess
import sys


def install_dependencies():
    """安装发布所需的依赖"""
    print("=" * 60)
    print("📦 安装 AethelumCoreLite 发布工具依赖")
    print("=" * 60)
    print()

    dependencies = [
        "build",
        "twine",
        "python-dotenv",
    ]

    print("将安装以下依赖:")
    for dep in dependencies:
        print(f"  - {dep}")
    print()

    response = input("确认安装? (Y/n): ")
    if response.lower() == 'n':
        print("❌ 取消安装")
        sys.exit(0)

    print()
    print("🔧 正在安装...")

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install"] + dependencies,
            check=True
        )
        print()
        print("=" * 60)
        print("✅ 安装完成!")
        print("=" * 60)
        print()
        print("下一步:")
        print("  1. 复制配置模板: cp .gitea/.env.example .gitea/.env")
        print("  2. 编辑配置文件: nano .gitea/.env (或使用其他编辑器)")
        print("  3. 验证配置: python .gitea/scripts/verify_gitea_config.py")
        print("  4. 发布包: python .gitea/scripts/publish_to_gitea.py")
        print()
    except subprocess.CalledProcessError as e:
        print()
        print("=" * 60)
        print("❌ 安装失败")
        print("=" * 60)
        print(f"\n错误代码: {e.returncode}")
        print("\n请手动安装:")
        print(f"  pip install {' '.join(dependencies)}")
        sys.exit(1)


if __name__ == "__main__":
    install_dependencies()

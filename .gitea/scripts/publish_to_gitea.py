#!/usr/bin/env python3
"""
发布包到 Gitea PyPI 仓库

使用方法:
    python scripts/publish_to_gitea.py

环境变量:
    GITEA_PYPI_URL - Gitea PyPI 仓库 URL
    GITEA_USERNAME - Gitea 用户名
    GITEA_PASSWORD - Gitea Token 或密码
"""

import os
import sys
import subprocess
from pathlib import Path

# 尝试导入 python-dotenv，如果不存在则跳过
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


def check_dependencies():
    """检查必要的依赖是否已安装"""
    required_modules = {
        'build': 'build',
        'twine': 'twine',
    }

    missing = []
    for module_name, package_name in required_modules.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print("=" * 60)
        print("❌ 缺少必要的依赖")
        print("=" * 60)
        print(f"\n请先安装以下包:")
        print(f"  pip install {' '.join(missing)}")
        print("\n或安装完整的发布工具:")
        print("  pip install build twine python-dotenv")
        print("=" * 60)
        sys.exit(1)


def load_env():
    """从环境变量加载配置"""
    # 尝试加载 .env 文件
    if HAS_DOTENV:
        # 查找 .gitea/.env 文件（从当前目录向上查找）
        current_dir = Path.cwd()
        env_file = None

        for parent in [current_dir] + list(current_dir.parents):
            potential_env = parent / '.gitea' / '.env'
            if potential_env.exists():
                env_file = potential_env
                break

        if env_file:
            load_dotenv(env_file)
            print(f"✅ 已加载配置文件: {env_file}")
            print()
        else:
            print("⚠️  未找到 .gitea/.env 文件，将使用系统环境变量")
            print()
    else:
        print("⚠️  未安装 python-dotenv，将使用系统环境变量")
        print("   安装: pip install python-dotenv")
        print()

    url = os.getenv("GITEA_PYPI_URL")
    username = os.getenv("GITEA_USERNAME")
    password = os.getenv("GITEA_PASSWORD")

    if not all([url, username, password]):
        print("❌ 错误: 缺少必要的环境变量")
        print("\n请设置以下环境变量或在 .gitea/.env 文件中配置:")
        print("  GITEA_PYPI_URL - Gitea PyPI 仓库 URL")
        print("  GITEA_USERNAME - Gitea 用户名")
        print("  GITEA_PASSWORD - Gitea Token 或密码")
        print("\n方法1: 使用 .gitea/.env 文件")
        print("  cp .gitea/.env.example .gitea/.env")
        print("  # 编辑 .gitea/.env 填入实际值")
        print("\n方法2: 设置环境变量")
        print("  # Linux/Mac:")
        print("  export GITEA_PYPI_URL='https://gitea.example.com/api/packages/owner/pypi'")
        print("  export GITEA_USERNAME='username'")
        print("  export GITEA_PASSWORD='your_token'")
        print("\n  # Windows (CMD):")
        print("  set GITEA_PYPI_URL=https://gitea.example.com/api/packages/owner/pypi")
        print("  set GITEA_USERNAME=username")
        print("  set GITEA_PASSWORD=your_token")
        print("\n  # Windows (PowerShell):")
        print("  $env:GITEA_PYPI_URL='https://gitea.example.com/api/packages/owner/pypi'")
        print("  $env:GITEA_USERNAME='username'")
        print("  $env:GITEA_PASSWORD='your_token'")
        sys.exit(1)

    return url, username, password


def build_package():
    """构建包"""
    print("🔨 开始构建包...")

    # 清理旧的构建文件
    dist_dir = Path("dist")
    if dist_dir.exists():
        subprocess.run(["rm", "-rf", "dist"], check=True)

    # 构建
    subprocess.run([sys.executable, "-m", "build"], check=True)
    print("✅ 构建完成")


def check_package():
    """检查包"""
    print("🔍 检查包...")
    subprocess.run([
        "twine", "check", "dist/*"
    ], check=True)
    print("✅ 包检查通过")


def publish_package(url, username, password):
    """发布到 Gitea"""
    print(f"📦 发布到 Gitea: {url}")

    subprocess.run([
        "twine", "upload",
        "--repository-url", url,
        "--username", username,
        "--password", password,
        "--verbose",
        "dist/*"
    ], check=True)

    print("✅ 发布成功!")


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 AethelumCoreLite - Gitea PyPI 发布工具")
    print("=" * 60)
    print()

    # 检查依赖
    check_dependencies()

    # 加载配置
    url, username, password = load_env()
    print(f"📍 仓库 URL: {url}")
    print(f"👤 用户名: {username}")
    print()

    # 构建包
    build_package()

    # 检查包
    check_package()

    # 确认发布
    print()
    response = input("确认发布? (y/N): ")
    if response.lower() != 'y':
        print("❌ 取消发布")
        sys.exit(0)

    # 发布包
    publish_package(url, username, password)


if __name__ == "__main__":
    main()

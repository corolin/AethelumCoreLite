#!/usr/bin/env python3
"""
验证 Gitea PyPI 配置是否正确

使用方法:
    python scripts/verify_gitea_config.py
"""

import os
import sys
from pathlib import Path

# 尝试导入 python-dotenv
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


def find_and_load_env():
    """查找并加载 .gitea/.env 文件"""
    if HAS_DOTENV:
        current_dir = Path.cwd()
        for parent in [current_dir] + list(current_dir.parents):
            env_file = parent / '.gitea' / '.env'
            if env_file.exists():
                load_dotenv(env_file)
                return env_file
    return None


def verify_config():
    """验证配置"""
    print("=" * 60)
    print("🔍 Gitea PyPI 配置验证工具")
    print("=" * 60)
    print()

    # 检查 python-dotenv
    if HAS_DOTENV:
        print("✅ python-dotenv 已安装")
    else:
        print("⚠️  python-dotenv 未安装")
        print("   安装命令: pip install python-dotenv")
        print()

    # 查找 .env 文件
    env_file = find_and_load_env()
    if env_file:
        print(f"✅ 找到配置文件: {env_file}")
    else:
        print("⚠️  未找到 .env 文件")
        print("   提示: 复制模板文件 cp .gitea/.env.example .gitea/.env")
        print()

    # 读取配置
    url = os.getenv("GITEA_PYPI_URL")
    username = os.getenv("GITEA_USERNAME")
    password = os.getenv("GITEA_PASSWORD")

    # 验证配置项
    print("-" * 60)
    print("配置项检查:")
    print("-" * 60)

    checks = [
        ("GITEA_PYPI_URL", url, "Gitea PyPI 仓库 URL"),
        ("GITEA_USERNAME", username, "Gitea 用户名"),
        ("GITEA_PASSWORD", password, "Gitea Token 或密码"),
    ]

    all_ok = True
    for env_var, value, description in checks:
        if value:
            # 隐藏密码的完整值
            if "PASSWORD" in env_var:
                display_value = f"{value[:8]}..." if len(value) > 8 else "***"
            else:
                display_value = value
            print(f"✅ {env_var:20} = {display_value}")
            print(f"   ({description})")
        else:
            print(f"❌ {env_var:20} = (未设置)")
            print(f"   ({description})")
            all_ok = False
        print()

    # 验证 URL 格式
    if url:
        print("-" * 60)
        print("URL 格式验证:")
        print("-" * 60)

        if url.startswith("https://") or url.startswith("http://"):
            print("✅ URL 协议正确 (http/https)")
        else:
            print("❌ URL 协议错误 (应以 http:// 或 https:// 开头)")
            all_ok = False

        if "/api/packages/" in url:
            print("✅ URL 包含 /api/packages/ 路径")
        else:
            print("⚠️  URL 可能缺少 /api/packages/ 路径")
            print("   正确格式: https://gitea.example.com/api/packages/{owner}/pypi")

        if url.endswith("/pypi"):
            print("✅ URL 以 /pypi 结尾")
        else:
            print("⚠️  URL 应以 /pypi 结尾")

        print()

    # 总结
    print("=" * 60)
    if all_ok:
        print("✅ 配置验证通过！可以开始发布")
        print()
        print("下一步:")
        print("  python scripts/publish_to_gitea.py")
    else:
        print("❌ 配置验证失败，请修正后重试")
        print()
        print("提示:")
        print("  1. 复制模板: cp .gitea/.env.example .gitea/.env")
        print("  2. 编辑 .gitea/.env 文件，填入实际值")
        print("  3. 重新运行此脚本验证")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    verify_config()

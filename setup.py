"""
Aethelum Core Lite - 灵壤精核
模拟神经网络的通信框架
"""

from setuptools import setup, find_packages
import os

# 读取README文件
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Aethelum Core Lite - 神经网络通信框架"

# 读取requirements文件
def read_requirements():
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    requirements = []
    if os.path.exists(requirements_path):
        with open(requirements_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('-'):
                    requirements.append(line)
    return requirements

setup(
    name="aethelum-core-lite",
    version="1.0.0",
    author="Aethelum Team",
    author_email="team@aethelum.ai",
    description="模拟神经网络的通信框架",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/aethelum/aethelum-core-lite",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=6.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "mypy>=0.991",
        ],
        "docs": [
            "sphinx>=4.5.0",
            "sphinx-rtd-theme>=1.0.0",
        ],
    },
    keywords=[
        "neural-network",
        "ai",
        "moral-audit",
        "communication",
        "agent",
        "protobuf",
        "openai",
        "safety",
    ],
    project_urls={
        "Bug Reports": "https://github.com/aethelum/aethelum-core-lite/issues",
        "Source": "https://github.com/aethelum/aethelum-core-lite",
        "Documentation": "https://aethelum-core-lite.readthedocs.io/",
    },
    include_package_data=True,
    zip_safe=False,
)
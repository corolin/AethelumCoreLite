# 打包配置说明

## 配置方式

本项目采用现代化的 **纯 pyproject.toml** 打包配置（符合 PEP 517/621 标准）。

### 文件结构

```
aethelum-core-lite/
├── pyproject.toml          # 主配置文件（PEP 621）
├── requirements/           # 开发依赖管理
│   ├── base.txt           # 核心运行依赖
│   ├── dev.txt            # 开发工具依赖
│   └── docs.txt           # 文档生成依赖
└── .gitignore             # 忽略 setup.py 和 requirements.txt
```

### 为什么移除 setup.py？

1. **避免配置重复**: pyproject.toml 已包含所有打包信息
2. **符合现代标准**: PEP 517/621 推荐使用 pyproject.toml
3. **简化维护**: 单一配置源，避免不一致
4. **更好的工具支持**: pip、build、poetry 等工具优先支持 pyproject.toml

### 为什么移除 requirements.txt？

1. **依赖集中管理**: 所有依赖已在 pyproject.toml 中定义
2. **避免重复**: requirements.txt 与 pyproject.toml 重复
3. **版本锁定**: 使用 requirements/ 目录管理不同环境的依赖

### requirements/ 目录说明

虽然 pyproject.toml 已经定义了依赖，但 requirements/ 目录仍然有用：

- **base.txt**: 仅包含核心运行依赖，方便部署
- **dev.txt**: 包含开发工具（pytest、black、mypy 等）
- **docs.txt**: 包含文档工具（sphinx 等）

这些文件可以：
- 快速安装特定环境依赖
- 作为 CI/CD 的依赖源
- 方便不使用 pyproject.toml 的用户

## 安装方式

### 方式 1: 使用 pyproject.toml（推荐）

```bash
# 安装核心依赖
pip install -e .

# 安装开发依赖
pip install -e ".[dev]"

# 安装性能优化依赖
pip install -e ".[performance]"

# 安装所有依赖
pip install -e ".[all]"
```

### 方式 2: 使用 requirements 文件

```bash
# 安装核心依赖
pip install -r requirements/base.txt

# 安装开发依赖
pip install -r requirements/dev.txt
```

## 构建发布包

```bash
# 使用 PEP 517 构建
python3 -m build

# 或使用 pip
pip install build
python3 -m build --outdir dist/
```

## 依赖管理

### 添加核心依赖

编辑 `pyproject.toml`:

```toml
[project]
dependencies = [
    "requests>=2.25.0",
    "protobuf>=3.20.0",
    "your-package>=1.0.0",  # 添加新依赖
]
```

### 添加可选依赖

编辑 `pyproject.toml`:

```toml
[project.optional-dependencies]
your-group = [
    "package1>=1.0.0",
    "package2>=2.0.0",
]
```

### 更新 requirements/ 文件

```bash
# 从 pyproject.toml 生成 requirements 文件
pip-compile pyproject.toml --extra dev -o requirements/dev.txt
```

## 锁文件（可选）

如果需要完全可复现的环境，可以使用 pip-tools：

```bash
# 安装 pip-tools
pip install pip-tools

# 生成锁文件
pip-compile pyproject.toml --extra dev --output-file requirements/dev.lock

# 安装锁文件
pip install -r requirements/dev.lock
```

## 迁移说明

如果你有旧的项目使用了 setup.py 或 requirements.txt：

1. **安装新版本**:
   ```bash
   pip install -e ".[all]"
   ```

2. **更新 CI/CD 配置**:
   ```bash
   # 旧方式
   pip install -r requirements.txt

   # 新方式
   pip install -e ".[dev]"
   ```

3. **更新 Dockerfile**:
   ```dockerfile
   # 旧方式
   COPY requirements.txt .
   RUN pip install -r requirements.txt

   # 新方式
   COPY pyproject.toml .
   RUN pip install -e ".[all]"
   ```

## 兼容性

- **Python 版本**: >= 3.8
- **pip 版本**: >= 19.0 (支持 PEP 517)
- **setuptools**: >= 45.0 (构建后端)

## 参考资料

- [PEP 517 - A build-system independent format](https://peps.python.org/pep-0517/)
- [PEP 621 - Storing project metadata in pyproject.toml](https://peps.python.org/pep-0621/)
- [Python Packaging User Guide](https://packaging.python.org/)

# 发布到 Gitea PyPI 仓库指南

本文档说明如何将 AethelumCoreLite 发布到私有 Gitea PyPI 仓库。

## 📋 前置要求

### 方法 1: 使用安装脚本（推荐）

```bash
python .gitea/scripts/install_dependencies.py
```

安装脚本会自动安装所有必要的依赖。

### 方法 2: 手动安装

```bash
pip install build twine python-dotenv
```

### 获取 Gitea Token（推荐）

- 登录 Gitea
- 设置 → 应用令牌 → 生成新令牌
- 作用域选择: `read:package`, `write:package`

## ⚙️ 配置方法

### 方法 1: 使用环境变量（推荐）

1. **复制环境变量模板**
   ```bash
   cp .gitea/.env.example .gitea/.env
   ```

2. **编辑 .env 文件**
   ```bash
   # Gitea PyPI 仓库 URL
   # 将 {owner} 替换为你的组织/用户名
   GITEA_PYPI_URL=https://gitea.example.com/api/packages/{owner}/pypi

   # Gitea 用户名
   GITEA_USERNAME=your-username

   # Gitea Token（推荐使用 Token 而非密码）
   GITEA_PASSWORD=your-token-here
   ```

3. **发布**
   ```bash
   python .gitea/scripts/publish_to_gitea.py
   ```

### 方法 2: 使用 ~/.pypirc

1. **创建或编辑 `~/.pypirc`**（Windows: `C:\Users\你的用户名\.pypirc`）

   ```ini
   [distutils]
   index-servers =
       gitea

   [gitea]
   repository = https://gitea.example.com/api/packages/{owner}/pypi
   username = your-username
   password = your-token-here
   ```

2. **构建并发布**
   ```bash
   # 构建
   python -m build

   # 检查
   twine check dist/*

   # 发布
   twine upload -r gitea dist/*
   ```

### 方法 3: 命令行参数

```bash
# Windows
set GITEA_PYPI_URL=https://gitea.example.com/api/packages/{owner}/pypi
set GITEA_USERNAME=your-username
set GITEA_PASSWORD=your-token
python .gitea/scripts/publish_to_gitea.py

# Linux/Mac
export GITEA_PYPI_URL=https://gitea.example.com/api/packages/{owner}/pypi
export GITEA_USERNAME=your-username
export GITEA_PASSWORD=your-token
python .gitea/scripts/publish_to_gitea.py
```

## 🚀 完整发布流程

```bash
# 1. 安装构建工具
pip install build twine python-dotenv

# 2. 配置环境变量
cp .gitea/.env.example .gitea/.env
# 编辑 .env 填入实际值

# 3. 验证配置（可选）
python .gitea/scripts/verify_gitea_config.py

# 4. 运行发布脚本
python .gitea/scripts/publish_to_gitea.py
```

发布脚本会自动：
1. 清理旧的构建文件
2. 构建包（wheel + source distribution）
3. 检查包的完整性
4. 询问确认
5. 发布到 Gitea PyPI 仓库

## 📥 从 Gitea 安装

### 临时安装

```bash
pip install --index-url https://gitea.example.com/api/packages/{owner}/pypi/simple aethelum-core-lite
```

### 配置 pip 永久使用 Gitea

**Linux/Mac:** `~/.pip/pip.conf` 或 `/etc/pip.conf`
```ini
[global]
index-url = https://gitea.example.com/api/packages/{owner}/pypi/simple
trusted-host = gitea.example.com
```

**Windows:** `C:\ProgramData\pip\pip.ini` 或 `%APPDATA%\pip\pip.ini`
```ini
[global]
index-url = https://gitea.example.com/api/packages/{owner}/pypi/simple
trusted-host = gitea.example.com
```

### 使用 requirements.txt

```
--index-url=https://gitea.example.com/api/packages/{owner}/pypi/simple
--extra-index-url=https://pypi.org/simple
aethelum-core-lite==1.0.0
```

## 🔐 安全最佳实践

1. **使用 Token 而非密码**
   - 在 Gitea 设置 → 应用令牌中创建专用 Token
   - Token 可以随时撤销

2. **不要将 .env 提交到版本控制**
   - `.gitea/.env` 已被忽略（`.gitea/` 在 `.gitignore` 中）
   - 只提交 `.gitea/.env.example` 作为模板

3. **在 CI/CD 中使用环境变量**
   ```yaml
   # GitHub Actions 示例
   - name: Publish to Gitea
     env:
       GITEA_PYPI_URL: ${{ secrets.GITEA_PYPI_URL }}
       GITEA_USERNAME: ${{ secrets.GITEA_USERNAME }}
       GITEA_PASSWORD: ${{ secrets.GITEA_PASSWORD }}
     run: |
       python -m build
       python .gitea/scripts/publish_to_gitea.py
   ```

4. **限制 Token 权限**
   - 只授予 `read:package` 和 `write:package` 权限
   - 不要授予仓库管理权限

## 🛠️ 常见问题

### Q: 发布时出现 401 错误
**A:** 检查用户名和 Token 是否正确，确保 Token 有 `write:package` 权限。

### Q: 发布时出现 400 错误
**A:** 可能是版本号已存在，需要更新 [pyproject.toml](../../pyproject.toml) 中的 `version` 字段。

### Q: pip 安装时找不到包
**A:**
1. 确认 URL 格式正确（末尾需要 `/simple`）
2. 检查 Gitea 仓库的可见性设置
3. 确认用户有 `read:package` 权限

### Q: 如何更新已发布的包？
**A:**
1. 更新 `pyproject.toml` 中的版本号（如 `1.0.0` → `1.0.1`）
2. 重新运行发布脚本

## 📚 相关文档

- [Gitea 官方文档 - 使用 PyPI 包仓库](https://docs.gitea.com/usage/packages/pypi)
- [Twine 用户指南](https://twine.readthedocs.io/)
- [Python 打包用户指南](https://packaging.python.org/)

## 🆘 获取帮助

如果遇到问题：
1. 查看 Gitea 服务器日志
2. 检查 `twine` 的详细输出（脚本已启用 `--verbose`）
3. 确认网络连接和防火墙设置

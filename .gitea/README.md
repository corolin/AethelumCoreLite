# .gitea 目录说明

此目录包含与私有 PyPI 仓库发布相关的配置和脚本，主要用于发布到 Gitea、GitLab 等私有包仓库。

## 📁 目录结构

```
.gitea/
├── .env.example           # 环境变量模板
├── README.md              # 本文件
├── scripts/
│   ├── publish_to_gitea.py       # Python 发布脚本（跨平台）
│   └── verify_gitea_config.py    # 配置验证脚本
└── docs/
    └── PUBLISHING_TO_GITEA.md    # 详细发布文档
```

## 🔐 隐私说明

**整个 `.gitea/` 目录已添加到 `.gitignore`**，不会被提交到版本控制。

这样做的原因：
- `.env` 文件包含敏感信息（仓库 URL、用户名、Token/密码）
- 不同开发者的发布配置可能不同
- 避免将私有仓库信息泄露到公开仓库

## 🚀 快速开始

1. **复制配置模板**
   ```bash
   cp .gitea/.env.example .gitea/.env
   ```

2. **编辑配置**
   ```bash
   # 编辑 .gitea/.env，填入你的仓库信息
   # GITEA_PYPI_URL=https://your-gitea.com/api/packages/{owner}/pypi
   # GITEA_USERNAME=your-username
   # GITEA_PASSWORD=your-token
   ```

3. **验证配置**
   ```bash
   python .gitea/scripts/verify_gitea_config.py
   ```

4. **发布包**
   ```bash
   python .gitea/scripts/publish_to_gitea.py
   ```

## 📚 更多文档

详细说明请参阅 [发布文档](docs/PUBLISHING_TO_GITEA.md)。

## 🔄 与其他仓库的兼容性

虽然目录名称是 `.gitea`，但这些脚本同样适用于：

- ✅ GitLab Package Registry
- ✅ GitHub Package Registry
- ✅ AWS CodeArtifact
- ✅ Sonatype Nexus
- ✅ JFrog Artifactory
- ✅ devpi
- ✅ pypiserver

只需在 `.gitea/.env` 中配置对应的仓库 URL 即可。

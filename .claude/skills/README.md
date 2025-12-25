# Aethelum Core Lite - Claude Code Skills

这个目录包含 Aethelum Core Lite 项目的 Claude Code 技能配置文件。

## 可用技能

### 1. test - 运行测试
运行项目的所有测试或指定测试文件

```bash
# 运行所有测试
test

# 运行指定测试文件
test tests/test_message.py

# 运行测试并生成覆盖率报告
test --coverage
```

### 2. run-example - 运行示例程序
运行 Aethelum Core Lite 的示例程序

```bash
# 运行主示例程序（交互式菜单）
run-example

# 运行基础示例
run-example basic

# 运行高级示例
run-example advanced

# 运行道德审计示例
run-example moral_audit

# 运行单线程示例
run-example single
```

### 3. compile-protobuf - 编译 ProtoBuf
编译 protobuf schema 文件生成 Python 代码

```bash
# 编译 protobuf
compile-protobuf

# 清理旧文件后编译
compile-protobuf --clean
```

### 4. format-code - 格式化代码
使用 black 格式化 Python 代码

```bash
# 格式化所有代码
format-code

# 只检查不修改
format-code --check
```

### 5. type-check - 类型检查
使用 mypy 进行 Python 类型检查

```bash
# 检查所有代码
type-check

# 检查指定文件
type-check aethelum_core_lite/core/router.py
```

### 6. install-dependencies - 安装依赖
安装项目依赖包

```bash
# 安装基础依赖
install-dependencies

# 安装开发依赖
install-dependencies --dev
```

### 7. git-status - Git状态
查看 Git 仓库状态和变更摘要

```bash
# 查看简要状态
git-status

# 查看详细差异
git-status --detailed
```

### 8. git-commit - Git提交
创建 Git 提交

```bash
# 提交所有变更
git-commit "feat: 添加新的Hook链管理功能"

# 指定提交信息并添加所有文件
git-commit "fix: 修复工作器调度bug" --all
```

## 项目结构说明

```
aethelum_core_lite/
├── core/           # 核心组件（router, queue, worker, message）
├── hooks/          # Hook机制实现
├── utils/          # 工具类（日志、验证等）
├── agents/         # Agent实现
├── workers/        # 工作器实现
└── examples/       # 示例程序
```

## 常用工作流程

### 开发新功能
1. `git-status` - 查看当前状态
2. `format-code` - 格式化代码
3. `type-check` - 类型检查
4. `test` - 运行测试
5. `git-commit "feat: xxx"` - 提交代码

### 调试示例程序
1. `run-example basic` - 运行基础示例
2. `run-example advanced` - 运行高级示例
3. 查看日志输出
4. 根据需要修改代码
5. `run-example` 重新运行

### 更新 ProtoBuf
1. 编辑 `aethelum_core_lite/core/protobuf_schema.proto`
2. `compile-protobuf` - 编译生成 Python 代码
3. `test` - 运行测试验证
4. `git-commit "update: 更新protobuf schema"` - 提交变更

## 技能配置文件格式

每个技能都是一个 JSON 文件，包含以下字段：

- `title`: 技能标题
- `description`: 技能描述
- `command`: 基础命令
- `arguments`: 参数列表（可选）
  - `name`: 参数名
  - `description`: 参数描述
  - `required`: 是否必需
  - `type`: 参数类型（string/boolean/enum）
  - `default`: 默认值
  - `enum`: 可选值列表（仅用于enum类型）
- `examples`: 使用示例列表

## 扩展技能

要添加新技能，请在 `skills/` 目录下创建新的 JSON 文件，遵循上述格式。

示例：

```json
{
  "title": "我的新技能",
  "description": "技能描述",
  "command": "command-name",
  "arguments": [
    {
      "name": "arg1",
      "description": "参数描述",
      "required": false,
      "default": "default_value"
    }
  ],
  "examples": [
    "skill-name",
    "skill-name --arg1 value"
  ]
}
```

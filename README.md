# Aethelum Core Lite - 灵壤精核

模拟树神经的通信框架

## 特性

- 🧠 **树神经架构**: 基于生物树神经概念的通信框架
- 🤖 **智谱AI集成**: 默认集成智谱AI客户端，支持深度思考模式
- 📦 **ProtoBuf支持**: 高效消息序列化（可选依赖）
- ⚡ **线程安全**: 多线程环境下的安全通信
- 🔍 **可选审核**: 提供内容安全审查示例（非强制流程）

## 安装

### 基础安装
```bash
pip install aethelum-core-lite
```

### 开发环境安装
```bash
git clone https://github.com/aethelum/aethelum-core-lite.git
cd aethelum-core-lite
pip install -e ".[dev]"
```

### 完整安装（包含开发工具和文档）
```bash
pip install -e ".[dev,docs]"
```

### ProtoBuf 编译要求（可选）

ProtoBuf是可选依赖，仅在需要使用ProtoBuf序列化功能时才需要编译：

```bash
# 安装protoc编译器
# Ubuntu/Debian:
sudo apt-get install protobuf-compiler

# macOS:
brew install protobuf

# Windows:
# 下载并安装 protoc: https://github.com/protocolbuffers/protobuf/releases

# 编译schema文件（仅在需要ProtoBuf功能时）
cd aethelum_core_lite/core
protoc --python_out=. protobuf_schema.proto
```

## 核心概念

### 神经脉冲 (NeuralImpulse)
在神经元间传递的信息包，包含：
- `session_id`: 会话ID
- `action_intent`: 路由目标
- `source_agent`: 消息来源
- `content`: 消息内容（支持ProtoBuf）
- `metadata`: 元数据

### 神经元组件

#### NeuralSomaRouter (神经胞体路由器)
主控制器，管理队列和工作器：
```python
from aethelum_core_lite import NeuralSomaRouter
from aethelum_core_lite.core.zhipu_client import ZhipuConfig

# 创建智谱AI配置（默认推荐）
config = ZhipuConfig(
    api_key="your-zhipu-api-key",
    model="glm-4.5-flash"
)

# 一键创建完整的神经系统
router = NeuralSomaRouter()
router.auto_setup()
```

#### SynapticQueue (突触队列)
线程安全的FIFO队列：
```python
queue = SynapticQueue("test_queue")
queue.put(impulse)
impulse = queue.get()
```

#### AxonWorker (轴突工作器)
消息处理单元：
```python
def process_message(impulse, source_queue):
    return impulse

# 使用auto_setup方法自动处理Hook注册和工作器启动
router.auto_setup(
    business_handler=process_message,
    response_handler=None  # 可选
)
```

#### AuditAgent (审计Agent) - 可选示例
内容安全审查（作为示例提供，非强制流程）
```python
from aethelum_core_lite.examples.agents import AuditAgent
from aethelum_core_lite.core.zhipu_client import ZhipuConfig, ZhipuSDKClient

# 配置智谱AI客户端
config = ZhipuConfig(
    api_key="your-zhipu-api-key",
    model="glm-4.5-flash"
)
zhipu_client = ZhipuSDKClient(config)

# 创建审计Agent（示例用途）
audit_agent = AuditAgent("SecurityAgent", zhipu_client)
```

## 快速开始

### 运行示例程序

最简单的开始方式是运行我们的示例程序主入口：

```bash
# 运行示例程序主入口
python -m aethelum_core_lite.examples.main
```

示例程序提供：
- 📋 交互式菜单选择不同示例
- 🔍 内容安全审查示例（可选）
- 🚀 高级多线程功能演示
- 📦 ProtoBuf集成示例（可选）
- 📊 配置状态检查

### 基础使用示例

```python
from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.core.zhipu_client import ZhipuConfig

# 1. 配置智谱AI客户端（推荐）
config = ZhipuConfig(
    api_key="your-zhipu-api-key",
    model="glm-4.5-flash"
)

# 2. 创建路由器并一键设置
router = NeuralSomaRouter()

# 3. 定义业务处理函数
def business_handler(impulse, source_queue):
    # 处理业务逻辑
    response = f"处理了您的请求: {impulse.get_text_content()}"
    impulse.set_text_content(response)
    impulse.update_source("BusinessAgent")
    impulse.reroute_to("Q_RESPONSE_SINK")  # 直接路由到响应
    return impulse

# 4. 一键自动设置整个神经系统
router.auto_setup(
    business_handler=business_handler,
    response_handler=None  # 可选
)

# 5. 发送消息
impulse = NeuralImpulse(
    content="你好，请帮我解答问题",
    action_intent="Q_PROCESS_INPUT"  # 使用标准输入队列
)
router.inject_input(impulse)
```

## 配置

### 智谱AI配置（推荐）
```python
from aethelum_core_lite.core.zhipu_client import ZhipuConfig, ZhipuSDKClient

config = ZhipuConfig(
    api_key="your-zhipu-api-key",
    model="glm-4.5-flash",
    audit_model="glm-4.5-flash",
    audit_temperature=0.0,
    audit_max_tokens=1000,
    thinking_type="disabled"  # 可选："enabled" 启用深度思考模式
)

client = ZhipuSDKClient(config)
```

### 审计Agent配置（示例）
```python
# 审计流程作为示例提供，非强制使用
audit_agent = AuditAgent(
    agent_name="CustomAuditAgent",
    client=client  # 支持智谱AI或OpenAI兼容客户端
)
```

## 安全特性

- **可选审核**: 提供内容安全审查示例，可根据需要启用
- **ProtoBuf支持**: 可选的消息序列化和加密传输
- **灵活架构**: 支持自定义安全验证机制
- **AI驱动**: 基于智谱AI的智能内容处理

## 开发

### 运行测试
```bash
pytest tests/
```

### 代码格式化
```bash
black aethelum_core_lite/
```

### 类型检查
```bash
mypy aethelum_core_lite/
```

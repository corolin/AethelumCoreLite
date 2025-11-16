# Aethelum Core Lite - 灵壤精核

模拟神经网络的通信框架

## 特性

- 🧠 **神经网络架构**: 基于生物神经概念的通信框架
- 🔍 **内容安全审查**: 集成完整的审查和反注入系统
- 📦 **ProtoBuf强制**: 高效消息序列化（强制依赖）
- ⚡ **线程安全**: 多线程环境下的安全通信

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

### ProtoBuf 编译要求

**重要**: ProtoBuf是强制性依赖，必须编译schema文件才能运行：

```bash
# 安装protoc编译器
# Ubuntu/Debian:
sudo apt-get install protobuf-compiler

# macOS:
brew install protobuf

# Windows:
# 下载并安装 protoc: https://github.com/protocolbuffers/protobuf/releases

# 编译schema文件
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
from aethelum_core_lite.core.openai_client import OpenAIConfig

# 创建配置
config = OpenAIConfig(
    api_key="your-api-key",
    model="gpt-3.5-turbo"
)

# 一键创建完整的神经系统
router = NeuralSomaRouter(openai_config=config)
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

#### AuditAgent (审计Agent)
内容安全审查
```python
from aethelum_core_lite.agents import AuditAgent
from aethelum_core_lite.core.openai_client import OpenAICompatClient, OpenAIConfig

# 配置OpenAI客户端
config = OpenAIConfig(
    api_key="your-api-key",
    model="gpt-3.5-turbo"
)
openai_client = OpenAICompatClient(config)

# 创建审计Agent
audit_agent = AuditAgent("SecurityAgent", openai_client)
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
- ⚙️ OpenAI客户端配置向导
- 🔍 内容安全审查基础示例
- 🚀 高级多线程功能演示
- 📦 ProtoBuf集成完整示例
- 📊 配置状态检查

### 基础使用示例

```python
from aethelum_core_lite import NeuralSomaRouter, NeuralImpulse
from aethelum_core_lite.core.openai_client import OpenAIConfig, OpenAICompatClient

# 1. 配置OpenAI客户端
config = OpenAIConfig(
    api_key="your-openai-api-key",
    model="gpt-3.5-turbo"
)

# 2. 创建路由器并一键设置
router = NeuralSomaRouter(openai_config=config)

# 3. 定义业务处理函数
def business_handler(impulse, source_queue):
    # 处理业务逻辑
    response = f"处理了您的请求: {impulse.get_text_content()}"
    impulse.set_text_content(response)
    impulse.update_source("BusinessAgent")
    impulse.reroute_to("Q_AUDIT_OUTPUT")
    return impulse

# 4. 一键自动设置整个神经系统
router.auto_setup(
    business_handler=business_handler,
    response_handler=None  # 可选
)

# 5. 发送消息进行审计
impulse = NeuralImpulse(
    content="你好，请帮我解答问题",
    action_intent="Q_AUDIT_INPUT"
)
router.inject_input(impulse)
```

## 内容安全审查系统

系统提供完整的内容安全检查机制：

### 违规类型
- `AnimalAbuse`: 虐待动物
- `SuicideSelfHarm`: 自杀与自残
- `Violence`: 暴力行为
- `HarmToOthers`: 对他人的致命伤害
- `SexualContent`: 性暗示内容
- `IllegalActivity`: 违法犯罪活动

### 双重随机性验证
- `primary_shift`: 主要加密偏移量 (1-25)
- `secondary_seed`: 辅助随机种子 (1-25)
- `final_shift`: 最终偏移量 = (primary_shift + secondary_seed) % 26

## 配置

### OpenAI配置
```python
from aethelum_core_lite.core.openai_client import OpenAIConfig, OpenAICompatClient

config = OpenAIConfig(
    api_key="your-api-key",
    base_url="https://api.openai.com/v1",
    model="gpt-3.5-turbo",
    audit_model="gpt-3.5-turbo",
    audit_temperature=0.0,
    audit_max_tokens=150
)

client = OpenAICompatClient(config)
```

### 审计Agent配置
```python
audit_agent = AuditAgent(
    agent_name="CustomAuditAgent",
    openai_client=client
)
```

## 安全特性

- **强制审查**: 所有输入输出必须经过内容安全审查
- **ProtoBuf加密**: 支持消息加密传输
- **双重验证**: 多层次的安全验证机制
- **AI驱动**: 基于AI的智能内容识别

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

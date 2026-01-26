# Aethelum Core Lite - 灵壤精核

模拟树神经的通信框架

## 特性

- 🧠 **树神经架构**: 基于生物树神经概念的通信框架
- 🤖 **智谱AI集成**: 默认集成智谱AI客户端，支持深度思考模式
- ⚡ **极致性能**: 异步 WAL + msgpack，持久化性能损失仅 7%，吞吐量达 40,000+ msg/s
- 💾 **高性能持久化**: 采用 WAL 架构，非阻塞写入，自动故障恢复
- 📦 **ProtoBuf支持**: 高效消息序列化（可选依赖）
- 🔒 **线程安全**: 多线程环境下的安全通信
- 🔍 **可选审核**: 提供内容安全审查示例（非强制流程）

## 安装

### 基础安装
```bash
pip install aethelum-core-lite
```

### 开发环境安装
```bash
# 克隆仓库
git clone https://github.com/aethelum/aethelum-core-lite.git
cd aethelum-core-lite

# 安装核心依赖
pip install -r requirements/base.txt

# 安装开发依赖（包含核心依赖）
pip install -r requirements/dev.txt
```

### 完整安装（包含开发工具和文档）
```bash
# 方式1：使用 pyproject.toml
pip install -e ".[dev,docs]"

# 方式2：使用 requirements 文件
pip install -r requirements/dev.txt
pip install -r requirements/docs.txt
```

### 性能优化（推荐）

为了获得最佳的持久化性能，建议安装 msgpack：

```bash
# 方式1：使用 pyproject.toml 可选依赖
pip install -e ".[performance]"

# 方式2：直接安装 msgpack
# Ubuntu/Debian
sudo apt-get install python3-msgpack

# macOS
brew install python-msgpack

# 使用 pip
pip install msgpack
```

**msgpack 的优势：**
- ⚡ 序列化速度比 JSON 快 3-5 倍
- 💾 二进制格式，文件体积更小
- 🔄 自动回退：未安装时自动使用 JSON 格式

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
线程安全的优先级队列，支持高性能持久化：

```python
# 基础使用
queue = SynapticQueue("test_queue")
queue.put(impulse, priority=5)  # 支持优先级
impulse = queue.get()

# 启用持久化（推荐用于生产环境）
queue = SynapticQueue(
    queue_id="persistent_queue",
    enable_persistence=True,
    persistence_path="/data/queue",
    cleanup_interval=300.0  # 5分钟清理一次
)
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

## 持久化与性能

### WAL (Write-Ahead Log) 架构

Aethelum Core Lite 采用高性能的 WAL 架构实现消息持久化，确保在保持极致性能的同时提供数据可靠性保障。

#### 架构设计

```
生产者线程 → 内存缓冲 (deque) → 后台写入线程 → log1.msgpack (消息日志)
                                                    ↓
消费者线程 → 内存缓冲 (deque) → 后台写入线程 → log2.msgpack (消费日志)
                                                    ↓
                              后台清理线程 → 清理已处理消息
```

**核心优势：**
- ⚡ **非阻塞写入**: 生产者/消费者只写内存，耗时 <0.001ms
- 🚀 **批量写入**: 后台线程每秒批量序列化 + 写入文件
- 💾 **msgpack 序列化**: 二进制格式，比 JSON 快 3-5 倍
- 🔄 **自动清理**: 后台线程定期清理已处理消息

#### 性能测试结果

端到端压测（5生产者 + 5消费者，持续10秒）：

| 方案 | 生产吞吐量 | 消费吞吐量 | 性能损失 |
|------|-----------|-----------|---------|
| 无持久化 | 46,205 msg/s | 2,913 msg/s | - |
| **异步 WAL + msgpack** ✅ | **42,972 msg/s** | **2,824 msg/s** | **7.0%** |
| 同步 WAL + msgpack | 20,750 msg/s | 1,846 msg/s | 56.5% |
| 旧版 JSON 持久化 | <100 msg/s | - | 99%+ |

**优化历程：**
1. **WAL 设计**: log1 (消息日志) + log2 (消费日志) 分离
2. **msgpack 序列化**: 替代 JSON，序列化速度提升 3-5 倍
3. **异步写入**: 内存缓冲 + 后台线程，彻底消除文件锁竞争
4. **批量 flush**: 每 100 条消息批量写入，减少系统调用

**最终成果：**
- ✅ 运行时性能损失仅 **7%**
- ✅ close() 快速关闭（311ms 包含最终 flush）
- ✅ 消息可靠性保证（先写缓冲再返回）
- ✅ 崩溃恢复（启动时从 log1 自动重建）

### 基础使用

#### 启用持久化

```python
from aethelum_core_lite import SynapticQueue, NeuralImpulse

# 创建持久化队列
queue = SynapticQueue(
    queue_id="my_queue",
    max_size=0,  # 0 = 无限制
    enable_persistence=True,
    persistence_path="/data/queue_data",  # 不含扩展名
    cleanup_interval=300.0  # 5分钟清理一次
)

# 正常使用
impulse = NeuralImpulse(
    content="Hello",
    action_intent="Q_PROCESS_INPUT"
)
queue.put(impulse, priority=5)
result = queue.get()

# 关闭队列（会触发最终flush）
queue.close()
```

#### 持久化文件说明

启用持久化后会生成两个文件（如果安装了 msgpack）：

```
/data/queue_data_log1.msgpack  # 消息日志（append-only）
/data/queue_data_log2.msgpack  # 消费日志（append-only）
```

**文件格式：**
- **msgpack 模式**（推荐）: 二进制格式，高性能
  - 优先使用，如果安装了 `python3-msgpack`
  - 每条消息：4字节长度前缀 + msgpack 数据
- **JSON 模式**（兼容）: 文本格式，可读性好
  - 回退方案，未安装 msgpack 时使用
  - 每行一个 JSON 对象

#### 依赖要求

**msgpack 是可选依赖**，优先使用 msgpack，否则自动回退到 JSON：

```bash
# Ubuntu/Debian
sudo apt install python3-msgpack

# 或使用 pip
pip install msgpack
```

### 性能优化建议

1. **安装 msgpack**: 序列化性能提升 3-5 倍
2. **调整清理间隔**: 根据消息量调整 `cleanup_interval`（默认 300 秒）
3. **监控文件大小**: 定期检查 log1 文件大小，避免过大
4. **合理设置队列大小**: 如果内存受限，设置 `max_size` 限制队列长度

### 故障恢复

启动时自动从 `log1` 恢复未处理的消息：

```python
queue = SynapticQueue(
    queue_id="my_queue",
    enable_persistence=True,
    persistence_path="/data/queue_data"
)
# 自动加载 log1 中未处理的消息
# 自动执行清理（移除上次运行已处理的消息）
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

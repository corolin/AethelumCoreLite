# Aethelum Core Lite - 灵壤精核

<div align="center">

🧠 基于 AsyncIO 的 AI Agent 高性能通信框架

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

✨ **特性**: 高并发架构 | WAL持久化 | Hook系统 | Prometheus监控 | 安全可靠

</div>

---

## ✨ 特性亮点

### 🚀 高并发架构
- **AsyncIO 设计**：专为 AI Agent I/O 密集型场景优化
- **高并发能力**：支持 1000+ Agent 并发处理
- **低内存占用**：协程栈仅几 KB，比线程轻量 10 倍
- **I/O 优化**：专为 AI API 调用、数据库操作等 I/O 密集型任务设计

### 💾 可靠持久化
- **WAL 架构**：双日志设计（log1 + log2）
- **异步写入**：后台批量写入，生产者零阻塞
- **自动恢复**：崩溃后自动重建未完成消息
- **灵活配置**：可选 msgpack 序列化（3-5x 性能提升）

### 🔒 安全可靠
- **API 认证**：Metrics API 强制 Bearer Token 认证
- **内容验证**：防止 DoS 攻击（10MB 限制、100 层嵌套限制）
- **消息完整性**：SHA256 哈希校验

### 🎯 高级特性
- **Hook 系统**：Pre/Post/Error 异步 Hook，支持自定义处理逻辑
- **监控集成**：Prometheus + OpenTelemetry 分布式追踪
- **配置管理**：TOML 配置文件，支持环境变量
- **Metrics API**：FastAPI 自动生成 Swagger UI

---

## 🚀 快速开始

### 安装

```bash
# 基础安装
pip install aethelum-core-lite

# 推荐安装（包含性能优化）
pip install aethelum-core-lite[performance]

# 完整安装（监控 + API）
pip install aethelum-core-lite[all]
```

### 5 分钟示例

```python
import asyncio
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.async_hooks import AsyncBaseHook, AsyncHookType

# 定义处理 Hook
class HandlerHook(AsyncBaseHook):
    async def process_async(self, impulse, source_queue):
        content = impulse.get_text_content()
        impulse.set_text_content(f"已处理: {content}")
        return impulse

async def main():
    # 1. 创建路由器
    router = AsyncNeuralSomaRouter("my_router")

    # 2. 创建队列（启用 WAL 持久化）
    queue = AsyncSynapticQueue("input_queue", enable_wal=True)

    # 3. 创建工作器
    worker = AsyncAxonWorker("worker_1", input_queue=queue)

    # 4. 注册组件
    router.register_queue(queue)
    router.register_worker(worker)

    # 5. 注册处理 Hook
    await router.register_hook(
        queue_name="input_queue",
        hook_function=HandlerHook("handler"),
        hook_type=AsyncHookType.PRE_PROCESS
    )

    # 6. 启动系统
    await router.start()

    # 7. 发送消息
    from aethelum_core_lite.core.message import NeuralImpulse
    impulse = NeuralImpulse(content="Hello AethelumCore!")
    await queue.async_put(impulse)

    # 8. 等待处理
    await asyncio.sleep(1)

    # 9. 停止系统
    await router.stop()

asyncio.run(main())
```

**运行示例程序**:
```bash
python -m aethelum_core_lite.examples.async_example
```

<details>
<summary>📖 查看更多示例</summary>

- **队列增强**: `examples/async_queue_enhanced_example.py`
- **工作器增强**: `examples/async_worker_enhanced_example.py`
- **路由器增强**: `examples/async_router_enhanced_example.py`
- **配置管理**: `examples/config_example.py`
- **监控集成**: `examples/monitoring_example.py`

</details>

---

## 🧠 核心概念

### 架构概览

```
┌─────────────┐
│   Producer  │
└──────┬──────┘
       │ NeuralImpulse
       ▼
┌──────────────────┐
│ AsyncSynapticQueue │ ← WAL持久化（可选）
└──────┬───────────┘
       │
       ▼
┌─────────────────┐
│ AsyncAxonWorker  │ ← Hook系统
└──────┬──────────┘
       │
       ▼
┌────────────────────┐
│ AsyncNeuralSomaRouter │ ← 监控指标
└───────────────────┘
```

### NeuralImpulse（神经脉冲）

在神经元间传递的消息包，包含：

```python
from aethelum_core_lite.core.message import NeuralImpulse, MessagePriority

impulse = NeuralImpulse(
    session_id="sess-001",        # 会话标识
    action_intent="Q_PROCESS",    # 路由目标
    source_agent="UserAgent",     # 消息来源
    content="Hello AI",            # 消息内容
    priority=MessagePriority.HIGH # 优先级
)
```

**核心字段**：
- `session_id`: 会话标识符
- `action_intent`: 下一个处理队列名称（路由键）
- `source_agent`: 上一个处理该消息的 Agent 标识符
- `content`: 消息内容（支持任意类型）
- `metadata`: 元数据字典
- `priority`: 消息优先级（CRITICAL、HIGH、NORMAL、LOW、BACKGROUND）

### AsyncSynapticQueue（异步突触队列）

```python
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue, MessagePriority

# 创建队列
queue = AsyncSynapticQueue(
    queue_id="my_queue",
    max_size=10000,              # 0 = 无限制
    enable_wal=True,             # 启用持久化
    wal_dir="./wal_data",        # WAL 目录
    message_ttl=3600             # 1小时过期
)

# 启动队列
await queue.start()

# 放入消息
await queue.async_put(impulse, priority=MessagePriority.HIGH)

# 批量操作
await queue.batch_put([
    (impulse1, MessagePriority.HIGH),
    (impulse2, MessagePriority.NORMAL)
])

# 获取消息
impulse = await queue.async_get()

# 停止队列
await queue.stop()
```

**核心特性**：
- 支持优先级队列
- 可选 WAL 持久化
- 消息 TTL（自动过期）
- 批量操作
- 并发安全（asyncio.Lock）

### AsyncAxonWorker（异步工作器）

```python
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.async_hooks import AsyncBaseHook, AsyncHookType

# 定义处理 Hook
class MyHook(AsyncBaseHook):
    async def process_async(self, impulse, source_queue):
        # 处理逻辑
        content = impulse.get_text_content()
        impulse.set_text_content(f"处理结果: {content}")
        return impulse

# 创建工作器
worker = AsyncAxonWorker(
    name="my_worker",
    input_queue=input_queue,
    max_consecutive_failures=5,   # 最大连续失败次数
    recovery_delay=5.0,            # 恢复延迟（秒）
    health_check_interval=30.0,    # 健康检查间隔
    processing_timeout=60.0        # 处理超时
)

# 注册 Hook
worker.register_hook(AsyncHookType.PRE_PROCESS, MyHook("my_hook"))

# 启动工作器
await worker.start()

# 获取统计信息
stats = await worker.get_stats()
print(f"处理消息: {stats.processed_messages}")
print(f"健康分数: {stats.health_score}")

# 停止工作器
await worker.stop()
```

**核心特性**：
- 异步消息处理
- Hook 集成（通过 Router 注册到队列）
- 健康监控和自动恢复
- 超时保护
- 统计信息收集

### AsyncNeuralSomaRouter（异步神经路由器）

```python
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

# 创建路由器
router = AsyncNeuralSomaRouter("main_router")

# 注册队列
router.register_queue(queue1, priority=QueuePriority.HIGH)
router.register_queue(queue2, priority=QueuePriority.NORMAL)

# 注册工作器
router.register_worker(worker1)
router.register_worker(worker2)

# 添加路由规则
router.add_routing_rule("pattern_a", "queue1")
router.add_routing_rule("pattern_b", "queue2")

# 启动路由器
await router.start()

# 路由消息
await router.route_message(data, "pattern_a")

# 获取指标
metrics = router.get_metrics()
print(f"总消息路由: {metrics['router']['total_messages_routed']}")

# 停止路由器
await router.stop()
```

**核心特性**：
- 组件管理（队列、工作器）
- 基于模式的消息路由
- Hook 系统（队列级、全局级）
- 性能指标收集
- 自动启动/停止所有组件

---

## ⚙️ 高级特性

### 💾 WAL 持久化

<details>
<summary>📖 详细说明</summary>

#### 架构设计

```
生产者 → 内存缓冲 → 后台写入 → log1.wal（消息日志）
                                ↓
消费者 → 内存缓冲 → 后台写入 → log2.wal（消费日志）
                                ↓
                          清理任务（定期删除已处理消息）
```

#### 核心特性

- **非阻塞写入**：生产者/消费者只写内存，耗时 <0.001ms
- **批量写入**：后台线程每秒批量序列化 + 写入文件
- **msgpack 序列化**：二进制格式，比 JSON 快 3-5 倍（可选）
- **自动清理**：后台线程定期清理已处理消息
- **崩溃恢复**：启动时从 log1 自动重建未完成消息

#### 使用方式

```python
# 启用 WAL
queue = AsyncSynapticQueue(
    queue_id="persistent_queue",
    enable_wal=True,
    wal_dir="./wal_data",
    message_ttl=3600  # 1小时过期
)

# 启动队列（启动 WAL 写入器）
await queue.start()

# 正常使用
await queue.async_put(message)

# 停止队列（触发最终 flush）
await queue.stop()
```

#### 文件格式

启用 WAL 后会生成两个文件：

```
./wal_data/persistent_queue_log1.wal  # 消息日志（append-only）
./wal_data/persistent_queue_log2.wal  # 消费日志（append-only）
```

**文件格式**：
- **msgpack 模式**（推荐）: 二进制格式，高性能
  - 优先使用，如果安装了 `python3-msgpack`
  - 每条消息：4字节长度前缀 + msgpack 数据
- **JSON 模式**（兼容）: 文本格式，可读性好
  - 回退方案，未安装 msgpack 时使用
  - 每行一个 JSON 对象

#### 安装 msgpack（推荐）

```bash
# Ubuntu/Debian
sudo apt install python3-msgpack

# macOS
brew install python-msgpack

# 使用 pip
pip install msgpack
```

</details>

### 🪝 Hook 系统

<details>
<summary>📖 详细说明</summary>

#### Hook 类型

| 类型 | 触发时机 | 用途 |
|------|----------|------|
| PRE_PROCESS | 消息处理前 | 验证、转换、日志 |
| POST_PROCESS | 处理成功后 | 通知、缓存、日志 |
| ERROR_HANDLER | 处理失败时 | 重试、告警、降级 |

#### 创建 Hook

```python
from aethelum_core_lite.core.async_hooks import AsyncBaseHook, AsyncHookType
import logging

class LoggingHook(AsyncBaseHook):
    """日志记录 Hook"""

    def __init__(self, name: str):
        super().__init__(name)
        self.logger = logging.getLogger(name)

    async def process_async(self, impulse, source_queue):
        self.logger.info(f"Processing: {impulse.message_id}")
        # 记录处理时间
        impulse.metadata['hook_processed_at'] = time.time()
        return impulse
```

#### 注册 Hook

```python
# 方式1: 在 Worker 上注册
worker.register_hook(AsyncHookType.PRE_PROCESS, LoggingHook("logger"))
worker.register_hook(AsyncHookType.POST_PROCESS, TransformHook("transformer"))

# 方式2: 在 Router 上注册（全局 Hook）
await router.register_hook(
    queue_name="input_queue",
    hook_function=logging_hook,
    hook_type=AsyncHookType.PRE_PROCESS
)
```

#### Hook 最佳实践

```python
# 1. 快速失败（验证 Hook）
async def validation_hook(impulse, source_queue):
    if not impulse.content:
        raise ValueError("Content is required")
    return impulse

# 2. 转换消息（预处理 Hook）
async def transform_hook(impulse, source_queue):
    impulse.metadata['processed'] = True
    impulse.content = impulse.content.upper()
    return impulse

# 3. 错误处理（错误 Hook）
async def error_hook(impulse, source_queue, error):
    logger.error(f"Error processing {impulse.message_id}: {error}")
    # 发送告警
    await send_alert(error)
    # 标记消息为失败
    impulse.reroute_to("Q_ERROR")
    return impulse
```

</details>

### 📊 监控与可观测性

<details>
<summary>📖 详细说明</summary>

#### Prometheus 指标

```python
from aethelum_core_lite.monitoring import PrometheusExporter

# 创建导出器
exporter = PrometheusExporter(
    host="127.0.0.1",
    port=8000,
    persist_state=True  # 持久化计数器状态
)

# 启动服务器
exporter.start_server()

# 访问 http://localhost:8000/metrics
```

**指标类型**：
- **Counter**: 消息总数、处理总数
- **Gauge**: 队列大小、工作器健康分数
- **Histogram**: 处理延迟分布

#### OpenTelemetry 追踪

```python
from aethelum_core_lite.monitoring import TracingManager

# 创建追踪管理器
tracer = TracingManager(
    service_name="my-service",
    jaeger_host="localhost",
    jaeger_port=6831,
    sample_rate=0.1  # 10% 采样
)

# 启动追踪
tracer.start()

# 创建 span
with tracer.trace("process_message") as span:
    span.set_tag("message_id", impulse.message_id)
    # 处理逻辑
```

#### Metrics API

```python
from aethelum_core_lite.api import MetricsAPIServer
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

router = AsyncNeuralSomaRouter("my_router")

# 创建 API 服务器（必须提供 API 密钥）
api_server = MetricsAPIServer(
    router=router,
    api_key="your-secret-key"  # 生产环境必须设置
)

# 启动服务器
import uvicorn
uvicorn.run(api_server.app, host="127.0.0.1", port=8080)

# 访问 http://localhost:8080/docs（Swagger UI）
```

**API 端点**：
- `GET /api/v1/metrics` - 获取所有指标
- `GET /api/v1/health` - 健康检查
- `GET /docs` - Swagger UI

**认证**：

```bash
# 使用 Bearer Token
curl -H "Authorization: Bearer <your-key>" \
     http://localhost:8080/api/v1/metrics
```

</details>

### ⚙️ 配置管理

<details>
<summary>📖 详细说明</summary>

#### 配置文件

创建 `config.toml`：

```toml
[system]
worker_mode = "async"
max_workers = 100
queue_size = 10000

[monitoring]
enable_prometheus = true
prometheus_port = 8000
enable_tracing = true
tracing_sample_rate = 0.1

[api]
metrics_api_port = 8080
api_key = "${AETHELUM_API_KEY}"  # 环境变量（推荐）

[performance]
async_io_concurrency = 1000
hook_timeout = 30.0
```

#### 加载配置

```python
from aethelum_core_lite.config import ConfigLoader

# 从文件加载
config = ConfigLoader.load_from_file("config.toml")

# 获取特定配置
system_config = ConfigLoader.get_system_config(config)
monitoring_config = ConfigLoader.get_monitoring_config(config)
api_config = ConfigLoader.get_api_config(config)

# 使用配置
print(f"Max workers: {system_config.max_workers}")
print(f"Prometheus port: {monitoring_config.prometheus_port}")
```

#### 环境变量

```bash
# 设置 API Key（推荐）
export AETHELUM_API_KEY="your-secret-key"

# 在配置文件中引用
[api]
api_key = "${AETHELUM_API_KEY}"
```

#### 默认配置

```python
# 获取默认配置（当文件不存在时）
default_config = ConfigLoader._get_default_config()
```

</details>

### 🔒 安全特性

<details>
<summary>📖 详细说明</summary>

#### API 认证

```bash
# 生成 API Key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 在配置文件中设置
[api]
api_key = "生成的密钥"

# 访问 API 时携带 Token
curl -H "Authorization: Bearer <your-key>" \
     http://localhost:8080/api/v1/metrics
```

#### 内容验证

AethelumCoreLite 自动验证消息内容，防止 DoS 攻击：

- **消息大小限制**：10MB（防 DoS）
- **JSON 深度限制**：100 层
- **字符串长度限制**：1MB

```python
from aethelum_core_lite.core.message import NeuralImpulse

# 自动验证
impulse = NeuralImpulse(content="safe content")
result = impulse.validate()

if not result.is_valid:
    print(f"Validation errors: {result.errors}")
```

#### 消息完整性

```python
# 计算 SHA256 哈希
impulse.compute_content_hash()

# 验证内容是否被篡改
if impulse.verify_content_integrity():
    print("Content is intact")
else:
    print("Content has been tampered with!")
```

</details>

---

## 📘 使用指南

### 场景 1: AI Agent 编排

<details>
<summary>📖 查看代码</summary>

```python
import asyncio
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.message import NeuralImpulse

async def agent_system():
    # 创建路由器
    router = AsyncNeuralSomaRouter("agent_system")

    # 创建多个 Agent 队列
    queues = {
        "input": AsyncSynapticQueue("agent_input", enable_wal=True),
        "llm": AsyncSynapticQueue("agent_llm"),
        "tool": AsyncSynapticQueue("agent_tool"),
        "output": AsyncSynapticQueue("agent_output")
    }

    # 启动队列
    for q in queues.values():
        await q.start()
        router.register_queue(q)

    # LLM Agent
    async def llm_agent(impulse, source_queue):
        # 调用 LLM API
        query = impulse.get_text_content()
        response = await call_llm_api(query)
        impulse.set_text_content(response)
        impulse.reroute_to("output")
        return impulse

    llm_worker = AsyncAxonWorker("llm_agent", queues["llm"], llm_agent)
    router.register_worker(llm_worker)

    # Tool Agent
    async def tool_agent(impulse, source_queue):
        # 执行工具调用
        tool_name = impulse.metadata.get("tool_name")
        result = await execute_tool(tool_name, impulse.content)
        impulse.set_content(result)
        impulse.reroute_to("llm")  # 返回 LLM
        return impulse

    tool_worker = AsyncAxonWorker("tool_agent", queues["tool"], tool_agent)
    router.register_worker(tool_worker)

    # 启动系统
    await router.start()

    # 发送任务
    task = NeuralImpulse(
        content="帮我查询今天的天气",
        action_intent="llm"
    )
    await queues["input"].async_put(task)

    # 等待处理
    await asyncio.sleep(2)

    # 停止系统
    await router.stop()

asyncio.run(agent_system())
```

</details>

### 场景 2: 流式数据处理

<details>
<summary>📖 查看代码</summary>

```python
async def stream_processor():
    router = AsyncNeuralSomaRouter("stream_processor")

    # 流式队列（TTL 5 分钟）
    queue = AsyncSynapticQueue(
        "stream_queue",
        message_ttl=300,  # 5 分钟后过期
        enable_wal=True
    )

    await queue.start()
    router.register_queue(queue)

    # 流式处理
    async def process_stream(impulse, source_queue):
        data = impulse.content
        # 处理流式数据
        result = transform(data)
        impulse.set_content(result)
        return impulse

    worker = AsyncAxonWorker("stream_worker", queue, process_stream)
    router.register_worker(worker)

    await router.start()

    # 模拟流式输入
    for i in range(1000):
        impulse = NeuralImpulse(content={"index": i, "data": f"stream_{i}"})
        await queue.async_put(impulse)

    # 等待处理
    await asyncio.sleep(1)

    # 查看统计
    stats = await worker.get_stats()
    print(f"Processed: {stats.processed_messages}")

    await router.stop()

asyncio.run(stream_processor())
```

</details>

### 场景 3: 高并发 Web 服务

<details>
<summary>📖 查看代码</summary>

```python
from fastapi import FastAPI
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue
from aethelum_core_lite.core.async_worker import AsyncAxonWorker
from aethelum_core_lite.core.message import NeuralImpulse
import uuid

app = FastAPI()
router = AsyncNeuralSomaRouter("web_service")
queue = AsyncSynapticQueue("api_queue", enable_wal=True)

@app.on_event("startup")
async def startup():
    await queue.start()
    router.register_queue(queue)

    # 创建 Worker
    async def process_request(impulse, source_queue):
        # 处理请求
        result = await process(impulse.content)
        impulse.set_content(result)
        return impulse

    worker = AsyncAxonWorker("api_worker", queue, process_request)
    router.register_worker(worker)
    await router.start()

@app.on_event("shutdown")
async def shutdown():
    await router.stop()
    await queue.stop()

@app.post("/api/process")
async def process_request(data: dict):
    # 异步处理请求
    task_id = str(uuid.uuid4())
    impulse = NeuralImpulse(
        content=data,
        session_id=task_id
    )
    await queue.async_put(impulse)
    return {"status": "queued", "task_id": task_id}

@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    # 查询结果
    # 实现中需要维护任务状态存储
    return {"task_id": task_id, "status": "processing"}
```

</details>

### 场景 4: 监控集成

<details>
<summary>📖 查看代码</summary>

```python
from aethelum_core_lite.monitoring import PrometheusExporter, TracingManager
from aethelum_core_lite.api import MetricsAPIServer

async def monitoring_example():
    # 创建路由器
    router = AsyncNeuralSomaRouter("monitored_router")

    # 启动 Prometheus
    exporter = PrometheusExporter(port=8000)
    exporter.start_server()

    # 启动追踪
    tracer = TracingManager(
        service_name="aethelum-service",
        jaeger_host="localhost",
        sample_rate=0.1
    )
    tracer.start()

    # 启动 Metrics API
    api_server = MetricsAPIServer(
        router=router,
        api_key="secret-key"
    )

    # 使用 uvicorn 运行 API
    import uvicorn
    config = uvicorn.Config(api_server.app, host="127.0.0.1", port=8080)
    server = uvicorn.Server(config)
    await server.serve()

asyncio.run(monitoring_example())
```

</details>

---

## 🔧 API 参考

### AsyncNeuralSomaRouter

```python
class AsyncNeuralSomaRouter:
    def __init__(router_id: str)
    async def start()
    async def stop()
    def register_queue(queue: AsyncSynapticQueue, priority: QueuePriority)
    def register_worker(worker: AsyncAxonWorker)
    async def route_message(data: Any, pattern: str)
    def add_routing_rule(pattern: str, queue_id: str)
    async def register_hook(queue_name: str, hook_function: Callable, hook_type: AsyncHookType)
    def get_metrics() -> dict
```

### AsyncSynapticQueue

```python
class AsyncSynapticQueue:
    def __init__(queue_id: str, max_size: int = 0, enable_wal: bool = True, wal_dir: str = "wal_data", message_ttl: Optional[float] = None)
    async def start()
    async def stop()
    async def async_put(item: Any, priority: MessagePriority = MessagePriority.NORMAL)
    async def async_get() -> Any
    async def batch_put(items: List[Tuple[Any, MessagePriority]]) -> int
    async def clear()
    def size() -> int
    def empty() -> bool
    def get_metrics() -> QueueMetrics
```

### AsyncAxonWorker

```python
class AsyncAxonWorker:
    def __init__(name: str, input_queue: AsyncSynapticQueue, hooks: Optional[List[BaseHook]] = None, max_consecutive_failures: int = 5, recovery_delay: float = 5.0)
    async def start()
    async def stop()
    def register_hook(hook_type: AsyncHookType, hook: AsyncBaseHook)
    async def get_stats() -> AsyncWorkerStats
    def get_health_score() -> float
```

<details>
<summary>📖 查看完整 API 文档</summary>

完整 API 文档请参考：
- [AsyncSynapticQueue API](docs/api/async_queue.md)
- [AsyncAxonWorker API](docs/api/async_worker.md)
- [AsyncNeuralSomaRouter API](docs/api/async_router.md)
- [NeuralImpulse API](docs/api/message.md)
- [Hook 系统 API](docs/api/hooks.md)

</details>

---

## 🔍 故障排查

### 常见问题

#### 问题 1: WAL 性能下降

**症状**: 消息处理变慢

**原因**: 未安装 msgpack

**解决**:
```bash
pip install msgpack
```

#### 问题 2: 内存占用高

**症状**: 进程内存持续增长

**原因**: 队列未启用 TTL 或 WAL 清理间隔过长

**解决**:
```python
queue = AsyncSynapticQueue(
    queue_id="my_queue",
    message_ttl=3600,  # 1 小时过期
    enable_wal=True
)
```

#### 问题 3: API 认证失败

**症状**: 401 Unauthorized

**原因**: 未设置 API Key 或 Token 错误

**解决**:
```bash
# 1. 检查配置文件
cat config.toml | grep api_key

# 2. 检查请求头
curl -H "Authorization: Bearer <correct-key>" \
     http://localhost:8080/api/v1/metrics
```

#### 问题 4: 消息丢失

**症状**: 发送的消息未处理

**原因**: 队列已满或 WAL 未启动

**解决**:
```python
# 1. 检查队列大小
queue = AsyncSynapticQueue(queue_id="my_queue", max_size=0)  # 0 = 无限制

# 2. 确保启动 WAL
await queue.start()  # 启动 WAL 写入器

# 3. 检查 WAL 日志
ls -lh wal_data/
```

<details>
<summary>📖 查看调试技巧</summary>

#### 启用详细日志

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 或使用环境变量
export AETHELUM_LOG_LEVEL=DEBUG
```

#### 性能分析

```python
# 查看 Worker 利用率
metrics = router.get_metrics()
for worker_id, worker_metrics in metrics['workers'].items():
    print(f"{worker_id}: {worker_metrics['health_score']}%")

# 查看队列使用率
for queue_id, queue_metrics in metrics['queues'].items():
    print(f"{queue_id}: {queue_metrics['usage_percent']:.1f}%")
```

#### Hook 调试

```python
# 添加日志 Hook
class DebugHook(AsyncBaseHook):
    async def process_async(self, impulse, source_queue):
        print(f"[DEBUG] Hook processing: {impulse.message_id}")
        return impulse

worker.register_hook(AsyncHookType.PRE_PROCESS, DebugHook("debug"))
```

</details>

---

## 🛠️ 开发指南

### 环境设置

```bash
# 克隆仓库
git clone https://github.com/aethelum/aethelum-core-lite.git
cd aethelum-core-lite

# 安装开发依赖
pip install -e ".[dev]"

# 安装预提交钩子（可选）
pre-commit install
```

### 运行测试

```bash
# 全部测试
pytest tests/

# 仅 AsyncIO 测试
pytest tests/test_async_*.py -v

# 并发安全测试
pytest tests/test_concurrency_safety.py -v
```

### 代码质量

```bash
# 格式化代码
black aethelum_core_lite/

# 类型检查
mypy aethelum_core_lite/

# Linting
flake8 aethelum_core_lite/
```

### 构建文档

```bash
# 安装文档依赖
pip install -e ".[docs]"

# 构建 Sphinx 文档
cd docs
make html

# 查看文档
open _build/html/index.html
```

### 贡献流程

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

<details>
<summary>📖 开发规范</summary>

#### 代码风格

- 遵循 PEP 8
- 使用类型注解
- 编写 docstring（Google 风格）
- 单元测试覆盖率 > 80%

#### Commit 规范

```
feat: 添加新功能
fix: 修复 bug
docs: 文档更新
refactor: 重构代码
test: 测试相关
chore: 构建/工具相关
```

#### Pull Request 检查清单

- [ ] 通过所有测试
- [ ] 添加/更新文档
- [ ] 更新 CHANGELOG.md
- [ ] 代码通过格式化检查

</details>

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

感谢所有贡献者的支持！

## 📮 联系方式

- 官网: https://aethelum.com
- 文档: https://aethelum-core-lite.readthedocs.io/
- Issues: https://github.com/aethelum/aethelum-core-lite/issues

---

<div align="center">

**🌟 如果觉得有用，请给我们一个 Star！**

Made with ❤️ by Aethelum Team

</div>

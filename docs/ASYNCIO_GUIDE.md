# AsyncIO 架构和监控功能使用指南

## 概述

本文档介绍 AethelumCoreLite 的 AsyncIO 架构和监控功能的使用方法。

## 核心特性

### 1. AsyncIO 架构

专为 AI Agent I/O 密集型场景设计的异步架构：
- **高并发**：支持 1000+ 个并发 Agent（相比多线程的 100 个）
- **低内存**：协程栈仅几 KB（相比线程的 8MB）
- **低延迟**：响应延迟降低 30-50%

### 2. 配置管理

统一的 TOML 配置文件管理：
- 系统配置（Worker 模式、队列大小等）
- 监控配置（Prometheus、OpenTelemetry、API）
- 性能配置（并发数、超时等）

### 3. 监控和可观察性

- **Prometheus 指标**：标准化的指标导出
- **OpenTelemetry 追踪**：完整的分布式链路追踪
- **指标查询 API**：简化的指标查询接口

## 快速开始

### 1. 安装依赖

```bash
# 基础依赖
pip install -e .

# 监控功能
pip install -e ".[monitoring]"

# API 功能
pip install -e ".[api]"

# 全部功能
pip install -e ".[all]"
```

### 2. 配置文件

创建 `config.toml`：

```toml
[system]
worker_mode = "async"
max_workers = 100
queue_size = 10000

[monitoring]
enable_prometheus = true
enable_tracing = false
enable_metrics_api = true
prometheus_host = "127.0.0.1"
prometheus_port = 8000

[api]
metrics_api_host = "127.0.0.1"
metrics_api_port = 8080
```

### 3. 使用示例

```python
import asyncio
from aethelum_core_lite.config import ConfigLoader
from aethelum_core_lite.core import (
    AsyncSynapticQueue,
    AsyncAxonWorker,
    AsyncNeuralSomaRouter
)

async def main():
    # 加载配置
    config = ConfigLoader.load_from_file("config.toml")
    monitoring_config = ConfigLoader.get_monitoring_config(config)

    # 创建Router
    router = AsyncNeuralSomaRouter("my_router")

    # 创建队列
    queue = AsyncSynapticQueue("my_queue", max_size=1000)
    router.register_queue(queue)

    # 添加路由规则
    router.add_routing_rule("my_pattern", "my_queue")

    # 创建Worker
    worker = AsyncAxonWorker("my_worker", input_queue=queue)
    router.register_worker(worker)

    # 启动系统
    await router.start()

    # 发送消息
    await router.route_message({"data": "test"}, "my_pattern")

    # 等待处理
    await asyncio.sleep(1)

    # 查看指标
    metrics = router.get_metrics()
    print(metrics)

    # 停止系统
    await router.stop()

asyncio.run(main())
```

## 组件详解

### AsyncSynapticQueue

异步队列，支持优先级和 WAL 持久化：

```python
from aethelum_core_lite.core.async_queue import AsyncSynapticQueue, MessagePriority

# 创建队列
queue = AsyncSynapticQueue("my_queue", max_size=1000, enable_wal=True)

# 放入消息（支持优先级）
await queue.async_put({"data": "test"}, priority=MessagePriority.HIGH)

# 获取消息
message = await queue.async_get()

# 获取指标
metrics = queue.get_metrics()
print(f"队列大小: {metrics.size}")
print(f"使用率: {metrics.metrics['usage_percent']}%")
```

### AsyncAxonWorker

异步工作器，专为 I/O 密集型场景设计：

```python
from aethelum_core_lite.core.async_worker import AsyncAxonWorker

# 创建Worker
worker = AsyncAxonWorker("my_worker", input_queue=queue)

# 启动
await worker.start()

# 暂停/恢复
await worker.pause()
await worker.resume()

# 停止
await worker.stop()

# 获取统计信息
stats = worker.get_stats()
print(f"处理消息: {stats.processed_messages}")
print(f"健康分数: {stats.health_score}")
```

### AsyncNeuralSomaRouter

异步路由器，管理队列和 Worker：

```python
from aethelum_core_lite.core.async_router import AsyncNeuralSomaRouter

# 创建Router
router = AsyncNeuralSomaRouter("my_router")

# 注册组件
router.register_queue(queue)
router.register_worker(worker)

# 添加路由规则
router.add_routing_rule("pattern", "queue_id")

# 路由消息
await router.route_message({"data": "test"}, "pattern")

# 获取所有指标
metrics = router.get_metrics()
```

## 监控功能

### Prometheus 指标导出

```python
from aethelum_core_lite.monitoring import PrometheusMetricsExporter

# 创建导出器
exporter = PrometheusMetricsExporter(host="127.0.0.1", port=8000)
exporter.start_server()

# 定期导出指标
async def export_loop():
    while True:
        metrics_data = router.get_metrics()
        exporter.export_from_memory(metrics_data)
        await asyncio.sleep(5)

asyncio.create_task(export_loop())
```

访问 http://127.0.0.1:8000/metrics 查看 Prometheus 指标。

### OpenTelemetry 追踪

```python
from aethelum_core_lite.monitoring.tracing import TracingManager

# 创建追踪管理器
tracing = TracingManager(
    service_name="my_service",
    jaeger_host="localhost",
    jaeger_port=6831,
    sample_rate=0.1
)

# 使用追踪
if tracing.should_sample():
    with tracing.start_span("operation_name", key="value"):
        # 执行操作
        pass
```

访问 http://localhost:16686 查看 Jaeger UI。

### 指标查询 API

```python
from aethelum_core_lite.api import MetricsAPIServer

# 创建API服务器
api_server = MetricsAPIServer(
    host="127.0.0.1",
    port=8080,
    router=router
)

# 启动API（在后台线程）
import threading
api_thread = threading.Thread(target=api_server.start, daemon=True)
api_thread.start()
```

API 端点：
- `GET /api/v1/health` - 健康检查
- `GET /api/v1/metrics` - 获取所有指标

访问 http://127.0.0.1:8080/docs 查看 API 文档。

#### API密钥认证（可选）

**⚠️ 安全建议**：
- 默认情况下，API仅监听127.0.0.1，依赖本地网络安全
- 生产环境强烈建议启用API密钥认证
- 不要将API暴露到公网

**启用API密钥认证**：

1. 配置文件设置密钥：
```toml
[api]
metrics_api_host = "127.0.0.1"
metrics_api_port = 8080
api_key = "your-secret-api-key-here-please-change-me"
```

2. 或在代码中设置：
```python
api_server = MetricsAPIServer(
    host="127.0.0.1",
    port=8080,
    router=router,
    api_key="your-secret-api-key-here-please-change-me"
)
```

3. 客户端使用API密钥：
```bash
# 使用Bearer Token
curl -H "Authorization: Bearer your-secret-api-key-here-please-change-me" \
     http://127.0.0.1:8080/api/v1/metrics
```

**安全注意事项**：
- 使用强密码（至少32个随机字符）
- 不要将密钥提交到版本控制系统
- 定期轮换密钥
- 默认监听127.0.0.1，不要修改为0.0.0.0

## 配置选项

### 监控配置场景

**场景1：只启用 Prometheus**
```toml
[monitoring]
enable_prometheus = true
enable_tracing = false
enable_metrics_api = false
```

**场景2：只启用追踪**
```toml
[monitoring]
enable_prometheus = false
enable_tracing = true
enable_metrics_api = false
```

**场景3：Prometheus + API**
```toml
[monitoring]
enable_prometheus = true
enable_tracing = false
enable_metrics_api = true
```

**场景4：全部启用**
```toml
[monitoring]
enable_prometheus = true
enable_tracing = true
enable_metrics_api = true
```

## 性能对比

| 指标 | 多线程模型 | AsyncIO模型 | 提升 |
|------|-----------|-------------|------|
| 并发Agent数 | 100 | 1000+ | 10倍 |
| 响应延迟 | 2-5秒 | 1-3秒 | 30-50% |
| 内存占用 | 8MB/线程 | 几KB/协程 | 60-80% |

## 测试

运行单元测试：

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_async_components.py -v

# 查看覆盖率
pytest tests/ --cov=aethelum_core_lite --cov-report=html
```

## 示例程序

查看完整示例：

```bash
python examples/async_example.py
```

## 常见问题

**Q: 如何从多线程迁移到 AsyncIO？**

A: 直接使用新的 AsyncIO 组件替换原有组件。由于项目还在开发阶段，不需要考虑向后兼容。

**Q: Prometheus 和 API 有什么区别？**

A: Prometheus 用于指标收集和可视化（配合 Grafana），API 提供简单的查询接口。复杂的查询和聚合建议使用 Prometheus。

**Q: 如何禁用监控功能？**

A: 在配置文件中设置 `enable_prometheus = false`、`enable_tracing = false`、`enable_metrics_api = false`。

## 下一步

- 查看完整示例：`examples/async_example.py`
- 阅读 API 文档：http://127.0.0.1:8080/docs（启动 API 后）
- 配置 Grafana 仪表盘
- 集成现有 AI API 和 RAG 组件

# AethelumCoreLite 示例程序

本目录包含了AethelumCoreLite框架的示例程序，帮助您快速了解和使用框架的各种功能。

## 🚀 快速开始

### 主入口程序

最简单的开始方式是运行主入口程序：

```bash
python -m aethelum_core_lite.examples.main
```

主入口程序提供：
- 📋 交互式菜单选择不同示例
- 🎯 非交互模式支持（CI/CD友好）
- 🔄 示例运行后的返回菜单

**注意**：所有示例使用 **Mock AI 服务**，不需要真实 API keys，开箱即用！

### 独立运行示例

您也可以直接运行各个示例：

```bash
# 基础示例（简单演示）
python -m aethelum_core_lite.examples.basic_example

# 高级示例（多Agent、Hook、性能监控）
python -m aethelum_core_lite.examples.advanced_example

# 单消息示例（等待响应完成）
python -m aethelum_core_lite.examples.single_example

# 内容安全审查示例（完整审核流程）
python -m aethelum_core_lite.examples.moral_audit_example

# 批量处理示例
python -m aethelum_core_lite.examples.batch_processing_example

# 自定义Hook示例
python -m aethelum_core_lite.examples.custom_hook_example

# 性能演示
python -m aethelum_core_lite.examples.performance_demo
```

### 非交互模式（CI/CD）

```bash
# 设置环境变量启用非交互模式
export AETHELUM_NONINTERACTIVE=1

# 或在 CI 环境中自动启用
export CI=1

# 运行示例（不会阻塞等待输入）
python -m aethelum_core_lite.examples.main
```

## 📋 示例说明

### 1. 基础示例 (`basic_example.py`)

**功能演示：**
- 模拟树神经系统的通信框架的基本使用
- 神经脉冲消息传递
- 队列管理和 Worker 处理
- 并发消息处理
- 自动响应收集

**适用场景：**
- 初次接触框架
- 理解基本架构
- 学习核心概念

**前置要求：**
- ✅ 无需配置（使用 Mock AI）

---

### 2. 高级示例 (`advanced_example.py`)

**功能演示：**
- 多个业务 Agent 协同工作
- 优先级队列处理
- 自定义 Hook 机制
- 性能监控和指标收集
- 错误处理和重试机制
- 批量消息处理

**适用场景：**
- 生产环境集成参考
- 学习高级特性
- 性能测试和优化

**前置要求：**
- ✅ 无需配置（使用 Mock AI）

---

### 3. 单消息示例 (`single_example.py`)

**功能演示：**
- 简单的端到端流程
- 等待响应完成
- 基本的消息处理流程
- 内容审核集成

**适用场景：**
- 理解完整流程
- 测试基本功能
- 学习审核机制

**前置要求：**
- ✅ 无需配置（使用 Mock AI）

---

### 4. 内容安全审查示例 (`moral_audit_example.py`)

**功能演示：**
- 完整的审核流程实现（输入审核和输出审核）
- 智能违规类型识别
- 自动拒绝回复生成
- 多线程并发审查
- 审查统计和性能分析

**适用场景：**
- 了解审核流程实现
- 学习内容审查
- 测试安全特性

**前置要求：**
- ✅ 无需配置（使用 Mock AI）

**注意：** 此示例展示的是可选的审核流程，不是框架的强制要求

---

### 5. 批量处理示例 (`batch_processing_example.py`)

**功能演示：**
- 批量消息发送
- 并发处理优化
- 进度跟踪
- 结果汇总和统计

**适用场景：**
- 大规模数据处理
- 批量任务调度
- 性能基准测试

---

### 6. 自定义Hook示例 (`custom_hook_example.py`)

**功能演示：**
- Logging Hook - 详细日志
- Validation Hook - 数据验证
- Transform Hook - 内容转换
- Cache Hook - 结果缓存
- Metrics Hook - 指标收集

**适用场景：**
- 学习 Hook 开发
- 自定义扩展功能
- 集成监控系统

---

### 7. 性能演示 (`performance_demo.py`)

**功能演示：**
- 吞吐量测试
- 并发性能测试
- 延迟分析
- 资源使用监控

**适用场景：**
- 性能基准测试
- 容量规划
- 瓶颈分析

---

## 核心概念说明

### 神经脉冲 (NeuralImpulse)

神经脉冲是在系统中传递的信息包，包含：
- `session_id`: 会话唯一标识
- `action_intent`: 下一个处理队列（路由键）
- `source_agent`: 上一个处理 Agent
- `input_source`: 消息来源（USER, API, SYSTEM 等）
- `content`: 消息内容
- `metadata`: 元数据字典
- `routing_history`: 路由历史记录

### 突触队列 (SynapticQueue)

突触队列是神经元间的连接点，基于 Python `queue.Queue` 实现：
- 线程安全的优先级队列
- 支持容量限制和统计信息
- 自动添加队列元数据
- 可选的 WAL 持久化

### 轴突工作器 (AxonWorker)

轴突工作器是处理神经信号的线程：
- 持续消费队列中的神经脉冲
- 执行注册的 Hook 函数
- 包含基本的响应处理机制
- 提供详细的统计信息

### 神经胞体路由器 (NeuralSomaRouter)

神经胞体路由器是整个系统的核心：
- 管理队列和工作器的生命周期
- 提供 `auto_setup()` 方法自动配置系统
- 支持灵活的消息路由流程
- 允许自定义业务逻辑处理

---

## Mock AI 服务

所有示例使用 `MockAIClient`，不依赖真实 API：

### 特性

- ✅ 模拟审核结果（基于内容长度判断安全性）
- ✅ 模拟处理延迟（可配置）
- ✅ 模拟响应生成
- ✅ 统计信息收集

### 使用示例

```python
from aethelum_core_lite.examples.mock_ai_service import MockAIClient

# 创建 Mock 客户端
mock_ai = MockAIClient(response_delay=0.05)

# 内容审核
audit_result = mock_ai.audit_content("测试内容")
# 返回: {"safe": True, "result": "审核通过", "confidence": 0.95, ...}

# 内容处理
process_result = mock_ai.process_content("输入内容")
# 返回: {"success": True, "result": "已处理您的请求", ...}

# 对话补全
response = mock_ai.chat_completion([{"role": "user", "content": "你好"}])
# 返回: "您好！很高兴为您服务..."

# 获取统计
stats = mock_ai.get_stats()
# 返回: {"total_requests": 10, "avg_delay": 0.05, ...}
```

### 集成真实 AI 服务（可选）

如需使用真实 AI 服务，可以轻松替换 Mock AI：

```python
# 替换为真实客户端
from openai import OpenAI

class RealAIClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def audit_content(self, content: str) -> dict:
        # 调用真实 API
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": f"审核: {content}"}]
        )
        return {"safe": True, "result": response.choices[0].message.content}
```

---

## 安全流程设计

AethelumCoreLite 提供灵活的消息处理流程，支持可选的安全审核：

**标准流程**:
```
用户输入 → Q_PROCESS_INPUT → [业务处理] → Q_RESPONSE_SINK → 用户响应
```

**可选审核流程**:
```
用户输入 → Q_AUDIT_INPUT → Q_AUDITED_INPUT → [业务处理] → Q_AUDIT_OUTPUT → Q_RESPONSE_SINK → 用户响应
```

**流程特性**:
1. **灵活路由**: 支持自定义消息路由和处理流程
2. **可选审核**: 提供审核流程示例，可根据需要启用
3. **标准处理**: 默认使用简化的标准处理流程
4. **自定义扩展**: 支持注册自定义 Hook 实现特定需求

---

## 树神经体系命名

整个框架采用生物学命名概念：

| 组件 | 生物学概念 | 功能描述 |
|------|------------|----------|
| NeuralSomaRouter | 神经胞体 | 整合和分发神经信号 |
| SynapticQueue | 突触 | 神经元间的连接点 |
| AxonWorker | 轴突 | 传递神经信号的纤维 |
| NeuralImpulse | 神经脉冲 | 神经元间的信息单位 |

---

## 扩展开发

### 创建自定义 Hook

```python
from aethelum_core_lite.hooks.base_hook import BaseHook

class MyCustomHook(BaseHook):
    def __init__(self, hook_name: str):
        super().__init__(hook_name)

    def process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        # 自定义处理逻辑
        impulse.metadata['processed_by'] = 'MyCustomHook'
        return impulse

# 注册 Hook
router.register_hook("MY_QUEUE", "pre_process", MyCustomHook("MyHook").process)
```

### 实现业务 Agent

```python
def my_business_logic(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
    # 处理业务逻辑
    response = process_user_input(impulse.content)
    impulse.set_text_content(response)

    # 路由到下一步
    impulse.reroute_to("Q_RESPONSE_SINK")
    impulse.update_source("MyBusinessAgent")

    return impulse

# 注册业务逻辑
router.register_hook("Q_AUDITED_INPUT", "pre_process", my_business_logic)
```

---

## 最佳实践

1. **灵活性**: 根据需求选择合适的消息处理流程
2. **错误处理**: 在 Hook 中实现适当的错误处理
3. **性能监控**: 利用统计信息监控系统性能
4. **资源管理**: 适当配置工作器数量和队列大小
5. **日志记录**: 启用适当的日志记录以便调试
6. **线程安全**: 使用锁保护共享数据

---

## 故障排除

### 常见问题

1. **示例运行失败**
   - 确保已安装所有依赖：`pip install -r requirements/base.txt`
   - 检查 Python 版本（需要 3.8+）

2. **消息丢失**
   - 检查 Hook 函数是否返回了 NeuralImpulse 对象
   - 确认工作器是否正常启动

3. **性能问题**
   - 调整工作器数量
   - 检查队列是否积压过多消息
   - 优化 Hook 函数的执行时间

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看统计信息
stats = router.get_stats()
print(stats)

# 检查队列状态
queue_sizes = router.get_queue_sizes()
print(queue_sizes)
```

---

## 更多资源

- [主 README](../../README.md)
- [设计文档](../../AethelumCoreLite_v0.1.md)
- [API 文档](../core/)
- [工具函数](../utils/)

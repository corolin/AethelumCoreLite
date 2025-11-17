# Aethelum Core Lite 示例程序

本目录包含了Aethelum Core Lite框架的示例程序，帮助您快速了解和使用框架的各种功能。

## 🚀 快速开始

### 主入口程序

最简单的开始方式是运行主入口程序：

```bash
python -m aethelum_core_lite.examples.main
```

主入口程序提供：
- 📋 交互式菜单选择不同示例
- ⚙️ OpenAI客户端代码配置
- 📊 配置状态检查
- 🔄 示例运行后的返回菜单

### OpenAI配置方法

运行主入口程序并选择选项4，程序会检测配置状态。如果未配置，会提示您按以下方法配置：

**🔧 方法1: 使用配置文件（推荐）**
1. 复制 `config_template.py` 为 `config.py`
2. 在 `config.py` 中填写您的API密钥
3. 重新运行程序

**🔧 方法2: 直接编辑代码**
1. 编辑 `aethelum_core_lite/examples/main.py` 文件
2. 找到 `api_key=""` 这一行
3. 填写您的OpenAI API密钥：`api_key="sk-your-api-key-here"`
4. 重新运行程序

💡 **获取API密钥**: https://platform.openai.com/api-keys

### 独立运行示例

如果您已经配置好OpenAI客户端并编译了ProtoBuf，也可以直接运行各个示例：

```bash
# 基础示例（简单演示）
python -m aethelum_core_lite.examples.basic_example

# 内容安全审查示例
python -m aethelum_core_lite.examples.moral_audit_example

# 高级多线程示例
python -m aethelum_core_lite.examples.advanced_example

# 单消息示例
python -m aethelum_core_lite.examples.single_example
```

## 📋 示例说明

### 1. 基础示例 (`basic_example.py`)

**功能演示：**
- 模拟树神经系统的通信框架的基本使用
- 强制性安全队列概念
- 简单的消息传递流程
- Agent工作原理展示

**适用场景：**
- 初次接触框架
- 理解基本架构
- 学习核心概念

**前置要求：**
- ✅ OpenAI客户端配置

### 2. 内容安全审查示例 (`moral_audit_example.py`)

**功能演示：**
- 基础的内容安全审查流程
- AI驱动的智能内容检测
- 违规类型的自动识别
- 智能拒绝回复生成

**适用场景：**
- 了解框架基本概念
- 学习内容审查流程
- 测试OpenAI集成

**前置要求：**
- ✅ OpenAI客户端配置
- ✅ OpenAI API密钥

### 3. 高级多线程示例 (`advanced_example.py`)

**功能演示：**
- 多个业务Agent协同工作
- 并发LLM处理模拟
- 性能监控和指标收集
- RAG增强处理
- 自动响应收集和排序
- 高级并发特性

**适用场景：**
- 生产环境集成参考
- 学习多线程处理
- 了解完整安全流程
- 性能测试

**前置要求：**
- ✅ OpenAI客户端配置
- ✅ OpenAI API密钥
- ✅ ProtoBuf编译（protobuf_schema.proto）

### 4. 单消息示例 (`single_example.py`)

**功能演示：**
- 简单的端到端流程
- 等待响应完成
- 完整的内容安全审查流程
- 简化的业务逻辑

**适用场景：**
- 初次接触框架
- 理解基本架构
- 学习核心概念
- 测试基本功能

**前置要求：**
- ✅ OpenAI客户端配置
- ✅ OpenAI API密钥

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
- 线程安全的 FIFO 队列
- 支持容量限制和统计信息
- 自动添加队列元数据

### 轴突工作器 (AxonWorker)

轴突工作器是处理神经信号的线程：
- 持续消费队列中的神经脉冲
- 执行注册的 Hook 函数
- 包含强制性的 SINK 安全校验
- 提供详细的统计信息

### 神经胞体路由器 (NeuralSomaRouter)

神经胞体路由器是整个系统的核心：
- 管理队列和工作器的生命周期
- 提供 `activate()` 方法激活整个神经系统
- 强制执行安全审计流程
- 禁止向安全队列注册自定义 Hook

## 安全流程设计

AethelumCoreLite 强制执行以下安全流程：

```
用户输入 → Q_AUDIT_INPUT → Q_AUDITED_INPUT → [业务处理] → Q_AUDIT_OUTPUT → Q_RESPONSE_SINK → 用户响应
```

**关键安全特性**:
1. **输入审查**: 所有用户输入必须经过 Q_AUDIT_INPUT 队列
2. **输出审查**: 所有输出必须经过 Q_AUDIT_OUTPUT 队列
3. **SINK 校验**: Q_RESPONSE_SINK 工作器会严格验证消息来源
4. **Hook 限制**: 禁止向 Q_AUDIT_INPUT 和 Q_AUDIT_OUTPUT 注册自定义 Hook

## 树神经体系命名

整个框架采用生物学命名概念：

| 组件 | 生物学概念 | 功能描述 |
|------|------------|----------|
| NeuralSomaRouter | 神经胞体 | 整合和分发神经信号 |
| SynapticQueue | 突触 | 神经元间的连接点 |
| AxonWorker | 轴突 | 传递神经信号的纤维 |
| NeuralImpulse | 神经脉冲 | 神经元间的信息单位 |

## 扩展开发

### 创建自定义 Hook

```python
from aethelum_core_lite.hooks.base_hook import BaseHook

class MyCustomHook(BaseHook):
    def process(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        # 自定义处理逻辑
        impulse.metadata['processed_by'] = 'MyCustomHook'
        return impulse

# 注册 Hook
router.register_hook("MY_QUEUE", MyCustomHook("MyHook").process)
```

### 实现业务 Agent

```python
def my_business_logic(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
    # 处理业务逻辑
    response = process_user_input(impulse.content)
    impulse.content = response

    # 路由到下一步
    impulse.reroute_to("Q_AUDIT_OUTPUT")
    impulse.update_source("MyBusinessAgent")

    return impulse

# 注册业务逻辑
router.register_hook("Q_AUDITED_INPUT", my_business_logic)
```

## 最佳实践

1. **安全性**: 始终确保消息经过完整的审查流程
2. **错误处理**: 在 Hook 中实现适当的错误处理
3. **性能监控**: 利用统计信息监控系统性能
4. **资源管理**: 适当配置工作器数量和队列大小
5. **日志记录**: 启用适当的日志记录以便调试

## 故障排除

### 常见问题

1. **路由器激活失败**
   - 检查是否创建了 Q_RESPONSE_SINK 队列
   - 确保所有强制性队列都已创建

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

## 更多资源

- [设计文档](../../AethelumCoreLite_v1.0.md)
- [API 文档](../core/)
- [工具函数](../utils/)
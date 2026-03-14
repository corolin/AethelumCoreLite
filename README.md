# Aethelum Core Lite - 灵壤精核

> 模拟树神经的异步通信框架

AethelumCoreLite 将"树神经"概念引入现代 JavaScript 异步编程，构建了一套基于事件循环的高性能消息处理架构。

## 特性

- 🧠 **树神经架构**: 基于生物树神经概念的通信框架
- ⚡ **极致性能**: 基于 Bun 的事件循环，零拷贝消息传递
- 💾 **异步优先**: 完全基于 Promise/async-await 的异步架构
- 🔒 **类型安全**: 端到端 TypeScript 支持，完整类型推导
- 🛡️ **健康监控**: 内置 Worker 健康评分与自动熔断恢复
- 🔗 **钩子系统**: 支持前置/后置/错误/转换/过滤等多种钩子
- 📝 **WAL 持久化**: Write-Ahead Logging 日志写入，支持数据恢复
- ✅ **统一验证**: 多级验证框架，支持分级结果（INFO/WARNING/ERROR/CRITICAL）
- 🔄 **自我优化**: 内置自我精炼分析器与合并器
- 📊 **指标 API**: 内置监控指标接口
- 🚀 **跨平台**: 支持 Bun 和 Node.js 运行时

## 安装

### 基础安装

```bash
# 使用 Bun（推荐）
bun add file:../path/to/AethelumCoreLite

# 或使用 npm
npm install ../path/to/AethelumCoreLite
```

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/corolin/AethelumCoreLite.git
cd AethelumCoreLite

# 安装依赖
bun install

# 类型检查
bun run typecheck
```

## 项目结构

```
src/
├── core/                   # 核心模块
│   ├── router.ts           # 路由器（神经胞体）
│   ├── message.ts          # 神经脉冲消息定义
│   ├── queue.ts            # 异步突触队列
│   ├── worker.ts           # 轴突工作器
│   ├── monitor.ts          # 工作器监控器
│   ├── error_handler.ts    # 错误处理器
│   └── self-refining/      # 自我优化模块
│       ├── analyzer.ts     # 精炼分析器
│       ├── merger.ts       # 精炼合并器
│       └── worker.ts       # 自我优化工作器
├── hooks/                  # 钩子系统
│   ├── chain.ts            # 钩子链管理
│   └── types.ts            # 钩子类型定义
├── utils/                  # 工具模块
│   ├── unified_validator.ts    # 统一验证框架
│   ├── wal_writer.ts       # WAL 写入器
│   ├── logger.ts           # 日志器
│   ├── structured_logger.ts    # 结构化日志
│   ├── payload_store.ts    # 负载存储
│   └── log_analytics.ts    # 日志分析
├── api/                    # API 模块
│   └── metrics_api.ts      # 指标 API
├── config/                 # 配置模块
│   └── config_loader.ts    # 配置加载器
├── prompts/                # 提示词模块
│   └── moral_audit_prompts.ts  # 道德审计提示词
└── types/                  # 全局类型定义
```

## 核心概念

### 神经脉冲 (NeuralImpulse)

在神经元间传递的信息包，包含：
- `sessionId`: 会话ID
- `actionIntent`: 路由目标
- `sourceAgent`: 消息来源
- `inputSource`: 输入来源类型
- `content`: 消息内容
- `metadata`: 元数据（可扩展）
- `priority`: 消息优先级
- `expiresAt`: 过期时间

### 神经元组件

#### CoreLiteRouter (神经胞体路由器)

主控制器，管理队列和工作器：

```typescript
import { CoreLiteRouter, NeuralImpulse } from 'aethelum-core-lite/core';

// 创建路由器
const router = new CoreLiteRouter();

// 注册队列
router.registerQueue("Q_PROCESS", new AsyncSynapticQueue("Q_PROCESS"));
router.registerQueue("Q_RESPONSE", new AsyncSynapticQueue("Q_RESPONSE"));

// 路由消息
const impulse = new NeuralImpulse({
    sessionId: "user-123",
    actionIntent: "Q_PROCESS",
    sourceAgent: "HTTPGateway",
    inputSource: "HTTP",
    content: "Hello, World!",
    metadata: {}
});

await router.routeMessage(impulse, "Q_PROCESS");
```

路由器内置系统队列：`Q_AUDIT_INPUT`、`Q_AUDIT_OUTPUT`、`Q_RESPONSE_SINK`、`Q_ERROR`、`Q_DONE`、`Q_REFLECTION`，并提供动态队列创建与安全路由机制。

#### AsyncSynapticQueue (突触队列)

高性能异步队列，支持优先级和超时获取：

```typescript
import { AsyncSynapticQueue } from 'aethelum-core-lite/core';

// 创建队列
const queue = new AsyncSynapticQueue("my_queue");

// 生产消息
await queue.asyncPut(impulse);

// 消费消息（支持超时）
const message = await queue.asyncGet(1000); // 1秒超时

// 带优先级的消息（5级：CRITICAL / HIGH / NORMAL / LOW / BACKGROUND）
await queue.asyncPut(impulse, 5); // priority = 5
```

队列支持 WAL 日志持久化，确保消息可恢复。

#### AsyncAxonWorker (轴突工作器)

异步消息处理单元，内置钩子集成：

```typescript
import { AsyncAxonWorker } from 'aethelum-core-lite/core';

class MyWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        // 处理消息逻辑
        console.log(`Processing: ${impulse.content}`);

        // 路由到下一个队列
        await this.routeAndDone(impulse, "Q_RESPONSE");
    }
}

// 创建并启动 Worker
const worker = new MyWorker("my-worker", inputQueue, router);
await worker.start();
```

#### AsyncWorkerMonitor (工作器监控器)

健康监控与自动熔断：

```typescript
import { AsyncWorkerMonitor } from 'aethelum-core-lite/core';

const monitor = new AsyncWorkerMonitor({
    checkIntervalMs: 5000,      // 健康检查间隔
    errorThreshold: 3,          // 连续错误阈值
    timeoutMs: 30000,           // 超时判定阈值
    autoRecovery: true,         // 启用自动恢复
    recoveryDelayMs: 10000      // 恢复延迟
});

monitor.registerWorker(worker);
monitor.start();

// 获取健康状态
const metrics = monitor.getGlobalMetrics();
console.log(metrics);
```

## 钩子系统

框架内置灵活的钩子机制，支持在消息处理的不同阶段插入自定义逻辑：

```typescript
// 支持的钩子类型
enum HookType {
    PRE_PROCESS = "PRE_PROCESS",       // 前置处理
    POST_PROCESS = "POST_PROCESS",     // 后置处理
    ERROR_HANDLER = "ERROR_HANDLER",   // 错误处理
    TRANSFORM = "TRANSFORM",           // 消息转换
    FILTER = "FILTER"                  // 消息过滤
}
```

钩子链支持：
- 优先级排序执行
- 超时控制
- 信号机制（中断/继续）
- 动态启用/禁用

## 快速开始

```typescript
import { CoreLiteRouter, AsyncSynapticQueue, AsyncAxonWorker, AsyncWorkerMonitor } from 'aethelum-core-lite/core';
import { NeuralImpulse } from 'aethelum-core-lite/core';

// 1. 创建路由器
const router = new CoreLiteRouter();
const inputQueue = new AsyncSynapticQueue("Q_PROCESS");
const outputQueue = new AsyncSynapticQueue("Q_RESPONSE");

router.registerQueue("Q_PROCESS", inputQueue);
router.registerQueue("Q_RESPONSE", outputQueue);

// 2. 定义 Worker
class EchoWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        const response = `Echo: ${impulse.content}`;
        impulse.content = response;
        await this.routeAndDone(impulse, "Q_RESPONSE");
    }
}

// 3. 创建并启动 Worker
const worker = new EchoWorker("echo-worker", inputQueue, router);
await worker.start();

// 4. 配置监控
const monitor = new AsyncWorkerMonitor();
monitor.registerWorker(worker);
monitor.start();

// 5. 发送消息
const impulse = new NeuralImpulse({
    sessionId: "test-session",
    actionIntent: "Q_PROCESS",
    sourceAgent: "User",
    inputSource: "CLI",
    content: "Hello, Aethelum!"
});

await router.routeMessage(impulse, "Q_PROCESS");

// 6. 消费响应
const response = await outputQueue.asyncGet(1000);
console.log(response.content); // "Echo: Hello, Aethelum!"
```

## 工具模块

### 统一验证器 (UnifiedValidator)

多级验证框架，支持扩展多种验证器，验证结果分级：

```typescript
// 验证结果级别：INFO → WARNING → ERROR → CRITICAL
```

### WAL 写入器 (ImprovedWALWriter)

Write-Ahead Logging 实现，为队列消息提供崩溃恢复能力。WAL 作为"临时保险箱"，确保进程崩溃后在途消息不丢失。

**双日志结构（参考数据库 WAL 设计）**：

```
消息入队 → Log1（数据日志，消息入当前队列之前落盘）
          ↓
     Worker 处理
          ↓
消息移交 → Log2（确认日志，消息成功进入下一队列后，对来源队列确认）
```

**核心保证**：任意时刻只有一个队列认为某条消息是"未消费"的。崩溃只会重放"尚未完成移交"的消息。

**关键语义**：
- **Log1**：`queue.asyncPut()` 调用时写入，消息入队前先落盘
- **Log2**：`router.routeMessage()` 成功将消息放入目标队列后，对来源队列调用 `queue.confirmDelivery()` 写入
- **崩溃恢复**：进程重启时，`queue` 构造函数自动扫描 WAL 段文件，回放 `lsn > committedLsn` 的未提交条目到队列
- **终端队列**（Q_RESPONSE_SINK）：不需要 WAL，是消息的最终归宿

**存储结构**：
```
wal_data_v2/
└── {queueId}/
    ├── tracker.ptr          # 已提交的 LSN 位点（原子重命名写入）
    ├── log1_000000.wal      # WAL 段文件（每段最大 100MB）
    └── log1_000001.wal      # 自动轮转
```

**WAL 记录格式**：`LSN|CHECKSUM|PAYLOAD_LENGTH|PAYLOAD\n`

**初始化与恢复时序**：
1. `queue` 构造函数异步启动 WAL 初始化 + 恢复
2. `asyncPut()` 中的 `await walReady` 确保恢复完成前新消息不入队
3. Workers 启动后轮询队列，恢复的消息会被正常消费

### 结构化日志

内置结构化日志系统，支持日志分析和性能监控。

## 健康监控与容错

### 健康评分系统

每个 Worker 维护一个 0-100 的健康分数：

| 事件 | 分数变化 |
|------|---------|
| 启动 | +100 |
| 每次错误 | -20 |
| 超时检测 | -50（仅一次）|
| 正常运行恢复 | +5/周期 |

### 熔断机制

当满足以下条件时触发熔断：
- 连续错误次数 ≥ `errorThreshold`
- 健康分数 ≤ 20

```typescript
// 熔断后的行为：
// 1. Worker 状态被设置为 ERROR
// 2. 停止处理新消息
// 3. 如果 autoRecovery = true，延迟后自动重启
```

### 自动恢复

```typescript
const monitor = new AsyncWorkerMonitor({
    autoRecovery: true,
    recoveryDelayMs: 10000
});

// 恢复流程：
// 1. 重置连续错误计数
// 2. 恢复健康分数到 80
// 3. 调用 worker.start() 重新启动
```

## 并发安全性

AethelumCoreLite 基于 JavaScript 事件循环，天然避免多线程竞争：

- **AsyncSynapticQueue**: Promise 链确保操作顺序，无锁设计
- **AsyncWorkerMonitor**: Map 数据结构保护，返回数据副本防止外部修改
- **AsyncAxonWorker**: 状态转换原子性，process() 方法串行执行

## 性能考虑

- **事件循环**: 单线程避免锁竞争
- **零拷贝**: NeuralImpulse 引用传递
- **优先级队列**: 5 级优先级确保关键消息优先处理
- **WAL 持久化**: 异步写入，不阻塞主流程

## 技术栈

| 组件 | 技术 |
|------|------|
| **运行时** | Bun / Node.js |
| **语言** | TypeScript 5.9+ |
| **模块系统** | ESM (nodenext) |
| **序列化** | JSON |
| **验证** | Zod |
| **Web 框架** | Hono |
| **UUID** | uuid v7 |

## 开发

```bash
# 运行测试
bun test

# 类型检查
bun run typecheck

# 代码格式化
bun run lint
```

## License

ISC

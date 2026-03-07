# Aethelum Core Lite - 灵壤精核 (Bun/Node.js)

> 模拟树神经的通信框架 - TypeScript 复刻版

AethelumCoreLite 是 Python 版本的 TypeScript/Bun 复刻，保持了相同的架构设计理念，将"树神经"概念引入现代 JavaScript 异步编程。

## 特性

- 🧠 **树神经架构**: 基于生物树神经概念的通信框架
- ⚡ **极致性能**: 基于 Bun 的事件循环，零拷贝消息传递
- 💾 **异步优先**: 完全基于 Promise/async-await 的异步架构
- 🔒 **类型安全**: 端到端 TypeScript 支持，完整类型推导
- 🛡️ **健康监控**: 内置 Worker 健康评分与自动熔断恢复
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

## 核心概念

### 神经脉冲 (NeuralImpulse)

在神经元间传递的信息包，包含：
- `sessionId`: 会话ID
- `actionIntent`: 路由目标
- `sourceAgent`: 消息来源
- `content`: 消息内容
- `metadata`: 元数据（可扩展）

### 神经元组件

#### NeuralSomaRouter (神经胞体路由器)

主控制器，管理队列和工作器：

```typescript
import { NeuralSomaRouter, NeuralImpulse } from 'aethelumcorelite-nodejs/core';

// 创建路由器
const router = new NeuralSomaRouter();

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

#### AsyncSynapticQueue (突触队列)

高性能异步队列，支持超时获取：

```typescript
import { AsyncSynapticQueue } from 'aethelumcorelite-nodejs/core';

// 创建队列
const queue = new AsyncSynapticQueue("my_queue");

// 生产消息
await queue.asyncPut(impulse);

// 消费消息（支持超时）
const message = await queue.asyncGet(1000); // 1秒超时

// 带优先级的消息
await queue.asyncPut(impulse, 5); // priority = 5
```

#### AsyncAxonWorker (轴突工作器)

异步消息处理单元：

```typescript
import { AsyncAxonWorker, WorkerState } from 'aethelumcorelite-nodejs/core';

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
import { AsyncWorkerMonitor } from 'aethelumcorelite-nodejs/core';

const monitor = new AsyncWorkerMonitor({
    checkIntervalMs: 5000,      // 健康检查间隔
    errorThreshold: 3,          // 连续错误阈值
    timeoutMs: 30000,           // 超时判定阈值
    autoRecovery: true,         // 启用自动恢复
    recoveryDelayMs: 10000      // 恢复延迟
});

// 注册 Worker
monitor.registerWorker(worker);

// 启动监控
monitor.start();

// 获取健康状态
const metrics = monitor.getGlobalMetrics();
console.log(metrics);
```

### Worker 状态管理

```typescript
enum WorkerState {
    IDLE = "IDLE",           // 空闲
    RUNNING = "RUNNING",     // 运行中
    PAUSED = "PAUSED",       // 暂停
    ERROR = "ERROR",         // 错误/熔断
    STOPPED = "STOPPED"      // 已停止
}
```

## 快速开始

### 基础使用示例

```typescript
import { NeuralSomaRouter, AsyncSynapticQueue, AsyncAxonWorker, AsyncWorkerMonitor } from 'aethelumcorelite-nodejs/core';
import { NeuralImpulse } from 'aethelumcorelite-nodejs/core';

// 1. 创建路由器
const router = new NeuralSomaRouter();
const inputQueue = new AsyncSynapticQueue("Q_PROCESS");
const outputQueue = new AsyncSynapticQueue("Q_RESPONSE");

router.registerQueue("Q_PROCESS", inputQueue);
router.registerQueue("Q_RESPONSE", outputQueue);

// 2. 定义 Worker
class EchoWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        // 处理业务逻辑
        const response = `Echo: ${impulse.content}`;
        impulse.content = response;

        // 路由到响应队列
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
// 熔断后的行为
// 1. Worker 状态被设置为 ERROR
// 2. 停止处理新消息
// 3. 如果 autoRecovery = true，延迟后自动重启
```

### 自动恢复

```typescript
// 启用自动恢复（推荐）
const monitor = new AsyncWorkerMonitor({
    autoRecovery: true,
    recoveryDelayMs: 10000  // 给外部10秒修复时间
});

// 恢复流程：
// 1. 重置连续错误计数
// 2. 恢复健康分数到 80
// 3. 调用 worker.start() 重新启动
```

## 并发安全性

### 异步安全保证

AethelumCoreLite 基于 JavaScript 事件循环，天然避免多线程竞争：

#### ✅ 已保护的组件

1. **AsyncSynapticQueue (突触队列)**
   - 使用 Promise 链确保操作顺序
   - asyncPut/asyncGet 原子性保证
   - 无锁设计，利用事件循环单线程特性

2. **AsyncWorkerMonitor (工作器监控器)**
   - Map 数据结构保护
   - 定时检查与 Worker 操作分离
   - 返回数据副本防止外部修改

3. **AsyncAxonWorker (轴突工作器)**
   - 状态转换原子性
   - 健康统计线程安全
   - process() 方法串行执行

### 使用最佳实践

#### ✅ 推荐做法

```typescript
// 1. 使用 async/await 确保操作顺序
async function safeOperation() {
    await queue.asyncPut(impulse);
    const result = await queue.asyncGet();
    return result;
}

// 2. 避免 Promise.all 中的竞争
// ❌ 可能乱序
await Promise.all([
    queue.asyncPut(impulse1),
    queue.asyncPut(impulse2)
]);

// ✅ 保证顺序
await queue.asyncPut(impulse1);
await queue.asyncPut(impulse2);

// 3. 错误处理
try {
    await worker.start();
} catch (error) {
    console.error('Worker failed to start:', error);
    // 实现回退逻辑
}
```

#### ❌ 常见陷阱

```typescript
// 1. 忘记 await
queue.asyncPut(impulse); // ❌ 消息可能未发送
await queue.asyncPut(impulse); // ✅

// 2. 混用回调与 Promise
queue.asyncPut(impulse).then(() => {
    // 嵌套回调地狱
    queue.asyncGet().then(result => {
        // ...
    });
});

// ✅ 使用 async/await
await queue.asyncPut(impulse);
const result = await queue.asyncGet();

// 3. 阻塞事件循环
function bad() {
    while (true) { // ❌ 阻塞整个事件循环
        // CPU 密集操作
    }
}

// ✅ 使用 Worker 线程或分片处理
async function good() {
    for (const chunk of data) {
        await processChunk(chunk);
        await new Promise(r => setImmediate(r)); // 让出控制
    }
}
```

## 性能考虑

- **事件循环**: 单线程避免锁竞争
- **零拷贝**: NeuralImpulse 引用传递
- **队列复用**: 使用对象池减少 GC
- **背压控制**: 队列满时的背压策略

## 开发

### 运行测试

```bash
bun test
```

### 类型检查

```bash
bun run typecheck
```

### 代码格式化

```bash
bun run lint
```

## 故障排查

### Worker 假死

**症状**: Worker 状态为 RUNNING 但长时间无响应

**原因**: process() 方法中有阻塞操作或死循环

**解决方案**:
```typescript
// ❌ 阻塞操作
protected async process(impulse: NeuralImpulse): Promise<void> {
    while (true) {  // 死循环
        // ...
    }
}

// ✅ 添加退出条件
protected async process(impulse: NeuralImpulse): Promise<void> {
    let attempts = 0;
    while (attempts < 3) {
        const result = await this.tryOperation();
        if (result.success) break;
        attempts++;
    }
}
```

### 内存泄漏

**症状**: 内存使用持续增长

**原因**: 未清理的事件监听器或定时器

**解决方案**:
```typescript
class MyWorker extends AsyncAxonWorker {
    private timers: NodeJS.Timeout[] = [];

    protected async process(impulse: NeuralImpulse): Promise<void> {
        const timer = setInterval(() => {
            // 定期任务
        }, 1000);
        this.timers.push(timer);
    }

    async stop(): Promise<void> {
        // 清理定时器
        for (const timer of this.timers) {
            clearInterval(timer);
        }
        this.timers = [];
        await super.stop();
    }
}
```

### 队列阻塞

**症状**: asyncGet 长时间等待

**原因**: 消费者处理速度慢于生产者

**解决方案**:
```typescript
// 增加消费者数量
const workers = [
    new Worker("worker-1", queue, router),
    new Worker("worker-2", queue, router),
    new Worker("worker-3", queue, router)
];

// 或设置队列大小限制
const queue = new AsyncSynapticQueue("bounded", {
    maxSize: 1000  // 超过 1000 条时背压
});
```

## 技术栈

| 组件 | 技术 |
|------|------|
| **运行时** | Bun / Node.js |
| **语言** | TypeScript 5.9+ |
| **序列化** | JSON |
| **验证** | Zod |
| **Web 框架** | Hono (用于 HTTP 相关组件) |

## 与 Python 版本的差异

| 特性 | Python 版 | Bun/Node.js 版 |
|------|-----------|----------------|
| 并发模型 | 多线程 | 事件循环 |
| 持久化 | WAL + msgpack | 计划中 |
| 类型系统 | 类型注解 | 完整 TypeScript |
| 性能特点 | GIL 限制 | 单线程极高性能 |
| 部署 | 需要 Python 环境 | 单一二进制 |

## 相关项目

- [Aethelum-Nexus](../Aethelum-Nexus) - 基于 AethelumCoreLite 的完整网关系统

## License

ISC

# Aethelum Core Lite - 灵壤精核

> 模拟树神经的异步通信框架

AethelumCoreLite 将"树神经"概念引入现代 JavaScript 异步编程，构建了一套基于事件循环的高性能消息处理架构。

## 特性

- 🧠 **树神经架构**: 基于生物树神经概念的通信框架（Agent 的神经系统：Agent 是上层实体，框架只保证脉冲“该拿到的不丢、该传递的传递、账目能对上”）
- ⚡ **极致性能**: 基于 Bun/Node.js 的事件循环，零拷贝消息传递
- 💾 **异步优先**: 完全基于 Promise/async-await 的异步架构
- 🔒 **类型安全**: 端到端 TypeScript 支持，完整类型推导
- 🛡️ **健康监控**: 内置 Worker 健康评分与自动熔断恢复
- 🔗 **插件化钩子**: Hook Plugin Registry，声明式组装前置/后置/错误钩子；1.1 起支持**旁路发射**（`context.emit` fan-out）与**尽力而为**（`bestEffort` 失败不中断）
- 📝 **WAL 持久化**: Write-Ahead Logging，支持崩溃恢复，以 Hook 形式挂载
- 🧮 **消息守恒（1.1）**: 每跳耗时精确追踪（`hopTimings` + UUIDv7 出生时间）+ 生命周期登记（`Q_FINISH`/`Q_SINK`/`Q_ERROR`）+ 守恒对账（`getConservationReport`），可定位“哪个神经管道吞了消息”
- 🏗️ **Runtime Builder**: 声明式运行时配置，通过 Zod schema 驱动队列与 Worker 装配
- ✅ **统一验证**: 多级验证框架，支持分级结果（INFO/WARNING/ERROR/CRITICAL）
- 🔐 **脱敏工具**: 内置 `desensitize` / `desensitizeObject`，自动屏蔽日志中的 API Key、Token 等敏感信息
- 📊 **指标 API**: 内置监控指标接口
- 🚀 **跨平台**: 核心框架兼容 Bun 和 Node.js 运行时（`MetricsAPIServer` 运行时自动判断）

> ⚠️ **审查流程已废弃（1.1 起）**：原内置审计流水线（`Q_AUDIT_INPUT` → `Q_AUDITED_INPUT` → `Q_AUDIT_OUTPUT` → `Q_RESPONSE_SINK`）、`injectInput`、`moral_audit_prompts`、`auditLogger` 及 SINK 白名单已标注 `@deprecated`，审查机制交由 Agent 层实现，框架不再关心内容审查。升级请参考 `UPGRADE.md`。

## 安装

> 📦 **从 1.0-dev 升级到 1.1.0？** 请阅读 [`UPGRADE.md`](./UPGRADE.md)——包含依赖变更、废弃项、破坏性行为变更与验证清单。

### 基础安装

```bash
# 使用 Bun（推荐）
bun add @syrkos/aethelum-core-lite

# 或使用 npm
npm install @syrkos/aethelum-core-lite
```

### 开发环境设置

```bash
git clone https://github.com/corolin/AethelumCoreLite.git
cd AethelumCoreLite

# 安装依赖
bun install

# 类型检查
bun run typecheck

# 运行测试
bun test
```

## 项目结构

```
src/
├── core/                   # 核心模块
│   ├── router.ts           # 路由器（神经胞体）
│   ├── message.ts          # 神经脉冲消息定义
│   ├── queue.ts            # 异步突触队列
│   ├── queue-factory.ts    # 可配置队列工厂（支持 Hook Plugin 装配）
│   ├── worker.ts           # 轴突工作器
│   ├── worker-factory.ts   # Worker 配置工厂（支持声明式 Hook 挂载）
│   ├── runtime-builder.ts  # Runtime 统一建造器（队列 + Worker 声明式装配）
│   ├── monitor.ts          # 工作器监控器
│   └── error_handler.ts    # 错误处理器
├── hooks/                  # 钩子系统
│   ├── chain.ts            # 钩子链管理
│   ├── runtime.ts          # Hook Plugin Registry（插件注册与装配）
│   ├── types.ts            # 钩子类型定义
│   └── wal_hook.ts         # WAL Hook 实现及 Plugin 工厂
├── config/                 # 配置模块
│   ├── config_loader.ts    # 配置加载器
│   └── runtime-schema.ts   # Runtime Zod Schema（队列/Worker/Router 声明式配置）
├── utils/                  # 工具模块
│   ├── desensitizer.ts     # 敏感数据脱敏工具（API Key / Token 屏蔽）
│   ├── unified_validator.ts    # 统一验证框架
│   ├── wal_writer.ts       # WAL 写入器
│   ├── logger.ts           # 日志器
│   ├── structured_logger.ts    # 结构化日志
│   ├── payload_store.ts    # 负载存储
│   └── log_analytics.ts    # 日志分析
├── api/                    # API 模块
│   └── metrics_api.ts      # 指标 API
├── prompts/                # 提示词模块
│   └── moral_audit_prompts.ts  # 道德审计提示词
└── types/                  # 全局类型定义
```

## 导出路径

| 导入路径 | 包含内容 |
|---------|---------|
| `@syrkos/aethelum-core-lite/core` | Router、Queue、Worker、Monitor、ErrorHandler、RuntimeBuilder |
| `@syrkos/aethelum-core-lite/hooks` | HookChain、HookPluginRegistry、WAL Hook |
| `@syrkos/aethelum-core-lite/utils` | desensitizer、structured_logger、wal_writer、unified_validator、payload_store 等 |
| `@syrkos/aethelum-core-lite/config` | ConfigLoader、RuntimeSchema |
| `@syrkos/aethelum-core-lite/api` | MetricsAPI |
| `@syrkos/aethelum-core-lite/prompts` | MoralAuditPrompts（⚠️ 已废弃，随审查流程移除） |
| `@syrkos/aethelum-core-lite/types` | LLMProvider、LLMChatOptions 等通用类型 |

## 核心概念

### 神经脉冲 (NeuralImpulse)

在神经元间传递的信息包：

- `sessionId`: 会话 ID
- `actionIntent`: 路由目标队列
- `sourceAgent`: 消息来源 Agent
- `inputSource`: 输入来源类型
- `content`: 消息内容
- `metadata`: 元数据（可扩展）
- `priority`: 消息优先级
- `expiresAt`: 过期时间

### 神经元组件

#### CoreLiteRouter (神经胞体路由器)

主控制器，管理队列和工作器的注册与路由：

```typescript
import { CoreLiteRouter, AsyncSynapticQueue, NeuralImpulse } from '@syrkos/aethelum-core-lite/core';

// 创建路由器（默认启用 WAL）
const router = new CoreLiteRouter();

// 手动注册额外队列（传入队列实例）
const processQueue = new AsyncSynapticQueue('Q_PROCESS');
router.registerQueue(processQueue);

// 激活路由器（启动所有已注册 Worker）
router.activate();

// 路由消息
const impulse = new NeuralImpulse({
    sessionId: 'user-123',
    actionIntent: 'Q_PROCESS',
    sourceAgent: 'HTTPGateway',
    content: 'Hello, World!',
});
await router.routeMessage(impulse, 'Q_PROCESS');

// 停止系统（顺序：monitor → workers → queues）
await router.stop();
```

路由器内置系统队列：`Q_ERROR`、`Q_DONE`（通用基础设施），以及已废弃的审查队列 `Q_AUDIT_INPUT`、`Q_AUDITED_INPUT`、`Q_AUDIT_OUTPUT`、`Q_REFLECTION`、`Q_RESPONSE_SINK`（⚠️ 自本版本起废弃，仅兼容旧版，后续版本移除），并提供动态队列创建与安全路由机制。

> **⚠️ 审查流程废弃说明**：原内置审计流水线（Q_AUDIT_INPUT → Q_AUDITED_INPUT → Q_AUDIT_OUTPUT → Q_RESPONSE_SINK）自本版本起标注废弃。审查机制交由 Agent 层实现，框架不再关心内容审查。Agent 应通过自定义队列（如 `Q_QQ_GATEWAY_INGRESS` / `Q_QQ_GATEWAY_EGRESS`）搭建自己的神经管道。

**构造选项**：

```typescript
// 简写（布尔值控制 WAL）
const router = new CoreLiteRouter(false); // 禁用 WAL

// 完整选项
const router = new CoreLiteRouter({
    enableWal: true,
    skipBuiltInQueues: false,       // 跳过内置队列（通常配合 RuntimeBuilder 使用）
    builtInQueues: [...],           // 自定义内置队列定义
});
```

#### AsyncSynapticQueue (突触队列)

高性能异步队列，支持优先级、超时获取、自动扩容和 WAL 持久化：

```typescript
import { AsyncSynapticQueue } from '@syrkos/aethelum-core-lite/core';

const queue = new AsyncSynapticQueue(
    'my_queue',
    1000,         // 初始容量（0 = 无限）
    true,         // 自动扩容
    10 * 60_000,  // 缩容检查间隔（ms）
);

// 生产消息
await queue.asyncPut(impulse);

// 消费消息（支持超时，单位 ms）
const message = await queue.asyncGet(1000);

// 声明式挂载 Hook Plugin
await queue.attachHookPlugins(registry, [{ plugin: 'wal' }]);
```

#### AsyncAxonWorker (轴突工作器)

异步消息处理单元，内置三条钩子链（pre / post / error）：

```typescript
import { AsyncAxonWorker } from '@syrkos/aethelum-core-lite/core';

class MyWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        impulse.content = `Processed: ${impulse.content}`;
        await this.routeAndDone(impulse, 'Q_RESPONSE');
    }
}

const worker = new MyWorker('my-worker', inputQueue, router);

// 声明式挂载 Hook Plugin
await worker.attachHookPlugins(registry, [{ plugin: 'my-plugin' }]);

worker.start();
```

## Hook Plugin 系统

Hook Plugin Registry 提供声明式、可复用的钩子装配能力，将"如何注册 Hook"从业务代码中解耦。

### 注册插件

```typescript
import { HookPluginRegistry } from '@syrkos/aethelum-core-lite/hooks';
import { BaseAsyncHook } from '@syrkos/aethelum-core-lite/hooks';
import { HookType } from '@syrkos/aethelum-core-lite/hooks';

const registry = new HookPluginRegistry();

registry.register({
    id: 'my-prefix-hook',
    description: '在入队前为消息内容添加前缀',
    supports: (mount) => mount.kind === 'queue',   // 仅限 queue 类型宿主
    setup: async (mount, options) => ({
        hooks: [new MyPrefixHook(String(options.prefix ?? ''))],
        dispose: async () => { /* 清理资源 */ },
    }),
});
```

### 注册 Profile（可复用捆绑包）

```typescript
registry.registerProfile('durable-chat', [
    { plugin: 'wal',        options: { walDir: 'wal_data_v2' } },
    { plugin: 'my-prefix-hook', options: { prefix: 'chat:' } },
]);
```

### WAL Hook Plugin

WAL 以 Plugin 形式提供，通过 `createWalHookPlugin` 注册：

```typescript
import { createWalHookPlugin } from '@syrkos/aethelum-core-lite/hooks';

registry.register(createWalHookPlugin('wal_data_v2'));

// 之后在队列或 builder 中通过 plugin: 'wal' 引用
await queue.attachHookPlugins(registry, [{ plugin: 'wal' }]);
```

## Runtime Builder（推荐用于生产）

`CoreLiteRuntimeBuilder` 提供统一的声明式装配入口，自动处理队列创建、Hook 挂载、Worker 配置和路由器注册：

```typescript
import { CoreLiteRuntimeBuilder } from '@syrkos/aethelum-core-lite/core';
import { HookPluginRegistry } from '@syrkos/aethelum-core-lite/hooks';
import { createWalHookPlugin } from '@syrkos/aethelum-core-lite/hooks';

// 1. 准备 Registry
const registry = new HookPluginRegistry();
registry.register(createWalHookPlugin());           // 注册 WAL plugin
registry.registerProfile('durable', [{ plugin: 'wal' }]);

// 2. 创建 Builder
const builder = new CoreLiteRuntimeBuilder(registry);

// 3. 声明式构建运行时
const { router, queues } = await builder.build({
    router: {
        enableWal: true,            // 自动为 built-in durable queues 挂载 WAL
    },
    queues: [
        {
            id: 'Q_CUSTOM',
            capacity: 500,
            hooks: { profiles: ['durable'] },   // 套用 profile
        },
    ],
});

// 4. 注册 Workers（支持声明式 Hook 挂载）
const myWorker = new MyWorker('my-worker', queues.get('Q_CUSTOM')!, router);
await builder.registerWorkers(router, [
    {
        worker: myWorker,
        definition: {
            hooks: { plugins: [{ plugin: 'my-prefix-hook' }] },
        },
    },
]);

// 5. 启动
router.activate();
```

> **说明**：当 `registry` 中注册了 `wal` plugin 且 `enableWal: true` 时，Builder 会自动为 `Q_ERROR`（及已废弃的 `Q_AUDIT_INPUT`、`Q_AUDITED_INPUT`、`Q_AUDIT_OUTPUT`、`Q_REFLECTION`，⚠️ 兼容旧版）注入 WAL hook，无需手动声明。

## 快速开始（不使用 Builder）

```typescript
import {
    CoreLiteRouter,
    AsyncSynapticQueue,
    AsyncAxonWorker,
} from '@syrkos/aethelum-core-lite/core';
import { NeuralImpulse } from '@syrkos/aethelum-core-lite/core';

// 1. 创建路由器
const router = new CoreLiteRouter({ enableWal: false }); // 开发时可关闭 WAL

// 2. 创建并注册自定义队列
const inputQueue = new AsyncSynapticQueue('Q_PROCESS', 1000, true);
const outputQueue = new AsyncSynapticQueue('Q_RESPONSE', 1000, true);
router.registerQueue(inputQueue);
router.registerQueue(outputQueue);

// 3. 定义 Worker
class EchoWorker extends AsyncAxonWorker {
    protected async process(impulse: NeuralImpulse): Promise<void> {
        impulse.content = `Echo: ${impulse.content}`;
        await this.routeAndDone(impulse, 'Q_RESPONSE');
    }
}

// 4. 注册并启动
const worker = new EchoWorker('echo-worker', inputQueue, router);
router.registerWorker(worker);
router.activate();

// 5. 发送消息
const impulse = new NeuralImpulse({
    sessionId: 'test-session',
    actionIntent: 'Q_PROCESS',
    sourceAgent: 'CLI',
    content: 'Hello, Aethelum!',
});
await router.routeMessage(impulse, 'Q_PROCESS');

// 6. 消费响应
const response = await outputQueue.asyncGet(1000);
console.log(response?.content); // "Echo: Hello, Aethelum!"

// 7. 优雅停机
await router.stop();
```

## 工具模块

### 脱敏工具 (desensitizer)

对日志中的敏感信息（API Key、Token、密码等）进行自动屏蔽：

```typescript
import { desensitize, desensitizeObject } from '@syrkos/aethelum-core-lite/utils';

// 字符串脱敏
desensitize('Authorization: Bearer sk-abc123...');
// → 'Authorization: Bearer sk-ab...'

// 对象递归脱敏（适合日志输出）
desensitizeObject({
    api_key: 'sk-secret-key-1234',
    message: 'hello',
});
// → { api_key: 'sk-s...234', message: 'hello' }
```

支持的模式：OpenAI `sk-*`、Bearer Token、GitHub `ghp_*`、Discord Token、URL 中的凭证、通用 `key=value` 键值对。

### 结构化日志 (structured_logger)

```typescript
import { getStructuredLogger } from '@syrkos/aethelum-core-lite/utils';

const logger = getStructuredLogger('MyModule', {
    level: 'INFO',
    format: 'plain',   // 'json' | 'plain'
    file: { path: 'logs/app.log' },
});

logger.info('消息处理完成', { metadata: { sessionId: 'abc' } });
logger.warning('队列积压', { metadata: { queueId: 'Q_PROCESS', size: 500 } });
```

### WAL 写入器 (wal_writer)

```typescript
import { ImprovedWALWriter } from '@syrkos/aethelum-core-lite/utils';

const wal = new ImprovedWALWriter('Q_PROCESS', 'wal_data_v2', true);
const recovered = await wal.start(); // 返回崩溃恢复条目

const lsn = await wal.writeLog1('msg-id', 1, { content: '...' });
wal.writeLog2('msg-id', lsn);       // 确认消费
await wal.writeDelete(lsn);         // 墓碑删除
await wal.stop();                   // flush + 压缩
```

## 钩子系统

框架内置灵活的钩子机制，支持在消息处理的不同阶段插入自定义逻辑：

```typescript
// 支持的钩子类型
enum HookType {
    PRE_PROCESS = 'PRE_PROCESS',          // Worker 前置处理
    POST_PROCESS = 'POST_PROCESS',        // Worker 后置处理
    ERROR_HANDLER = 'ERROR_HANDLER',      // 错误处理
    TRANSFORM = 'TRANSFORM',              // 消息转换
    FILTER = 'FILTER',                    // 消息过滤
    QUEUE_BEFORE_PUT = 'QUEUE_BEFORE_PUT' // 入队前处理
}
```

钩子链特性：
- 优先级降序执行
- 超时控制
- 信号机制（中断/继续）
- 动态启用/禁用（`enabled` 字段）
- 批量添加（`addHooks()`）

## WAL 持久化

Write-Ahead Logging 以 Hook Plugin 形式挂载，为队列消息提供崩溃恢复能力。

**双日志结构**：

```
消息入队 → Log1（数据日志，消息入当前队列之前落盘）
          ↓
     Worker 处理
          ↓
消息移交 → Log2（确认日志，消息成功进入下一队列后，对来源队列确认）
```

**核心保证**：任意时刻只有一个队列认为某条消息是"未消费"的。崩溃只会重放"尚未完成移交"的消息。

**存储结构**：
```
wal_data_v2/
└── {queueId}/
    ├── tracker.ptr          # 已提交的 LSN 位点（原子重命名写入）
    ├── log1_000000.wal      # WAL 段文件（每段最大 100MB）
    └── log1_000001.wal      # 自动轮转
```

**WAL 记录格式**：`LSN|CHECKSUM|PAYLOAD_LENGTH|PAYLOAD\n`

**终端队列**（`Q_DONE`，及已废弃的 `Q_RESPONSE_SINK`⚠️）：是消息的最终归宿，不需要 WAL。`Q_RESPONSE_SINK` 的业务语义随审查流程废弃，由新生命周期登记队列 `Q_SINK` 取代。

## 消息守恒与生命周期记账（1.1.0）

框架保证“该拿到的不丢、该传递的传递、**账目能对上**”：每个神经脉冲都有归宿，且可对账。

### 每跳耗时精确追踪

- `NeuralImpulse.hopTimings`：`[{ node, ts }]` 数组，自动记录每一跳（入队/出队/处理/路由）的时间戳，**两两相减即得每跳耗时**
- `getEndToEndDuration()`：端到端耗时 = 末跳 - 创建时间
- `messageId` 为 UUIDv7，自带出生时间（`NeuralImpulse.parseUuidV7Timestamp()` 可解析），与 `timestamp` 互为校验

### 生命周期登记队列

框架内置三个“归宿寄存器”（由框架自动写入，Agent 可挂记账 Worker 消费）：

- `Q_FINISH`：处理完成登记（Worker 流程结束时自动路由）
- `Q_ERROR`：错误登记（errorHandler 自动路由，错误脉冲与原始脉冲同 ID）
- `Q_SINK`：销毁登记（钩子拦截、过期丢弃、未定归宿兑底）

```typescript
const report = router.getConservationReport();
// { created, finished, errored, sunk, inFlight, suspicious, balanced }
// balanced: created === finished + errored + sunk + inFlight

// 疑似被吞的消息（最后停留队列 + 闲置时长）→ 定位“哪个神经管道吞了消息”
const suspects = router.getSuspiciousMessages();
// [{ messageId, lastQueue, lastTs, idleMs }]
```

### Hook 增强：旁路发射 + 尽力而为

- **`context.emit(impulse, targetQueueId)`**：Hook 可在处理过程中向管道发射独立脉冲（fan-out），适合“演绎结束 → 旁路到 Live2D”等场景；不 `await` 即不阻塞主通路
- **`BaseAsyncHook(..., bestEffort)`**：`bestEffort: true` 时钩子失败/超时仅告警并继续链，适合记忆写入、生命周期登记、遥测等旁路副作用；超时标记 `HookExecutionStatus.TIMEOUT`

## 健康监控与容错

### 健康评分系统

每个 Worker 维护一个 0–100 的健康分数：

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

熔断后：Worker 状态设为 ERROR，停止处理新消息；若 `autoRecovery: true`，延迟后自动重启。

### 自动恢复

恢复流程：重置连续错误计数 → 恢复健康分数至 80 → 调用 `worker.start()` 重启。

## 并发安全性

AethelumCoreLite 基于 JavaScript 事件循环，天然避免多线程竞争：

- **AsyncSynapticQueue**: Promise 链确保操作顺序，无锁设计
- **AsyncWorkerMonitor**: Map 数据结构保护，返回数据副本防止外部修改
- **AsyncAxonWorker**: 状态转换原子性，`process()` 方法串行执行

## 性能考虑

- **事件循环**: 单线程避免锁竞争
- **零拷贝**: NeuralImpulse 引用传递
- **优先级队列**: 5 级优先级确保关键消息优先处理
- **WAL 持久化**: 异步写入，不阻塞主流程
- **自动扩容 / 缩容**: 队列容量随负载动态调整

## 技术栈

| 组件 | 技术 |
|------|------|
| **运行时** | Bun / Node.js（`MetricsAPIServer` 运行时自动适配）|
| **语言** | TypeScript 5.9+ |
| **模块系统** | ESM (nodenext) |
| **序列化** | JSON |
| **Schema 验证** | Zod |
| **Web 框架** | Hono |
| **UUID** | uuid v7 |

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| `1.1.2` | 2026-10-13 | **自环防御与生命周期终结健壮性**：① 阻断 Worker 未路由脉冲自环与毒消息重投自环（硬上限 3 次）；② 隔离手动路由标记（从元数据下沉为实例闭包状态，避免跨 Worker 污染）；③ 生命周期终点队列（`Q_FINISH`/`Q_SINK`/`Q_ERROR`）引入容量限额与环形最老淘汰（`evictOldestOnFull`），强制过滤 WAL 插件并阻断 discard 递归级联；④ 修复 WAL 写入器在 Bun 下因未关闭句柄触发的 `ERR_INVALID_STATE` 崩溃，完善 Windows 目录 fsync 兼容；⑤ `bestEffort` 钩子失败不再污染主脉冲状态（仅记入警告）；⑥ 错误脉冲保留原始上下文元数据；⑦ 精确守恒记账（仅在入队成功后记账）与动态队列管控策略。 |
| `1.1.1` | 2026-08-13 | **动态持久化队列与 WAL 运维扩展**：① 新增 `router.ensureQueue()` 运行时幂等建队与 hookPlugins 装配；② 自动建队注入 onDiscard 丢弃追踪；③ 新增 `ImprovedWALWriter.compactNow()` 手动压缩运维 API。 |
| `1.1.0` | 2026-08-13 | **框架定位收敛为“Agent 的树神经”（脉冲传递基础设施）**：① 审查流程废弃——`Q_AUDIT_INPUT`（AUDIT_I）/ `Q_AUDITED_INPUT`（AUDIT_II）/ `Q_AUDIT_OUTPUT` / `Q_REFLECTION` 及 SINK 白名单、`injectInput`、`moral_audit_prompts`、`auditLogger` 标注 `@deprecated`，审查机制交由 Agent 层实现；② 每跳耗时追踪——`NeuralImpulse.hopTimings` + UUIDv7 出生时间解析，精确记录每一跳消费时间；③ 消息守恒——新增生命周期登记队列 `Q_FINISH` / `Q_SINK`，Worker 自动归宿登记（完成/销毁/错误/兜底），Router 提供 `getConservationReport()` / `getSuspiciousMessages()` 对账与“被吞消息”定位；④ Hook 增强——`HookContext.emit` 旁路发射能力（fan-out），`BaseAsyncHook.bestEffort` 尽力而为语义（失败/超时不中断流转），超时标记 `HookExecutionStatus.TIMEOUT` |
| `1.0.2-dev.8` | 2026-04-05 | **时区支持**：`PlainFormatter` / `JsonFormatter` 新增 `timezone` 参数；`'local'` 自动解析系统时区；`LoggerManager` 透传 `timezone` 配置 |
| `1.0.2-dev.7` | 2026-04-05 | **Node.js 兼容性**：`MetricsAPIServer` 改为运行时自动判断（Bun.serve / node:http 桥接）；`config_loader` TOML 解析改为 `smol-toml`，彻底移除所有 Bun 专属 API |
| `1.0.2-dev.6` | 2026-04-05 | **架构修正**：移除 `self-refining` 模块（业务逻辑，不属于框架层）；新增 `desensitizer` 到 `utils`；清理 dist 残留产物 |
| `1.0.2-dev.5` | 2026-04-05 | 新增 `desensitizer` 脱敏工具到 `utils`（已废弃，请升级）|
| `1.0.2-dev.4` | 2026-04-03 | `refactor(worker)`：将 while 轮询改为观察者模式 Promise 信号，降低空转 CPU |
| `1.0.2-dev.3` | 2026-04-02 | 新增队列 `.close()` 方法，支持优雅关闭时唤醒阻塞消费者 |
| `1.0.2-dev.2` | 2026-04-02 | CI 修复：确保 `dist/` 每次发布前必须 build；首个稳定 CI 发布版本 |
| `1.0.2-dev.1` | 2026-04-02 | **Hook Plugin 系统**：`HookPluginRegistry`、`CoreLiteRuntimeBuilder`、`ConfigurableQueueFactory`，WAL 从队列内嵌改为以 Plugin 形式挂载 |
| `1.0.1-dev.9` | 2026-04-01 | `perf(stop)`：关闭时立即唤醒消费者，跳过退出压缩，大幅缩短停机耗时 |
| `1.0.1-dev.7` | 2026-04-01 | **WAL Hook 化**：`feat(core)` 将 WAL 从 `AsyncSynapticQueue` 解耦，改为 Hook 插件挂载 |
| `1.0.1-dev.2` | ~2026-03 | WAL 全面重写：两阶段压缩、fsync 原子写、墓碑删除（防 ghost replay）、崩溃恢复 |
| `1.0.1` | ~2026-03 | `MetricsAPI` 可选认证；`AsyncWorkerMonitor` 防重叠；Worker 自动恢复改进 |
| `1.0.0`（TS 移植版） | 2026-03-04 | **从 Python 移植到 Node.js/Bun**，重新实现异步队列、路由、WAL、钩子系统 |
| `1.0.0`（Python 初版） | 2025 | 原始 Python AsyncIO 架构，语义等价的树神经通信模型 |

## 开发

```bash
# 运行测试
bun test

# 类型检查
bun run typecheck
```

## License

MIT

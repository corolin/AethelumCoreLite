# UPGRADE.md — 1.0-dev → 1.1.2 升级指南（面向 AI 升级骨架）

> **增量：1.1.1 → 1.1.2（健壮性与防死循环修复，强烈建议升级，无破坏性 API 变更）**
>
> 1. **未路由自环与毒消息重投阻断**：
>    - Worker 在脉冲处理后，若自动路由目标 `targetQueue === this.inputQueue.queueId`，强制拦截并转入 `lifecycleFinish` 终结，彻底杜绝微任务纳秒级自投自收打满事件循环。
>    - Worker 捕获异常时，若 ErrorHook 未重定向或重定向指向自身队列，严禁重复入队自身；新增脉冲级错误重试硬上限（3次），超出后立即终结并记入错误日志。
> 2. **手动路由标记 Worker 级隔离**：
>    - 废除在 `impulse.metadata._manually_routed` 写入持久化标记的设计（该设计曾导致多级管道下游 Worker 误判跳过自动路由），改为 Worker 内部实例状态闭包追踪，避免元数据跨 Worker 污染。
> 3. **生命周期终点队列环形淘汰与 WAL 拦截**：
>    - `AsyncSynapticQueue` 新增 `evictOldestOnFull` 配置。`Q_FINISH`、`Q_SINK` 等终点队列默认开启容量限额（10,000）与环形最老淘汰，防止内存泄漏；
>    - 队列工厂强制过滤终点队列挂载 WAL 插件，避免终结状态反复落盘；
>    - Router 阻断终点队列自身的 `onDiscard` 级联投递，杜绝丢弃死循环。
> 4. **WAL 写入器文件句柄显式释放与 Windows 平台兼容**：
>    - `ImprovedWALWriter` 在写操作所有出口处使用 `try ... finally` 显式 `await fd?.close()`，彻底消除 Bun 垃圾回收未关闭句柄抛出的 `ERR_INVALID_STATE` 异常；
>    - 在 Windows 平台针对目录自动跳过不支持的 `fsync` 调用。
> 5. **钩子尽力而为（`bestEffort`）状态净化**：
>    - `bestEffort: true` 钩子失败时仅在 `impulse.metadata.hook_warnings` 记录告警，不再污染主脉冲 `status = FAILED`。
> 6. **错误脉冲元数据保留**：
>    - `createErrorImpulse` 会继承合并原始脉冲的 `metadata`（保留平台、会话、`reply_target` 等上下文）。
> 7. **精确守恒记账与动态队列受控策略**：
>    - Router 仅在 `queue.asyncPut` 成功后递增 `created` 与在途计数；
>    - Router 支持 `dynamicQueues: { mode: 'deny' | 'allow', allowPatterns }` 策略，防止意料之外的隐式队列无序膨胀。
>
> ---
>
> **增量：1.1.0 → 1.1.1（纯新增，无破坏性变更，直接 bump 依赖即可）**
>
> 1. **F1 动态 durable 队列官方路径**：`CoreLiteRouter.ensureQueue(definition)` —— 运行时幂等建队（已存在直接返回）。构造 Router 时传入 `hookRegistry`（`CoreLiteRuntimeBuilder.createRouter` 已自动注入自身 registry），即可按 `definition.hookPlugins` 挂插件（如 `[{ plugin: 'wal' }]`），并以 registerQueue 语义注入 onDiscard 归宿登记 + 纳入守恒对账。典型用法（Nexus 动态队列改造）：
>    ```ts
>    await router.ensureQueue({ id: `Q_DISPATCH:${id}`, capacity: 50, hookPlugins: [{ plugin: 'wal' }] });
>    ```
>    同时 `registerWorker` 注册的输入队列改为 registerQueue 语义（注入 onDiscard；原先裸 `queues.set`，丢弃消息无归宿登记）。
> 2. **F2 自动建队补登记**：`routeMessage` 动态创建的队列同样注入 onDiscard（不自动挂 WAL——意图不明的隐式建队不应静默落盘）。
> 3. **F3 WAL 运维 API**：`ImprovedWALWriter.compactNow()` —— 立即执行段压缩（与写路径互斥；取消未到期的 debounce 调度；未启用 WAL 为 no-op）。长期运行可低峰定时触发，不依赖写删除后的自动调度。
>
> 本文件供 **AI/开发者** 将基于 `1.0-dev` 的 AethelumCoreLite 骨架升级到 `1.1.0` / `1.1.2`。
> 覆盖：依赖变更、废弃项、破坏性行为变更、新能力启用、验证步骤。
> 版本对应源码：`1.1.2`（`package.json` `version: "1.1.2"`）。

---

## 0. 升级总览

`1.1.0` 的核心变化：

1. **框架定位收敛为"Agent 的树神经"**——脉冲传递基础设施，只保证：该拿到的不丢、该传递的传递、账目能对上
2. **审查流程废弃**——原内置审计流水线（Q_AUDIT_*）标注 `@deprecated`，审查机制移交 Agent 层
3. **消息守恒**——每跳耗时精确追踪（`hopTimings`）+ 生命周期登记（Q_FINISH/Q_SINK/Q_ERROR）+ 守恒对账
4. **Hook 增强**——旁路发射（`context.emit`）+ 尽力而为（`bestEffort`）
5. **若干正确性修复**——WAL 来源确认断链、runLoop 忙循环、动态队列参数错位、手动路由标记语义

---

## 1. 依赖与工具链变更

### 1.1 直接依赖（dependencies）

| 包 | 旧版本 | 新版本 | 说明 |
|---|---|---|---|
| `hono` | `^4.12.4` | `^4.13.1` | minor |
| `smol-toml` | `^1.6.1` | `^1.8.0` | minor |
| `zod` | `^4.3.6` | `^4.4.3` | minor |
| `uuid` | `^13.0.0` | `^14.0.1` | **major**：要求 `node@>=20` 且 `crypto` 全局可用（Bun 内置满足）；`v7` 导出保留，仅用 `v7 as uuidv7` 的代码无需改动 |

### 1.2 开发依赖（devDependencies）

| 包 | 旧版本 | 新版本 | 说明 |
|---|---|---|---|
| `@types/bun` | `^1.3.10` | `^1.3.14` | patch |
| `@types/node` | `^25.3.3` | `^26.2.0` | **major**：Node 26 类型（tsconfig `types: ["node","bun"]` 下 typecheck 已验证通过） |
| `@typescript-eslint/eslint-plugin` | `^8.56.1` | `^8.67.0` | minor |
| `@typescript-eslint/parser` | `^8.56.1` | `^8.67.0` | minor |
| `eslint` | `^10.0.2` | `^10.8.1` | minor |
| `typescript` | `^5.9.3` | **保持 `^5.9.3`** | ⚠️ **不要升级到 7.x**：`@typescript-eslint` 8.67 的 peerDependencies 为 `typescript <6.1.0`，eslint 生态尚不支持 TS7 |

### 1.3 scripts 变更

```jsonc
// package.json scripts
"test": "bun test --parallel=1"   // 旧：bun test
```

原因：并行跑测试文件时 WAL 测试（固定临时目录）互相干扰，串行文件执行可消除。

### 1.4 执行命令

```bash
bun add hono@^4.13.1 smol-toml@^1.8.0 zod@^4.4.3 uuid@^14.0.1
bun add -d @types/bun@^1.3.14 @types/node@^26.2.0 \
  @typescript-eslint/eslint-plugin@^8.67.0 @typescript-eslint/parser@^8.67.0 eslint@^10.8.1
bun install
# 若仓库同时维护 npm 锁文件：
npm install --package-lock-only --ignore-scripts
```

---

## 2. 废弃项（功能保留、标 `@deprecated`，新代码勿用）

> 审查机制交由 Agent 层实现，框架不再关心内容审查。以下 API 仍可用（兼容），但会在后续版本移除。

### 2.1 内置审查队列（@deprecated）

文件：`src/core/router.ts`（`getDefaultBuiltInQueueDefinitions`）、`src/core/runtime-builder.ts`

| 队列 | 旧用途 | 替代 |
|---|---|---|
| `Q_AUDIT_INPUT`（AUDIT_I） | 输入审计入口 | Agent 自定义入口队列（如 `Q_QQ_GATEWAY_INGRESS`） |
| `Q_AUDITED_INPUT`（AUDIT_II） | 审计通过后业务入口 | 同上 |
| `Q_AUDIT_OUTPUT` | 输出审计 | Agent 自定义输出链 |
| `Q_REFLECTION` | 反思队列 | 按需自定义 |
| `Q_RESPONSE_SINK` | 审计输出终点 | 由新生命周期登记队列 `Q_SINK` 取代 |

**保留的通用队列**：`Q_ERROR`（错误登记）、`Q_DONE`（通用终点）。

### 2.2 `injectInput()`（@deprecated）

文件：`src/core/router.ts`

```ts
// 旧：强制改写 actionIntent 并路由到 Q_AUDIT_INPUT
await router.injectInput(impulse);
// 新：直接路由到自定义入口队列
await router.routeMessage(impulse, 'Q_QQ_GATEWAY_INGRESS');
```

### 2.3 SINK 安全（@deprecated）

文件：`src/core/worker.ts`

- `ALLOWED_SINK_SOURCES` / `isSinkAccessAllowed()` / `validateSinkSecurity()` 全部废弃
- `routeMessage` 中的 SINK 拦截分支与 `AuditInputWorker` 特殊路由分支废弃（保留兼容）

### 2.4 prompts 模块（@deprecated）

文件：`src/prompts/moral_audit_prompts.ts`（导出面 `@syrkos/.../prompts`）

- 内容安全审计 LLM 提示词与防注入 token，整体废弃
- 审查逻辑迁移到 Agent 侧实现

### 2.5 `auditLogger`（@deprecated）

文件：`src/utils/logger.ts`

---

## 3. 破坏性行为变更（必须适配）

### 3.1 `actionIntent = 'Done'` 语义变更 ⭐

**旧**（1.0-dev，另一个 Agent 的中间重构）：`routeAndDone()` 与 Router 代理把 `actionIntent` 设为 `'Done'` 作为"已手动路由"标记。

**新**（1.1.0）：

- 手动路由标记改为消息级 `metadata['_manually_routed']`（由 Router 代理设置）
- `actionIntent === 'Done'` 或 `'Q_DONE'` 或空 → **流程结束** → Worker 自动登记 `Q_FINISH`

**适配**：

```ts
// 旧：判断子类是否已手动路由
if (impulse.actionIntent === 'Done') { /* 已路由 */ }
// 新：
if (impulse.metadata['_manually_routed']) { /* 已路由 */ }
```

**注意**：终结点 Worker（处理完不再转发）应把 `actionIntent` 置为 `'Done'` 以触发 FINISH 登记。

### 3.2 内置队列新增：`Q_FINISH` / `Q_SINK`（生命周期登记）

文件：`src/core/router.ts`（内置队列由 8 个 → 10 个）

- `Q_FINISH`：完成登记（Worker 流程结束时自动路由）
- `Q_SINK`：销毁登记（钩子拦截、过期丢弃、未定归宿兜底）
- 二者容量 `100_000` + 自动扩容，仅作"归宿寄存器"，Agent 可挂记账 Worker 消费

**影响**：

1. 所有经 `AsyncAxonWorker` 处理的**终结消息**会自动多一跳到登记队列（需 `router.activate()`；未激活时登记路由返回 `false`，不抛错）
2. `routeMessage` 对登记队列（Q_FINISH/Q_SINK/Q_ERROR）**不再覆盖 status**：
   - `Q_FINISH` → `COMPLETED`、`Q_SINK` → `CANCELLED`、`Q_ERROR` → `FAILED`

### 3.3 基类自动路由走原始 Router

文件：`src/core/worker.ts`（`processImpulse`）

- 基类自动路由 / SINK 校验失败路由 / ErrorHook 后路由：改用 `this.originalRouter.routeMessage(...)`（不再经过代理）
- **效果**：`_manually_routed` 只在**子类手动调用** `this.router.routeMessage()` / `routeAndDone()` 时设置，不会因基类自动路由而污染下游判断

### 3.4 错误脉冲继承原始 messageId

文件：`src/core/error_handler.ts`（`createErrorImpulse`）

- 错误脉冲（进 Q_ERROR）与原始脉冲**同 `messageId`**，并继承 `hopTimings`
- 目的：守恒对账可把 Q_ERROR 登记对应回原始消息
- **注意**：按 messageId 追踪时，错误脉冲与原消息同 ID，需用 `status` / `metadata.error_type` 区分

### 3.5 队列丢弃归宿登记（onDiscard）

文件：`src/core/queue.ts`、`src/core/router.ts`

- 新增 `queue.onDiscard?: (impulse, reason) => Promise<void>`，由 `router.registerQueue()` 自动注入（指向 `lifecycleSink`）
- 触发：**过期丢弃**（`asyncGet` 消费时发现）与 **BEFORE_PUT 钩子拦截**
- **影响**：未注册到 Router 的裸队列无 `onDiscard`（行为与 1.0 相同）；注册过的队列丢弃消息会登记 Q_SINK

### 3.6 WAL 来源确认修复（行为变化）

文件：`src/core/queue.ts`、`src/utils/wal_writer.ts`、`src/hooks/wal_hook.ts`

- 出队/直接投递时同步记录 `metadata['_src_wal_lsn']`
- `wal_writer.ownsLsn(lsn)`：判定 LSN 归属
- `wal_hook` afterAck：无显式来源 LSN 时，`wal_lsn` 经 `ownsLsn` 校验后才删除；**不属于本队列 → 告警并跳过**（防止误删其他队列 WAL 记录）
- **修复了**：源队列 WAL Log1 记录永不删除/崩溃重放已移交消息的问题

### 3.7 Worker 生命周期改进

文件：`src/core/worker.ts`、`src/core/queue.ts`

- `worker.stop()` 现在**等待 runLoop 退出**（最多 3s 兜底），并保存 `runLoopPromise`
- runLoop 遇到**已关闭队列**直接退出（不再忙循环饿死事件循环）
- `queue.isClosed()` 新方法
- `asyncGet` 在 push 消费者后二次检查 `_closed`（修复 close 竞态）

### 3.8 Hook 接口变更 ⭐

文件：`src/hooks/types.ts`、`src/hooks/chain.ts`

- `AsyncHook` 接口**新增必填字段** `bestEffort: boolean`
- `BaseAsyncHook` 构造函数签名（第 5 参）：

```ts
constructor(
  name: string,
  hookType: HookType,
  priority: number = 0,
  timeoutMs: number = 5000,
  bestEffort: boolean = false,   // 新增
)
```

- `HookContext` 新增可选 `emit?: (impulse, targetQueueId) => Promise<boolean>`

**适配**：自定义实现 `AsyncHook` 接口（非继承 `BaseAsyncHook`）的类**必须补充 `bestEffort` 字段**，否则类型错误。

### 3.9 动态队列参数修复

文件：`src/core/router.ts`（`routeMessage`）

```ts
// 旧：enableWal 被误当作 autoExpand 传入
new AsyncSynapticQueue(targetQueueId, 1000, this.enableWal);
// 新：
new AsyncSynapticQueue(targetQueueId, 1000, true);
```

---

## 4. 新能力（可选启用）

### 4.1 每跳耗时精确追踪

文件：`src/core/message.ts`

```ts
impulse.markHop('myNode');            // 手动记录一跳（运行时自动记录入队/出队/处理/路由）
impulse.hopTimings;                   // [{ node, ts }]，两两相减即得每跳耗时
impulse.getEndToEndDuration();        // 端到端耗时 = 末跳 - 创建时间
NeuralImpulse.parseUuidV7Timestamp(impulse.messageId); // UUIDv7 出生时间（ms）
```

`hopTimings` 随 `toDict`/`fromDict` 序列化（WAL 恢复保留）。

### 4.2 消息守恒对账

文件：`src/core/router.ts`

```ts
const report = router.getConservationReport();
// { created, finished, errored, sunk, inFlight, suspicious, balanced }
// balanced: created === finished + errored + sunk + inFlight
// suspicious: 在途超过 router.suspiciousIdleMs（默认 60s）未终结的脉冲数

const suspects = router.getSuspiciousMessages();
// [{ messageId, lastQueue, lastTs, idleMs }] —— “哪个神经管道吞了消息”排查
```

### 4.3 Hook 旁路发射（fan-out）

文件：`src/hooks/types.ts`（`HookContext.emit`）

```ts
// 在 Worker 的 pre/post/error hook 中：
async executeAsync(impulse, context) {
  // 不 await = 不阻塞主通路流转
  context.emit!(new NeuralImpulse({ actionIntent: 'Q_LIVE2D_EGRESS' }), 'Q_LIVE2D_EGRESS');
  return impulse;
}
```

### 4.4 尽力而为 Hook（best-effort）

```ts
const memoryHook = new MyMemoryHook(/* name, type, priority, timeoutMs, */ true /* bestEffort */);
// 失败/超时：结构化告警 + 继续链（不中断消息流转），适合记忆写入、遥测、生命周期登记
```

---

## 5. 升级步骤（AI 执行顺序）

1. **依赖**：按 §1.4 更新 `package.json` 与锁文件；确认 `typescript` 保持 5.9.x
2. **废弃项**：按 §2 排查并替换——删除/迁移审查逻辑（AUDIT 队列、`injectInput`、`moral_audit_prompts` 用法），改为 Agent 自定义队列
3. **行为适配**：按 §3 逐项核对——
   - 手动路由判断改用 `_manually_routed`（§3.1）
   - 自定义 `AsyncHook` 补 `bestEffort` 字段（§3.8）
   - 确认终结点 Worker 会置 `actionIntent='Done'`（触发 FINISH）
   - 确认所有消费队列通过 `router.registerQueue()` 注册（获得 onDiscard 与守恒追踪）
4. **新能力**：按 §4 按需启用
5. **验证**：见 §6

---

## 6. 验证检查清单

```bash
bun run typecheck          # 必须通过（TS 5.9 + @types/node 26）
bun test                   # 期望：102 pass / 2 skip / 0 fail（--parallel=1）
```

集成自检（临时脚本，验证后删除）：

```ts
import { CoreLiteRouter, AsyncSynapticQueue, AsyncAxonWorker, NeuralImpulse } from './src/core/index.ts';

const router = new CoreLiteRouter({ enableWal: false });
// 注册队列 → 注册 Worker → activate → 流转消息（终结点 Worker 置 actionIntent='Done'）
// 完成后：
const report = router.getConservationReport();
console.assert(report.balanced === true, '守恒等式必须成立');
console.assert(report.finished >= 1, '终结消息应登记 Q_FINISH');
```

自检通过标准：

- [ ] typecheck 0 错误
- [ ] 测试套件无新增失败
- [ ] 消息完整流转后 `getConservationReport().balanced === true`
- [ ] 手动路由场景下 `_manually_routed` 正常标记、终结点触发 FINISH
- [ ] 源码中不再出现新的 `Q_AUDIT_*` / `injectInput` 使用

---

## 7. 已知限制（非本次升级范围）

- 过期消息为"消费时检查"语义：无消费者时过期消息驻留队列，直到被消费或 `stop()`
- 直接 `asyncGet` 消费（绕过 Worker）的消息无自动归宿登记——请始终用 `AsyncAxonWorker` 子类消费以获得守恒兜底
- 动态创建的队列（`routeMessage` 对未知队列自动建队）无 WAL hook、无守恒登记（`autoExpand=true`，见 §3.9）

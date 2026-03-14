# Aethelum Core Lite - 开发指南

This file provides guidance to package.json (package.json.ai/code) when working with code in this repository.

## 常用命令

```bash
bun install              # 安装依赖
bun run typecheck        # TypeScript 类型检查 (tsc --noEmit)
bun test                 # 运行全部测试
bun test test/core/router.test.ts           # 运行单个测试文件
bun test --test-name-pattern "injectInput" # 运行匹配名称的测试
```

`bun test` 脚本为占位符，需直接使用 `bun test` 命令。

## 技术栈

- **运行时**: Bun（首选）/ Node.js
- **语言**: TypeScript 5.9+，ESM 模块（`"type": "module"`, `"module": "nodenext"`）
- **关键依赖**: Hono（Web）、Zod 4（配置校验）、uuid v7（消息 ID）

## 架构概览

### 核心消息流

```
外部输入 → CoreLiteRouter.injectInput()
         → Q_AUDIT_INPUT（输入审计）
         → Q_AUDITED_INPUT（业务处理，由用户定义的 Worker 消费）
         → Q_AUDIT_OUTPUT（输出审计）
         → Q_RESPONSE_SINK（响应终点，受安全保护）
```

Router 内置 7 个系统队列：`Q_AUDIT_INPUT`、`Q_AUDITED_INPUT`、`Q_AUDIT_OUTPUT`、`Q_RESPONSE_SINK`、`Q_ERROR`、`Q_DONE`、`Q_REFLECTION`。未注册的队列名会动态创建。

### 核心组件关系

- **CoreLiteRouter**（`src/core/router.ts`）：中枢控制器，管理所有队列和 Worker，包含路由逻辑、SINK 安全校验、动态队列创建
- **AsyncSynapticQueue**（`src/core/queue.ts`）：5 级优先级异步队列，支持 WAL 持久化（写入 `wal_data_v2/`），带超时消费者等待机制
- **AsyncAxonWorker**（`src/core/worker.ts`）：消息处理基类（模板方法模式），子类覆盖 `process()` 方法。内置 Proxied Router 自动检测子类是否手动路由，防止重复路由
- **AsyncWorkerMonitor**（`src/core/monitor.ts`）：健康监控守护进程（setInterval 轮询），0-100 健康评分，熔断隔离 + 自动恢复
- **AsyncErrorHandler**（`src/core/error_handler.ts`）：错误分类与路由，将错误脉冲发送至 `Q_ERROR`
- **NeuralImpulse**（`src/core/message.ts`）：消息载体，含 sessionId、priority（5 级）、routingHistory、TTL/过期机制

### 钩子系统（`src/hooks/`）

HookType: `PRE_PROCESS` / `POST_PROCESS` / `ERROR_HANDLER` / `TRANSFORM` / `FILTER`。AsyncHookChain 按优先级降序执行，支持超时（AbortController 通知 Hook 终止 I/O）和 Filter 拦截（返回 null）。BaseAsyncHook 为抽象基类，子类实现 `executeAsync()`。

### 子类 Worker 路由约定

子类在 `process()` 中应使用 `this.routeAndDone(impulse, targetQueue)` 路由消息，而非直接调用 `this.router.routeMessage()`。`routeAndDone()` 会自动设置 `actionIntent = 'Done'` 防止基类重复路由。

### 配置系统（`src/config/`）

Zod schema 定义（`AppConfigSchema`），从 TOML 文件加载（`config.toml`）。配置缺失时使用 schema 默认值，不抛错。分组：`system`（worker_mode、max_workers）、`monitoring`（prometheus、tracing）、`api`（metrics 端口、CORS）、`performance`（hook_timeout）。

### 监控 API（`src/api/`）

基于 Hono 的 REST API，必须设置 apiKey（Bearer token 认证）。端点：`/api/v1/health`、`/api/v1/metrics`。MetricsAPIServer 使用 `Bun.serve()` 启动。

### 自我优化模块（`src/core/self-refining/`）

- `SelfRefiningWorker`：后台 Worker，在记忆压缩后分析对话提取用户偏好
- `ConversationAnalyzer`：调用 LLM 提取偏好
- `PreferenceMerger`：合并偏好到 `.aethelum/refining.md`（带互斥锁防并发丢失更新）

### 道德审计提示词（`src/prompts/`）

`MoralAuditPrompts`：内容安全审计系统，使用凯撒密码生成随机 token 防止提示词注入。通过 `AsyncLocalStorage` 绑定每次请求的 nonce 和密文 token。`PromptBuilder`：链式构建审计提示词。

### 全局类型

- `globalThis.logRaw`：可选的全局日志函数，由应用层注入（`src/types/global.d.ts`）
- `LLMProvider` 接口：统一的 LLM 调用抽象（`src/types/index.ts`）

## 代码约定

- 所有源码 import 使用 `.js` 扩展名（ESM + nodenext 要求）
- 严格 TypeScript 模式：`strict: true`、`verbatimModuleSyntax`、`noUncheckedIndexedAccess`、`exactOptionalPropertyTypes`
- 日志使用 `console.log/error/warn`，关键流动日志同时调用 `globalThis.logRaw?.()`
- 配置校验失败抛出中文错误信息
- 测试使用 `bun:test`（describe/expect/test/beforeEach/spyOn）

## 已知问题（来自 ISSUE.md 代码审查）

1. Worker `start()` 在 ERROR/PAUSED 状态恢复时可能产生重复 runLoop
2. WAL 异步初始化竞态：首次入队时 WAL 可能尚未就绪
3. Monitor `scheduleRecovery()` 未重置 Worker 的 `internalErrorCount`，可能导致无限熔断循环
4. Monitor 的 `setInterval` 调用异步 `checkHealth()` 可能重叠执行
5. `Router.stop()` 未调用 `queue.stop()`，WAL 日志可能不会被 flush

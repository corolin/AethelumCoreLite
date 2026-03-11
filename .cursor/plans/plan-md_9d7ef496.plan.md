---
name: plan-md
overview: 为 Aethelum-Nexus-Bun 完整实现 OpenAI Chat/Responses + Anthropic Messages 三套 HTTP 协议入口，支持多模态透传与 SSE，并确保外部无法通过 tools/function/mcp 控制内部工具链；同时让 IM/Terminal 等网关也可使用统一的多模态 `ContentPart`。
todos:
  - id: contentpart-types
    content: 新增 ContentPart/MessageContent 类型并全项目导出
    status: completed
  - id: openai-chat-gw
    content: 调整 OpenAIChatGateway：多模态 content 解析 + 忽略外部 tools/function/mcp + 注入 MessageContent
    status: completed
  - id: anthropic-gw
    content: 完善 AnthropicGateway：多模态解析 + 错误 envelope 对齐 + 忽略外部工具字段
    status: completed
  - id: openai-responses-gw
    content: 新增 OpenAIResponsesGateway：/v1/responses 非流式+SSE，多模态输入支持
    status: completed
  - id: llmworker-multimodal
    content: 升级 LLMWorker/_buildMessages 支持 MessageContent，并按协议映射到 SDK 结构
    status: completed
  - id: tools-safety
    content: 实现“外部 tools 忽略 + 本地工具可用(配置开关)”策略
    status: completed
  - id: im-gateways
    content: Discord/Satori ingress 抽取附件到 ContentPart[]（Terminal 保持 string）
    status: completed
  - id: wireup-tests
    content: index.ts 接线 Responses 网关 + 增加集成测试 + typecheck/test 通过
    status: completed
isProject: false
---

# 多协议多模态网关实现计划

## 目标

- 完整支持三套 HTTP 协议入口：
  - OpenAI Chat Completions：`POST /v1/chat/completions`
  - OpenAI Responses：`POST /v1/responses`
  - Anthropic Messages：`POST /v1/messages`
- 支持多模态输入：文字、图片、音频、视频、文件；传输方式支持 **URL + JSON(base64) + multipart**。
- 支持流式：
  - OpenAI：SSE `data: {...}` + `data: [DONE]`
  - Anthropic：SSE `event:` + `data:`
- **不滥用 metadata**：复杂输入放入 `NeuralImpulse.content`，metadata 只放轻量控制/路由字段。
- **安全**：外部请求中的 `tools/functions/tool_choice/mcp` 等字段 **accept-but-ignore**，避免外部直接控制工具调用；工具能力只来自本地注册表（可配置开关）。

## 关键现状确认

- CoreLite 的 `NeuralImpulse.content` 为 `any` 且 WAL/队列用 `toDict()` JSON 序列化，允许 `ContentPart[]` 这类纯 JSON 结构。
- Nexus 当前 HTTP 网关把用户输入降级为纯文本，`LLMWorker` 的 `LLMMessage` 也默认 `content: string`，需整体升级为可携带多模态结构。

## 内部统一内容模型（全 Gateway 通用）

- 新增类型：`ContentPart` + `MessageContent = string | ContentPart[]`
- 放置位置建议：`src/types/content.ts`（或 `src/types/index.ts` 中拆分导出）
- `ContentPart` 最小集合（JSON 可序列化）：
  - `text`: `{ type: 'text', text: string }`
  - `image`: `{ type: 'image', url?: string, base64?: string, mime?: string }`
  - `audio`: `{ type: 'audio', url?: string, base64?: string, mime?: string }`
  - `video`: `{ type: 'video', url?: string, base64?: string, mime?: string }`
  - `file`: `{ type: 'file', filename?: string, url?: string, base64?: string, mime?: string }`

## HTTP 网关改造

### 1) 调整 `OpenAIChatGateway`

文件：`src/gateways/http/openai-chat-gateway.ts`

- **请求解析**：从 `messages[]` 解析出最后一个 user 的 `content`，允许为 string 或多模态数组（并支持 multipart 引用）。
- **忽略外部工具字段**：如果请求包含 `tools/functions/tool_choice/mcp/...`，只做兼容接收，不进入 `NeuralImpulse`，也不影响内部工具列表。
- **注入**：`NeuralImpulse.content` 设为 `MessageContent`，metadata 保持轻量（`protocol`, `stream_response`, `request_id`, `model`, etc）。

### 2) 完善 `AnthropicGateway`

文件：`src/gateways/http/anthropic-gateway.ts`

- **多模态解析**：解析 `messages[].content[]` 的 block，映射为内部 `ContentPart[]`。
- **错误 envelope**：与项目现有 HTTP 策略对齐（建议统一 `{ error: { message } }`）。
- **忽略外部工具字段**：如出现工具相关输入，一律忽略，不写入内部。

### 3) 新增 `OpenAIResponsesGateway`

新增文件：`src/gateways/http/openai-responses-gateway.ts`

- 路由：`POST /v1/responses`
- 输入：兼容常见 `input` 形态（string / message list / content parts），支持 URL/base64/multipart。
- 输出：实现 Responses 的最小可用响应结构 + SSE 流式（文本 delta + done）。
- 注入：与 Chat/Anthropic 一致使用 `NeuralImpulse.content`（不塞 metadata）。

### 4) 处理旧 `HTTPGateway`

文件：`src/gateways/http/http-gateway.ts`

- 标记 deprecated 或移出启动路径，避免与 `OpenAIChatGateway` 重复。

## LLMWorker / LLMCaller 升级

### 1) `LLMWorker` 支持多模态 content

文件：`src/core/llm-worker.ts`

- `_buildMessages()` 构造 `LLMMessage` 时，支持 `content` 为 `string | ContentPart[]`。
- 根据 `impulse.metadata.protocol` 或 gateway 标记，选择把内部 `ContentPart[]` 映射为：
  - OpenAI Chat message content（content array items）
  - OpenAI Responses input items
  - Anthropic content blocks

### 2) 工具安全策略

- Gateway ingress 层：忽略外部 tools/function/mcp 字段。
- `LLMWorker`：工具列表只来自本地 `ToolRegistry`，并加一个配置开关（默认启用；可按部署关闭）。
- （可选）当请求携带外部 tools 字段时，在日志里记录 `external_tools_ignored=true`，方便审计。

### 3) `LLMCaller` 允许结构化内容透传

文件：`src/core/llm-caller.ts`

- 确保 `messages` 里 `content` 为数组时不被 stringify；按 SDK 期望类型透传。
- Responses 需要时新增 `responses.create` 调用（若要真正对齐 Responses API），或由网关统一落到 `chat.completions`（取决于你对“严格对齐”的要求）。

## IM/Terminal 网关适配

- Ingress：
  - Discord/Satori：把附件/图片/语音等转换为 `ContentPart[]` 注入 `NeuralImpulse.content`。
  - Terminal：仍以纯文本 `string`。
- Egress：
  - 默认将非文本 part 转成摘要/链接；若平台支持原生附件发送可后续增强。

## 接线与启动

- 修改 `src/index.ts`：注册并启动 `OpenAIResponsesGateway`，确保路由/serve 端口一致。

## 验证

- `bun run typecheck`
- `bun test` 新增基础集成：
  - OpenAI Chat：非流式 + SSE
  - OpenAI Responses：非流式 + SSE
  - Anthropic Messages：非流式 + SSE
  - 带 tools/function/mcp 字段的请求：确认被忽略且不会触发外部控制路径


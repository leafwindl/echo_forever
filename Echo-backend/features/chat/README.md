# Chat 模块

## 1. 业务目标

负责文本对话的一轮完整编排：构建上下文、调用 LLM、保存 user/assistant 消息、更新会话摘要，并触发长期记忆抽取调度。

## 2. 核心业务流程

1. 接收聊天请求，解析当前用户和用户输入。
2. 校验用户身份和消息内容；空消息会被拒绝。
3. 获取当前用户的活跃会话；如果没有则创建新会话。
4. 构建模型上下文：系统提示词、相关长期记忆、会话摘要、近期聊天历史和当前消息。
5. 优先通过向量召回相关长期记忆；没有可用向量时回退到重要度列表。
6. 调用大模型生成回复。
7. 将用户消息和 AI 回复作为同一轮对话写入数据库。
8. 在消息数量达到阈值时尝试更新会话摘要；摘要失败不影响本轮回复。
9. 根据本轮对话内容判断是否需要抽取长期记忆，并在需要时创建后台任务。
10. 返回 AI 回复给前端。

## 3. 对外契约

### HTTP API

- `POST /chat/send`
  - Request: `ChatRequest`
  - Response: `ChatResponse`

### 发布的事件

- 当前无已落地事件。
- 预留事件：`ChatMessageSent`，用于表示用户消息已回复。

### 依赖的其它模块接口

- Memory 模块：召回长期记忆，并在对话结束后调度记忆抽取。
- LLM Provider：根据上下文生成 AI 回复。
- 会话仓储：获取或创建当前会话。
- 消息仓储：保存用户消息和 AI 回复。
- 记忆仓储：在上下文构建时读取长期记忆。

## 4. 数据库表

- `conversations`
- `chat_messages`
- `user_memories`
- `memory_embeddings`
- `background_jobs`

## 5. 关键配置项

- `LLM_MODEL`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `TEMPERATURE`
- `MAX_TOKENS`
- `TIMEOUT`
- `MEMORY_VECTOR_TOP_K`
- `MEMORY_VECTOR_SCORE_THRESHOLD`

## 6. 注意事项

- Application 不直接访问数据库、配置或 provider。
- 跨模块调用 Memory 时只走 Memory 模块公开接口。
- 会话摘要失败不能影响当前聊天回复。
- 长期记忆注入必须克制，避免把无关历史塞入 prompt。

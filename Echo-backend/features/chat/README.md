# Chat Feature

Chat 负责两条明确分离的交付链路：异步文字聊天与同步语音通话。两条链路复用同一个统一 Agent、会话上下文、记忆、关系和执行门禁，但不复用 HTTP 交付协议。

## 文字聊天

```text
POST /chat/messages
  -> 立即持久化用户文字或表情包
  -> 创建或追加 Chat Turn
  -> 返回 202 ACK
  -> Worker 串行运行统一 Agent
  -> 持久化一至三条文字和最多一张表情包
  -> GET /chat/events 通过 SSE 交付 typing 和 Reply Group
```

- APP 可在 Echo 处理期间继续发送文字或表情包。
- `client_message_id` 提供单条消息幂等与失败重试。
- `GET /chat/messages?before_id=...` 加载更早历史。
- `GET /chat/messages?after_id=...` 为 SSE 重连补齐遗漏消息。
- Echo 文字与表情包分别保存和展示。

## 语音通话

`POST /chat/send` 只接受：

```json
{"message": "你好", "mode": "call"}
```

- 同步运行统一 Agent，并返回 `reply` 与 `audio_urls`。
- 用户消息类型为 `voice_asr`，Echo 消息类型为 `voice_reply`。
- 通话模式不允许发送或回复表情包。
- 不支持 `/chat/send mode=chat`，也不维护旧 APK 文字聊天兼容层。

## 共同约束

- 用户身份只来自 Bearer Token。
- 同一用户的文字 Worker 与同步通话不能并行运行 Agent。
- 摘要、长期记忆和关系信号在回复持久化后更新。
- Application 只依赖 Domain Protocol；PostgreSQL、模型 Provider 和其他 feature 由 Infrastructure 适配。

# Chat Feature

Chat 负责两条明确分离的交付链路：异步文字聊天与同步语音通话。两条链路复用同一个统一 Agent、会话上下文、记忆、关系和执行门禁，但不复用 HTTP 交付协议。

## 文字聊天

```text
POST /chat/messages
  -> 立即持久化用户文字或表情包
  -> 创建或追加 Chat Turn
  -> 返回 202 ACK
  -> Worker 串行运行统一 Agent
  -> 按自然段持久化文字（通常一至三条，安全上限六条）和最多一张表情包
  -> GET /chat/events 通过 SSE 交付 typing 和 Reply Group
```

- APP 可在 Echo 处理期间继续发送文字或表情包。
- `client_message_id` 提供单条消息幂等与失败重试。
- `GET /chat/messages?before_id=...` 加载更早历史。
- `GET /chat/messages?after_id=...` 为 SSE 重连补齐遗漏消息。
- Echo 文字与表情包分别保存和展示。
- 自然换行表达独立气泡，没有最低分段字数或必须达到的气泡数量；代码、列表、表格和多行引用保持完整。
- 闲聊信息量由人格与对话策略控制；长自然段仅在安全的句子边界兜底拆分，六条是交付保护上限。
- 表情包由本轮表达意图与语境决定，不再按累计轮数进入优先发送窗口；保留防连续刷图与重复选图的冷却。
- 文字可偶尔使用颜文字；文字“抱抱”不会再被当成真实身体动作删除。
- 首条内容立即显示，后续间隔随对应文本长度变化，整组额外等待不超过三秒；客户端继续读取现有 `message_delays_ms`。

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

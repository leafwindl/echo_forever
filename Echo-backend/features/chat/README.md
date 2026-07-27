# Chat Feature

Chat 负责一轮完整对话：构建上下文、调用 LLM、保存消息、更新摘要、调度记忆和关系事件，并在电话模式请求 TTS。

## 契约

`POST /chat/send` 只接受：

```json
{"message": "你好", "mode": "chat"}
```

- `mode=chat`：即时通讯文字表达，消息类型为 `text`，不合成语音。
- `mode=call`：口语化短句表达，消息类型为 `voice_asr` / `voice_reply`，返回 `audio_urls`。
- 用户身份只来自 Bearer Token。
- 响应不包含旧的单值 `audio_url`，也没有 SSE 聊天接口。

## 流程

1. Interface 校验请求、鉴权和限流。
2. Application 串行保护同一用户的一轮请求。
3. Context Builder 按安全、产品人格、自然对话、渠道、关系、用户偏好、长期记忆、摘要、历史的顺序组装上下文。
4. LLM 生成完整回复；自然度规则失败时只重写一次。
5. 同一事务语义中保存用户和 Echo 消息。
6. 更新会话摘要，调度记忆抽取并记录关系信号。
7. 电话模式调用 Voice；TTS 失败时仍返回已保存的文字。

Application 仅依赖 Domain Protocol。PostgreSQL、模型 Provider 和其它 feature 均由 Infrastructure 适配。

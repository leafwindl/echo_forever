# Echo v0.2 第四阶段测试文档
> 阶段：5. 会话摘要
> 目标：验证长对话会被压缩进 `conversations.summary`，并由 Context Builder 注入后续 prompt，避免上下文无限增长

***

## 1. 本阶段交付范围

本阶段完成以下能力：

- `conversations` 表支持 `summary_message_id`
- Chat Service 会为每轮对话绑定一个 active `conversation_id`
- 新增 `services/conversation_summary.py`
- 每轮对话落库后，摘要服务按阈值判断是否需要更新会话摘要
- Context Builder 会读取 `conversations.summary`
- 如果摘要存在，Context Builder 会把摘要作为 system 消息注入 prompt
- 最近历史只读取 `summary_message_id` 之后的消息，避免摘要覆盖过的旧消息重复进入 prompt

本阶段不做：

- 结构化长期记忆抽取
- 记忆列表和删除接口
- 向量检索
- 前端会话列表 UI

***

## 2. 关键代码路径

### 2.1 普通对话

```text
POST /chat/send 或 POST /voice/reply
  -> services.chat.generate_chat_reply()
  -> services.memory.get_or_create_active_conversation()
  -> services.context_builder.build_chat_context()
  -> llm_client.request_llm()
  -> services.memory.add_message(user)
  -> services.memory.add_message(assistant)
  -> services.conversation_summary.maybe_update_conversation_summary()
```

### 2.2 摘要注入

```text
build_chat_context()
  -> get_conversation_summary()
  -> get_history(after_message_id=summary_message_id)
  -> messages:
      1. system prompt
      2. 当前会话摘要（如果存在）
      3. 摘要之后的最近历史
      4. 当前用户消息
```

### 2.3 摘要更新

```text
maybe_update_conversation_summary()
  -> 读取 summary_message_id 之后的未摘要消息
  -> 未摘要消息数量超过阈值才调用 LLM
  -> 保留最近若干条原文
  -> 将更早的消息合并进 summary
  -> 更新 conversations.summary 和 conversations.summary_message_id
```

***

## 3. 测试用例

### 用例 1：数据库迁移字段存在

**操作**

启动后端后检查 SQLite：

```sql
PRAGMA table_info(conversations);
```

**预期**

`conversations` 表包含：

- `summary`
- `summary_message_id`

### 用例 2：Chat Service 自动绑定 active 会话

**操作**

调用：

```python
from services.chat import generate_chat_reply

result = await generate_chat_reply(
    user_id="dev_summary_user",
    message="你好 Echo"
)
```

**预期**

- `result.conversation_id` 不为空
- `conversations` 表中存在该 `conversation_id`
- `chat_messages` 中该轮 user/assistant 消息都带有同一个 `conversation_id`

### 用例 3：摘要未达阈值时不更新

**操作**

同一个 `user_id` 连续发送少量消息，数量低于 `SUMMARY_TRIGGER_MESSAGES`。

**预期**

- `conversations.summary` 仍为空
- `summary_message_id = 0`
- 当前对话行为不受影响

### 用例 4：长对话触发摘要

**操作**

同一个 `user_id` 连续进行超过 `SUMMARY_TRIGGER_MESSAGES` 条消息的对话。

**预期**

- `conversations.summary` 被写入非空文本
- `summary_message_id > 0`
- `summary_message_id` 对应的是被摘要覆盖的最后一条消息 ID
- 最近若干条消息仍保留为原文，没有被摘要边界覆盖

### 用例 5：Context Builder 注入摘要

**操作**

在已有摘要的会话中调用：

```python
from services.context_builder import build_chat_context

context = build_chat_context(
    user_id="dev_summary_user",
    user_message="我们刚才聊到哪了？",
    conversation_id="你的 conversation_id"
)
```

**预期**

- `context.conversation_summary` 非空
- `context.messages[0].role = system`
- `context.messages` 中包含一条内容以 `当前会话摘要` 开头的 system 消息
- `context.history_messages` 只包含 `summary_message_id` 之后的最近历史

### 用例 6：摘要失败不影响当前回复

**操作**

模拟摘要服务失败，例如临时让摘要 LLM 请求失败。

**预期**

- `/chat/send` 或 `/voice/reply` 当前回复仍正常返回
- 后端日志记录 `Conversation summary update failed`
- 不应因为摘要失败导致用户消息发送失败

### 用例 7：文本和语音共用摘要能力

**操作**

1. 通过文本连续对话触发摘要
2. 再通过 `/voice/reply` 发送问题：“我们前面一直在聊什么？”

**预期**

- `/voice/reply` 使用同一个 active conversation
- Context Builder 同样注入会话摘要
- 语音链路返回结构仍为 `{ reply, audio_url }`

***

## 4. 代码层验收

### 4.1 Context Builder 接入摘要

```bash
rg "get_conversation_summary|conversation_summary|summary_message_id" Echo-backend/services/context_builder.py
```

预期：

- 能看到摘要读取和注入逻辑

### 4.2 Chat Service 接入摘要更新

```bash
rg "maybe_update_conversation_summary|get_or_create_active_conversation|conversation_id" Echo-backend/services/chat.py
```

预期：

- 能看到 active 会话绑定和摘要更新逻辑

### 4.3 语法检查

```bash
python -m py_compile Echo-backend/main.py Echo-backend/services/chat.py Echo-backend/services/context_builder.py Echo-backend/services/conversation_summary.py Echo-backend/services/memory.py
```

预期：

- 无语法错误

***

## 5. 本阶段通过标准

第四阶段验收通过需要同时满足：

- `conversations.summary_message_id` 存在
- 每轮对话都有明确 `conversation_id`
- 长对话超过阈值后会更新 `conversations.summary`
- Context Builder 会把摘要注入 prompt
- 已摘要消息不会继续作为普通历史重复塞进 prompt
- 摘要更新失败不会影响当前用户回复
- `/chat/send` 和 `/voice/reply` 返回结构保持不变

***

## 6. 后续阶段入口

第四阶段完成后，可以进入第五阶段：

```text
结构化长期记忆
```

下一阶段会在每轮对话后抽取稳定事实、偏好、目标、关系等内容，写入 `user_memories`，并逐步接入 Context Builder。

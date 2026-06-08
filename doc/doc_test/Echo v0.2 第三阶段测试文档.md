# Echo v0.2 第三阶段测试文档
> 阶段：4. Context Builder
> 目标：验证上下文拼装逻辑已从 Chat Service 中独立出来，并保持现有文本/语音对话行为不变
Chat Service 管“怎么完成一轮对话”，Context Builder 管“这一轮对话给模型看什么”。这样后续拓展会很干净。
***

## 1. 本阶段交付范围

本阶段完成以下能力：

- 新增 `services/context_builder.py`
- 将“系统 Prompt + 最近历史 + 当前用户消息”的上下文拼装逻辑从 `services/chat.py` 迁移到 Context Builder
- `services/chat.py` 不再直接读取历史、不再直接引用系统 Prompt
- `services/chat.py` 只负责编排对话流程：
  - 校验输入
  - 调用 Context Builder
  - 调用 LLM
  - 写入用户和助手消息
- 当前 prompt 行为保持不变

本阶段不做：

- 会话摘要
- 结构化长期记忆注入
- 向量召回
- token 预算管理

这些能力会在后续阶段继续接入 `build_chat_context()`。

***

## 2. 关键代码路径

### 2.1 文本聊天

```text
POST /chat/send
  -> main.chat_send()
  -> services.chat.generate_chat_reply()
  -> services.context_builder.build_chat_context()
  -> services.memory.get_history()
  -> llm_client.request_llm()
  -> services.memory.add_message(user)
  -> services.memory.add_message(assistant)
```

### 2.2 语音回复

```text
POST /voice/reply
  -> main.voice_reply()
  -> services.chat.generate_chat_reply()
  -> services.context_builder.build_chat_context()
  -> llm_client.request_llm()
  -> TTS
  -> 返回 reply + audio_url
```

### 2.3 当前 Context Builder 输出

当前阶段 `build_chat_context()` 返回：

```text
ChatContext
  - messages
  - history_messages
```

`messages` 当前结构仍为：

```text
1. system prompt
2. 最近 N 条历史消息
3. 当前用户消息
```

***

## 3. 测试用例

### 用例 1：Context Builder 基础结构

**操作**

调用：

```python
from services.context_builder import build_chat_context

context = build_chat_context(
    user_id="dev_test_user_context",
    user_message="你好 Echo"
)
```

**预期**

- `context.messages` 是列表
- 第一条消息 `role = system`
- 最后一条消息 `role = user`
- 最后一条消息 `content = "你好 Echo"`
- `context.history_messages` 是列表

### 用例 2：Chat Service 使用 Context Builder

**代码层检查**

```bash
rg "build_chat_context" Echo-backend/services/chat.py
```

**预期**

- `services/chat.py` 中存在 `build_chat_context`

```bash
rg "get_history|settings.system_prompt|MAX_HISTORY_MESSAGES" Echo-backend/services/chat.py
```

**预期**

- 无结果
- 说明 Chat Service 不再直接拼上下文

### 用例 3：文本接口行为保持不变

**请求**

```http
POST /chat/send
Content-Type: application/json
```

```json
{
  "user_id": "dev_test_user_context",
  "message": "今天继续测试第三阶段"
}
```

**预期**

- 返回 200
- 返回体仍为 `{ "reply": "..." }`
- `chat_messages` 新增 user 和 assistant 两条记录
- `message_type` 仍为 `text`

### 用例 4：语音回复行为保持不变

**请求**

```http
POST /voice/reply
Content-Type: application/json
```

```json
{
  "user_id": "dev_test_user_context_voice",
  "message": "我想听你回复我"
}
```

**预期**

- 返回 200
- 返回体仍包含：
  - `reply`
  - `audio_url`
- 用户消息写入 `message_type = voice_asr`
- 助手消息写入 `message_type = voice_reply`

### 用例 5：历史上下文仍然生效

**操作**

1. 用户发送：“以后叫我小安”
2. 同一个 `user_id` 再发送：“你还记得怎么叫我吗？”

**预期**

- Context Builder 会通过 `get_history()` 读取最近历史
- 第二轮请求的 `messages` 中包含第一轮历史
- Echo 有机会结合短期历史回答“小安”

***

## 4. 代码层验收

### 4.1 Chat Service 职责边界

执行：

```bash
rg "get_history|settings.system_prompt|MAX_HISTORY_MESSAGES|MAX_ROUNDS" Echo-backend/services/chat.py
```

预期：

- 无结果

### 4.2 Context Builder 职责边界

执行：

```bash
rg "get_history|settings.system_prompt|MAX_HISTORY_MESSAGES|MAX_ROUNDS" Echo-backend/services/context_builder.py
```

预期：

- 能看到这些逻辑集中在 `context_builder.py`

### 4.3 语法检查

执行：

```bash
python -m py_compile Echo-backend/main.py Echo-backend/services/chat.py Echo-backend/services/context_builder.py
```

预期：

- 无语法错误

***

## 5. 本阶段通过标准

第三阶段验收通过需要同时满足：

- `services/context_builder.py` 存在
- `build_chat_context()` 是唯一负责基础上下文拼装的入口
- `services/chat.py` 不再直接读取历史或系统 Prompt
- `/chat/send` 返回结构不变
- `/voice/reply` 返回结构不变
- 文本和语音仍共用 `generate_chat_reply()`
- 第一阶段用户隔离和第二阶段统一 Chat Service 能力保持有效

***

## 6. 后续阶段入口

第三阶段完成后，可以进入第四阶段：

```text
会话摘要
```

第四阶段建议优先把 `conversations.summary` 接入 `build_chat_context()`：

```text
系统 Prompt
当前会话摘要
最近上下文
当前用户消息
```

这样长对话不会只依赖最近 N 条原文历史。

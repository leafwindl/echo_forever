# Echo v0.2 第二阶段测试文档
> 阶段：3. 文本和语音链路统一到 Chat Service
> 目标：验证 `/chat/send` 和 `/voice/reply` 共用同一套对话生成、短期历史读取和消息落库逻辑

***

## 1. 本阶段交付范围

本阶段完成以下能力：

- 新增 `services/chat.py`
- 将短期上下文窗口配置移动到 Chat Service
- 将“读取历史 -> 拼接 messages -> 调用 LLM -> 写入用户和助手消息”统一封装
- `/chat/send` 调用 Chat Service 获取文本回复
- `/voice/reply` 调用同一个 Chat Service 获取文本回复，再执行 TTS
- 文本和语音消息写入同一张 `chat_messages` 表
- 语音链路通过 `message_type` 标记为 `voice_asr` 和 `voice_reply`

本阶段不做：

- 会话摘要
- 长期记忆抽取
- 向量检索
- 记忆管理接口

这些能力会在后续阶段接入 Chat Service 或 Context Builder。

***

## 2. 关键代码路径

### 2.1 文本聊天

```text
POST /chat/send
  -> main.chat_send()
  -> services.chat.generate_chat_reply()
  -> services.chat.build_basic_messages()
  -> llm_client.request_llm()
  -> services.memory.add_message(user)
  -> services.memory.add_message(assistant)
```

### 2.2 语音聊天

```text
POST /voice/asr
  -> 腾讯 ASR
  -> 返回 user_text

POST /voice/reply
  -> main.voice_reply()
  -> services.chat.generate_chat_reply()
  -> llm_client.request_llm()
  -> services.memory.add_message(user, message_type='voice_asr')
  -> services.memory.add_message(assistant, message_type='voice_reply')
  -> MiniMax/Edge TTS
  -> 返回 reply + audio_url
```

### 2.3 当前基础上下文结构

第二阶段仍保持 v0.1 行为：

```text
系统 Prompt
最近 N 条历史消息
当前用户消息
```

后续第三阶段会把 `build_basic_messages()` 替换或升级为正式的 `Context Builder`。

***

## 3. 测试用例

### 用例 1：文本接口行为保持不变

**请求**

```http
POST /chat/send
Content-Type: application/json
```

```json
{
  "user_id": "dev_test_user_a",
  "message": "你好 Echo"
}
```

**预期**

- 返回 200
- 返回体包含 `reply`
- `reply` 为字符串
- `chat_messages` 中新增两条记录：
  - `role = user`
  - `role = assistant`
- 两条记录的 `message_type` 均为 `text`

### 用例 2：文本空消息校验

**请求**

```json
{
  "user_id": "dev_test_user_a",
  "message": "   "
}
```

**预期**

- 返回 400
- 不写入新的聊天记录

### 用例 3：语音回复接口共用 Chat Service

**请求**

```http
POST /voice/reply
Content-Type: application/json
```

```json
{
  "user_id": "dev_test_user_voice",
  "message": "我今天有点累"
}
```

**预期**

- 返回 200
- 返回体包含：
  - `reply`
  - `audio_url`
- `chat_messages` 中新增两条记录：
  - 用户消息 `message_type = voice_asr`
  - 助手消息 `message_type = voice_reply`

### 用例 4：文本和语音共享短期历史

**操作**

1. 文本发送：“以后叫我小安”
2. 语音识别后调用 `/voice/reply`：“你还记得怎么叫我吗？”

**预期**

- `/voice/reply` 会读取同一个 `user_id` 的历史消息
- Echo 有机会结合文本历史回复“小安”
- 说明文本和语音没有再走两套独立上下文

### 用例 5：不同用户历史隔离仍然有效

**操作**

1. 用户 A 通过文本发送：“我叫小安”
2. 用户 B 通过语音或文本问：“你知道我叫什么吗？”

**预期**

- 用户 B 的 Chat Service 只读取 B 的历史
- 不应使用用户 A 的消息

***

## 4. 代码层验收

### 4.1 `main.py` 不应再直接处理核心对话流程

搜索：

```bash
rg "request_llm|get_history|add_message|MAX_HISTORY_MESSAGES|MAX_ROUNDS" Echo-backend/main.py
```

预期：

- 无结果
- 这些逻辑应集中在 `services/chat.py`

### 4.2 Chat Service 可单独编译

```bash
python -m py_compile Echo-backend/main.py Echo-backend/services/chat.py
```

预期：

- 无语法错误

***

## 5. 本阶段通过标准

第二阶段验收通过需要同时满足：

- 文本和语音回复都调用 `generate_chat_reply()`
- `/chat/send` 返回结构保持 `{ reply }`
- `/voice/reply` 返回结构保持 `{ reply, audio_url }`
- 文本消息落库 `message_type = text`
- 语音消息落库 `message_type = voice_asr / voice_reply`
- `main.py` 不再直接拼接 messages、不再直接调用 LLM、不再直接写聊天消息
- 第一阶段的用户隔离能力保持有效

***

## 6. 后续阶段入口

第二阶段完成后，可以进入第三阶段：

```text
Context Builder
```

第三阶段重点是把 `build_basic_messages()` 从“系统 Prompt + 最近历史 + 当前消息”升级为：

```text
系统 Prompt
用户画像
长期记忆
会话摘要
最近上下文
当前用户消息
```

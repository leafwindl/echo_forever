# Echo v0.2 第五阶段测试文档
> 阶段：结构化长期记忆
> 目标：验证 Echo 能从对话中抽取稳定事实、偏好、目标、关系等长期记忆，写入 `user_memories`，并由 Context Builder 注入后续 prompt

***

## 1. 本阶段交付范围

本阶段完成以下能力：

- 新增 `services/memory_extractor.py`
- 每轮对话落库后，Chat Service 先做规则门控，只在命中长期记忆信号时调度抽取
- 长期记忆抽取以后台异步任务执行，不阻塞当前用户回复
- 长期记忆抽取支持独立低成本模型配置：`MEMORY_EXTRACTION_MODEL`
- LLM 抽取结果必须是 JSON，后端负责解析、校验和过滤
- 支持 `create`、`update`、`deactivate`、`ignore` 四类动作
- 支持按 `user_id` 读取 active 长期记忆
- 支持重复记忆刷新更新时间，不重复写入
- Context Builder 会把 active 长期记忆注入 prompt

本阶段不做：

- 向量 embedding 和语义召回
- 记忆管理 API
- 记忆管理前端
- 复杂后台任务队列

***

## 2. 关键代码路径

### 2.1 对话后抽取长期记忆

```text
POST /chat/send 或 POST /voice/reply
  -> services.chat.generate_chat_reply()
  -> services.context_builder.build_chat_context()
  -> llm_client.request_llm()
  -> services.memory.add_message(user)
  -> services.memory.add_message(assistant)
  -> services.conversation_summary.maybe_update_conversation_summary()
  -> services.memory_extractor.schedule_memory_extraction()
      -> should_extract_memory()
      -> 命中规则后后台执行 extract_and_store_memories()
      -> services.memory.add_user_memory() / update_user_memory() / deactivate_user_memory()
```

### 2.2 长期记忆注入

```text
build_chat_context()
  -> list_user_memories(user_id, status='active')
  -> messages:
      1. system prompt
      2. 用户长期记忆（如果存在）
      3. 当前会话摘要（如果存在）
      4. 摘要之后的最近历史
      5. 当前用户消息
```

***

## 3. 测试用例

### 用例 1：抽取并写入称呼记忆

**操作**

用户发送：

```text
以后叫我小安吧
```

模拟或真实 LLM 抽取返回：

```json
{
  "memories": [
    {
      "action": "create",
      "target_memory_id": "",
      "memory_type": "profile",
      "content": "用户希望 Echo 称呼自己为小安。",
      "confidence": 0.95,
      "importance": 5
    }
  ]
}
```

**预期**

- `should_extract_memory()` 返回 `should_extract = True`
- `ChatTurnResult.memory_extraction_scheduled = True`
- `user_memories` 新增一条 active 记忆
- `memory_type = profile`
- `content` 包含“小安”
- `source_message_id` 指向用户本轮消息 ID

### 用例 1.1：普通闲聊不触发抽取 LLM

**操作**

用户发送：

```text
今天有点累
```

**预期**

- `should_extract_memory()` 返回 `should_extract = False`
- `ChatTurnResult.memory_extraction_scheduled = False`
- 不调用记忆抽取 LLM
- 不写入新的 `user_memories`

### 用例 2：重复记忆不重复写入

**操作**

同一个用户多次表达：

```text
你以后还是叫我小安
```

**预期**

- 不新增重复内容的 active 记忆
- 已有记忆的 `updated_at` 被刷新
- 后台任务日志中 `updated > 0`

### 用例 3：用户纠正记忆

**操作**

用户先说：

```text
以后叫我小安
```

之后又说：

```text
我改主意了，以后叫我阿叶
```

LLM 应返回 `update`，并带上旧记忆的 `target_memory_id`。

**预期**

- 旧记忆被更新为“用户希望 Echo 称呼自己为阿叶”
- 后续 Context Builder 不再注入“小安”作为 active 称呼

### 用例 4：用户要求忘记

**操作**

用户说：

```text
刚才那个称呼不用记了
```

LLM 应返回 `deactivate`，并带上对应 `target_memory_id`。

**预期**

- 对应记忆 `status = inactive`
- Context Builder 不再注入该记忆

### 用例 5：低置信度或非法类型被忽略

**操作**

模拟 LLM 返回：

```json
{
  "memories": [
    {
      "action": "create",
      "memory_type": "unknown",
      "content": "用户可能喜欢咖啡。",
      "confidence": 0.4,
      "importance": 3
    }
  ]
}
```

**预期**

- 不写入 `user_memories`
- `MemoryExtractionResult.ignored > 0`

### 用例 6：Context Builder 注入长期记忆

**操作**

已有 active 记忆后调用：

```python
from services.context_builder import build_chat_context

context = build_chat_context(
    user_id="dev_memory_user",
    user_message="你还记得怎么叫我吗？",
)
```

**预期**

- `context.long_term_memories` 非空
- `context.messages` 中包含一条以 `用户长期记忆` 开头的 system 消息
- inactive 记忆不会被注入

### 用例 7：文本和语音共用长期记忆

**操作**

1. 用户通过 `/voice/reply` 说：“我最近在准备考研”
2. 用户通过 `/chat/send` 问：“我最近为什么压力这么大？”

**预期**

- 语音链路写入的长期记忆属于同一个 `user_id`
- 文本链路的 Context Builder 能读取并注入这条长期记忆

### 用例 8：记忆抽取失败不影响当前回复

**操作**

模拟 `extract_and_store_memories()` 抛出异常。

**预期**

- `/chat/send` 或 `/voice/reply` 当前回复仍正常返回
- 后端日志记录 `Background memory extraction failed`
- 不应因为记忆抽取失败导致用户消息发送失败

### 用例 9：低成本模型配置生效

**操作**

在 `.env` 中配置：

```env
MEMORY_EXTRACTION_MODEL=gpt-4o-mini
MEMORY_EXTRACTION_TEMPERATURE=0.1
MEMORY_EXTRACTION_MAX_TOKENS=400
```

触发一次命中规则的长期记忆抽取。

**预期**

- 主对话仍使用 `LLM_MODEL`
- 记忆抽取请求使用 `MEMORY_EXTRACTION_MODEL`
- 记忆抽取输出长度受 `MEMORY_EXTRACTION_MAX_TOKENS` 控制

***

## 4. 代码层验收

### 4.1 Chat Service 接入后台记忆抽取

```bash
rg "schedule_memory_extraction|memory_extraction_scheduled|memory_extraction_gate_reason" Echo-backend/services/chat.py
```

预期：

- 能看到对话落库后的后台调度逻辑

### 4.2 Memory Service 支持长期记忆管理基础函数

```bash
rg "list_user_memories|get_user_memory|update_user_memory|deactivate_user_memory|touch_user_memory" Echo-backend/services/memory.py
```

预期：

- 能看到 active 记忆读取、更新、失效和重复刷新逻辑

### 4.3 Context Builder 注入长期记忆

```bash
rg "list_user_memories|long_term_memories|用户长期记忆" Echo-backend/services/context_builder.py
```

预期：

- 能看到长期记忆读取和 system message 注入逻辑

### 4.4 语法检查

```bash
python -B -m py_compile Echo-backend/main.py Echo-backend/llm_client.py Echo-backend/config.py Echo-backend/services/chat.py Echo-backend/services/context_builder.py Echo-backend/services/conversation_summary.py Echo-backend/services/memory_extractor.py Echo-backend/services/memory.py
```

预期：

- 无语法错误

***

## 5. 本阶段通过标准

第五阶段验收通过需要同时满足：

- 对话后会尝试抽取结构化长期记忆
- 普通闲聊不会调用记忆抽取 LLM
- 记忆抽取以后台异步任务运行，不阻塞当前回复
- 记忆抽取可以使用独立低成本模型配置
- 只有合法类型、内容非空、置信度足够的记忆会入库
- 重复记忆不会重复写入
- 用户纠正信息时，旧记忆能被更新或失效
- Context Builder 会注入 active 长期记忆
- 文本和语音链路共享同一套长期记忆
- 记忆抽取失败不会影响当前用户回复

***

## 6. 后续阶段入口

第五阶段完成后，可以进入下一阶段：

```text
记忆管理接口
```

下一阶段会开放 `/memory/list`、删除单条记忆、清空长期记忆等接口，让用户能查看和控制 Echo 记住的内容。

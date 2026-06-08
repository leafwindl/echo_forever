# Echo v0.2 第六阶段测试文档
> 阶段：记忆管理接口
> 目标：验证用户可以查看、删除和清空 Echo 的长期记忆，且删除后的记忆不会再进入 Context Builder

***

## 1. 本阶段交付范围

本阶段完成以下能力：

- 新增 `GET /memory/list`
- 新增 `DELETE /memory/{memory_id}`
- 新增 `POST /memory/clear`
- 删除和清空均采用软删除，记忆状态标记为 `deleted`
- 所有记忆操作都必须带 `user_id`
- 所有查询和更新都按 `user_id` 隔离，避免跨用户访问或删除
- Context Builder 仍然只读取 `active` 长期记忆

本阶段不做：

- 前端记忆管理页
- 向量库同步删除
- 原始聊天记录删除
- 用户全部数据删除

***

## 2. 接口说明

### 2.1 获取长期记忆列表

```http
GET /memory/list?user_id=dev_user&status=active&limit=50
```

参数：

- `user_id`：必填，当前用户 ID
- `status`：可选，默认 `active`，支持 `active`、`inactive`、`deleted`、`all`
- `limit`：可选，默认 `50`，后端限制在 `1` 到 `200`

返回：

```json
{
  "memories": [
    {
      "memory_id": "mem_xxx",
      "memory_type": "profile",
      "content": "用户希望 Echo 称呼自己为小安。",
      "source_message_id": 123,
      "confidence": 0.95,
      "importance": 5,
      "status": "active",
      "created_at": "2026-06-08 10:00:00",
      "updated_at": "2026-06-08 10:00:00",
      "expires_at": null
    }
  ],
  "count": 1
}
```

### 2.2 删除单条长期记忆

```http
DELETE /memory/mem_xxx?user_id=dev_user
```

返回：

```json
{
  "memory_id": "mem_xxx",
  "status": "deleted"
}
```

### 2.3 清空长期记忆

```http
POST /memory/clear
Content-Type: application/json

{
  "user_id": "dev_user"
}
```

返回：

```json
{
  "cleared_count": 3
}
```

***

## 3. 测试用例

### 用例 1：查看 active 长期记忆

**操作**

先写入一条 active 记忆，然后调用：

```http
GET /memory/list?user_id=dev_memory_user
```

**预期**

- HTTP 200
- 返回 `count > 0`
- 返回项只包含当前 `user_id` 的 active 记忆
- 不返回其他用户的记忆

### 用例 2：按状态查看记忆

**操作**

分别调用：

```http
GET /memory/list?user_id=dev_memory_user&status=inactive
GET /memory/list?user_id=dev_memory_user&status=deleted
GET /memory/list?user_id=dev_memory_user&status=all
```

**预期**

- `inactive` 只返回 inactive 记忆
- `deleted` 只返回 deleted 记忆
- `all` 返回该用户所有状态的长期记忆

### 用例 3：非法状态返回 400

**操作**

```http
GET /memory/list?user_id=dev_memory_user&status=unknown
```

**预期**

- HTTP 400
- 返回 `Invalid memory status`

### 用例 4：删除单条记忆

**操作**

```http
DELETE /memory/mem_xxx?user_id=dev_memory_user
```

**预期**

- HTTP 200
- 返回 `status = deleted`
- `user_memories` 中该记忆状态变为 `deleted`
- `GET /memory/list?user_id=dev_memory_user` 不再返回该记忆

### 用例 5：不能删除其他用户的记忆

**操作**

用户 A 有记忆 `mem_a`，用户 B 调用：

```http
DELETE /memory/mem_a?user_id=user_b
```

**预期**

- HTTP 404
- 用户 A 的 `mem_a` 状态不变

### 用例 6：清空长期记忆

**操作**

```http
POST /memory/clear
Content-Type: application/json

{
  "user_id": "dev_memory_user"
}
```

**预期**

- HTTP 200
- 返回 `cleared_count`
- 该用户所有非 deleted 长期记忆都变为 `deleted`
- 原始聊天记录 `chat_messages` 不受影响
- 会话摘要 `conversations.summary` 不受影响

### 用例 7：删除后不再注入 Context Builder

**操作**

1. 用户有一条 active 记忆：“用户希望 Echo 称呼自己为小安”
2. 删除这条记忆
3. 调用：

```python
from services.context_builder import build_chat_context

context = build_chat_context(
    user_id="dev_memory_user",
    user_message="你还记得怎么叫我吗？",
)
```

**预期**

- `context.long_term_memories` 不包含已删除记忆
- `context.messages` 中的 `用户长期记忆` 不包含“小安”

### 用例 8：缺少 user_id 返回 400

**操作**

```http
GET /memory/list?user_id=
POST /memory/clear {"user_id": ""}
DELETE /memory/mem_xxx?user_id=
```

**预期**

- HTTP 400
- 不修改任何记忆

***

## 4. 代码层验收

### 4.1 Memory Service 支持用户主动删除和清空

```bash
rg "delete_user_memory|clear_user_memories" Echo-backend/services/memory.py
```

预期：

- 能看到单条软删除和批量软删除逻辑

### 4.2 FastAPI 暴露记忆管理接口

```bash
rg "memory_list|memory_delete|memory_clear|/memory/list|/memory/clear" Echo-backend/main.py
```

预期：

- 能看到三个记忆管理接口

### 4.3 语法检查

```bash
python -B -m py_compile Echo-backend/main.py Echo-backend/llm_client.py Echo-backend/config.py Echo-backend/services/chat.py Echo-backend/services/context_builder.py Echo-backend/services/conversation_summary.py Echo-backend/services/memory_extractor.py Echo-backend/services/memory.py
```

预期：

- 无语法错误

***

## 5. 本阶段通过标准

第六阶段验收通过需要同时满足：

- 用户可以查看自己的长期记忆
- 用户不能查看或删除其他用户的长期记忆
- 删除单条记忆后，该记忆不会再被 Context Builder 注入
- 清空长期记忆不会删除原始聊天记录
- 清空长期记忆不会清空会话摘要
- 缺少 `user_id` 或非法参数会返回明确错误

***

## 6. 后续阶段入口

第六阶段完成后，可以进入下一阶段：

```text
记忆管理前端
```

下一阶段会在小程序中增加记忆管理入口，调用本阶段的 `/memory/list`、`DELETE /memory/{memory_id}` 和 `/memory/clear`。

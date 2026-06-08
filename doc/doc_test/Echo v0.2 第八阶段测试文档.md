# Echo v0.2 第八阶段测试文档
> 阶段：embedding 和向量检索
> 目标：验证 Echo 只把与当前问题相关的长期记忆注入 prompt，避免把所有长期记忆都塞给模型

***

## 1. 本阶段交付范围

本阶段完成以下能力：

- 新增 `services/embedding_client.py`
- 新增 `services/vector_store.py`
- 新增 `memory_embeddings` 表
- 对 `user_memories.content` 生成 embedding
- 支持通过 `/memory/backfill-embeddings` 给旧阶段已有 active 记忆补齐 embedding
- 记忆新增或更新时写入/刷新 embedding
- 记忆删除、失效或清空时删除对应 embedding
- Context Builder 改为异步函数，优先按当前用户消息召回相关长期记忆
- 向量检索失败或没有 embedding 时，回退到重要度排序的 active 记忆
- 当已有 embedding 但本轮没有相关命中时，不注入无关长期记忆

本阶段不做：

- 文档知识库 RAG
- 原始聊天记录向量化
- Chroma 或 pgvector 部署
- 前端向量调试 UI

***

## 2. 关键代码路径

### 2.1 记忆写入后生成向量

```text
services.memory_extractor.extract_and_store_memories()
  -> add_user_memory() / update_user_memory()
  -> services.vector_store.upsert_memory_embedding()
  -> services.embedding_client.create_embedding()
  -> memory_embeddings
```

### 2.2 记忆删除后移除向量

```text
DELETE /memory/{memory_id}
  -> delete_user_memory()
  -> delete_memory_embedding()

POST /memory/clear
  -> clear_user_memories()
  -> clear_memory_embeddings()
```

### 2.3 当前消息召回相关记忆

```text
services.chat.generate_chat_reply()
  -> await build_chat_context()
  -> retrieve_relevant_memories(user_id, user_message)
  -> query embedding
  -> cosine similarity
  -> top-k active memories
  -> 注入 prompt
```

### 2.4 旧记忆补 embedding

```text
POST /memory/backfill-embeddings
  -> backfill_user_memory_embeddings(user_id)
  -> 找出缺少 embedding 的 active 记忆
  -> 逐条生成 embedding
  -> 写入 memory_embeddings
```

***

## 3. 配置项

`.env` 可选配置：

```env
EMBEDDING_API_KEY=你的 embedding 服务 Key
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
MEMORY_VECTOR_TOP_K=5
MEMORY_VECTOR_SCORE_THRESHOLD=0.25
```

说明：

- `EMBEDDING_MODEL`：长期记忆和当前问题使用同一个 embedding 模型
- `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL`：embedding 独立配置，不默认复用聊天模型地址，避免 DeepSeek 等 chat-only 接口没有 `/embeddings`
- `MEMORY_VECTOR_TOP_K`：每轮最多召回几条长期记忆
- `MEMORY_VECTOR_SCORE_THRESHOLD`：低于该相似度的记忆不进入 prompt

***

## 4. 测试用例

### 用例 1：数据库存在 memory_embeddings 表

**操作**

启动后端后检查 SQLite：

```sql
SELECT name FROM sqlite_master WHERE type='table' AND name='memory_embeddings';
PRAGMA table_info(memory_embeddings);
```

**预期**

- 表存在
- 包含 `memory_id`
- 包含 `user_id`
- 包含 `embedding_model`
- 包含 `embedding`

### 用例 2：新增长期记忆后生成 embedding

**操作**

模拟或真实触发记忆抽取：

```text
以后叫我小安吧
```

**预期**

- `user_memories` 新增 active 记忆
- `memory_embeddings` 新增对应 `memory_id`
- `embedding_model = EMBEDDING_MODEL`
- `embedding` 为 JSON 数组

### 用例 3：更新长期记忆后刷新 embedding

**操作**

用户先说：

```text
以后叫我小安
```

之后纠正：

```text
以后叫我阿叶
```

**预期**

- 旧记忆内容被更新
- `memory_embeddings` 中同一个 `memory_id` 的 embedding 被刷新
- 不产生重复 embedding 记录

### 用例 4：删除记忆后删除 embedding

**操作**

```http
DELETE /memory/mem_xxx?user_id=dev_user
```

**预期**

- `user_memories.status = deleted`
- `memory_embeddings` 中该 `memory_id` 被删除
- 后续向量检索不会召回该记忆

### 用例 5：清空记忆后清空 embedding

**操作**

```http
POST /memory/clear
{
  "user_id": "dev_user"
}
```

**预期**

- 该用户所有长期记忆软删除
- 该用户所有 `memory_embeddings` 被删除
- 其他用户的 embedding 不受影响

### 用例 6：按当前消息召回相关记忆

**操作**

同一用户有三条长期记忆：

- 用户希望 Echo 称呼自己为小安
- 用户最近在准备考研
- 用户喜欢简洁回答

用户问：

```text
我最近为什么总是因为复习焦虑？
```

**预期**

- Context Builder 优先召回“准备考研”相关记忆
- `context.memory_retrieval_mode = vector`
- `context.long_term_memories` 不超过 `MEMORY_VECTOR_TOP_K`
- prompt 中不应无脑注入所有长期记忆

### 用例 7：已有 embedding 但没有相关命中

**操作**

用户有长期记忆：

- 用户喜欢猫

用户问：

```text
帮我想一个数据库索引方案
```

**预期**

- 如果相似度低于阈值，`context.long_term_memories` 为空
- `context.memory_retrieval_mode = vector_empty`
- prompt 不注入“用户喜欢猫”这类无关记忆

### 用例 8：没有 embedding 时回退到重要度列表

**操作**

用户有 active 长期记忆，但没有 `memory_embeddings` 记录。

**预期**

- Context Builder 回退到 `list_user_memories()`
- `context.memory_retrieval_mode = fallback_importance`
- 当前对话不因缺少 embedding 而失败

### 用例 9：旧记忆 backfill

**操作**

用户已有 active 长期记忆，但这些记忆是在 embedding 阶段之前生成的，没有向量记录。

调用：

```http
POST /memory/backfill-embeddings
Content-Type: application/json

{
  "user_id": "dev_user",
  "limit": 100
}
```

**预期**

- HTTP 200
- 返回 `backfilled_count`
- 只为当前用户 active 记忆补 embedding
- 已经有 embedding 的记忆不会重复生成
- 未配置 embedding 服务时返回 HTTP 503 和明确错误

### 用例 10：用户隔离

**操作**

用户 A 有“准备考研”的 embedding，用户 B 问：

```text
我最近为什么焦虑？
```

**预期**

- 用户 B 不会召回用户 A 的长期记忆
- 向量检索 SQL 和内存过滤都必须带 `user_id`

***

## 5. 代码层验收

### 5.1 Embedding 客户端存在

```bash
rg "create_embedding|/embeddings|EMBEDDING_MODEL" Echo-backend/services/embedding_client.py Echo-backend/config.py
```

预期：

- 能看到 embedding API 调用和模型配置

### 5.2 Vector Store 存在

```bash
rg "upsert_memory_embedding|retrieve_relevant_memories|backfill_user_memory_embeddings|cosine|memory_embeddings" Echo-backend/services/vector_store.py Echo-backend/services/memory.py
```

预期：

- 能看到 SQLite 向量存储和相似度检索逻辑

### 5.3 Context Builder 使用向量检索

```bash
rg "retrieve_relevant_memories|memory_retrieval_mode|vector_empty|fallback_importance" Echo-backend/services/context_builder.py
```

预期：

- 能看到向量召回和回退逻辑

### 5.4 后端暴露 backfill 接口

```bash
rg "memory_backfill_embeddings|/memory/backfill-embeddings|backfill_user_memory_embeddings" Echo-backend/main.py
```

预期：

- 能看到旧记忆补 embedding 接口

### 5.5 语法检查

```bash
python -B -m py_compile Echo-backend/main.py Echo-backend/llm_client.py Echo-backend/config.py Echo-backend/services/chat.py Echo-backend/services/context_builder.py Echo-backend/services/conversation_summary.py Echo-backend/services/embedding_client.py Echo-backend/services/memory_extractor.py Echo-backend/services/memory.py Echo-backend/services/vector_store.py
```

预期：

- 无语法错误

***

## 6. 本阶段通过标准

第八阶段验收通过需要同时满足：

- 长期记忆新增/更新后有 embedding
- 长期记忆删除/清空后对应 embedding 失效
- 当前消息能召回相关长期记忆
- 不相关长期记忆不会被强行注入 prompt
- 向量检索严格按 `user_id` 隔离
- embedding 服务失败时不影响主对话生成

***

## 7. 后续阶段入口

第八阶段完成后，可以进入下一阶段：

```text
验收测试和日志观测
```

下一阶段会补充端到端验收用例和关键日志字段，方便定位记忆抽取、embedding、召回和 prompt 注入的完整链路。

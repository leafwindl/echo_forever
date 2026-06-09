# Memory 模块

## 1. 业务目标

负责长期记忆的抽取、存储、管理和向量索引。它让 Echo 能跨会话记住用户明确表达的重要事实、偏好、称呼和长期目标。

## 2. 核心业务流程

### 记忆抽取流程

1. Chat 模块完成一轮回复后，把用户消息和 AI 回复交给 Memory 模块评估。
2. Memory 先用领域规则判断这轮对话是否包含值得长期保存的信息。
3. 如果不需要抽取，流程直接结束，不创建后台任务。
4. 如果需要抽取，创建可追踪、可恢复的后台任务。
5. 后台任务执行时，先锁定任务，避免重复处理。
6. 系统读取用户已有记忆，连同本轮对话一起交给大模型分析。
7. 大模型返回结构化的记忆操作，例如创建、更新、触碰或停用。
8. Memory 根据操作结果更新长期记忆表。
9. 对新增或更新的记忆生成 embedding，写入向量索引。
10. 任务成功后标记完成；失败则记录错误并进入重试或失败状态。

### 记忆管理流程

1. 接收记忆列表、删除、清空或补齐 embedding 请求。
2. 解析当前用户，确保用户只能操作自己的记忆。
3. 列表查询会规范化状态条件，并限制返回数量。
4. 删除单条记忆时，先确认记忆存在，再软删除记录。
5. 清空记忆时，批量将当前用户的记忆标记为删除。
6. 删除或清空记忆后，同步删除对应向量，避免后续检索命中已删除内容。
7. 补齐 embedding 时，只处理当前用户已有的 active 记忆，并限制批处理数量。
8. 将处理结果转换为接口响应返回。

## 3. 对外契约

### HTTP API

- `GET /memory/list`
- `DELETE /memory/{memory_id}`
- `POST /memory/clear`
- `POST /memory/backfill-embeddings`

### 发布的事件

- 当前无已落地事件。
- 预留事件：`MemoryExtracted`、`MemoryDeleted`。

### 依赖的其它模块接口

- LLM Provider：分析对话并生成结构化记忆操作。
- Embedding Provider：为长期记忆生成向量。
- 记忆仓储：保存、更新、停用和查询长期记忆。
- 向量仓储：保存和删除记忆向量。
- 后台任务仓储：记录任务状态、重试次数和错误信息。

## 4. 数据库表

- `user_memories`
- `memory_embeddings`
- `background_jobs`

## 5. 关键配置项

- `MEMORY_EXTRACTION_MODEL`
- `MEMORY_EXTRACTION_TEMPERATURE`
- `MEMORY_EXTRACTION_MAX_TOKENS`
- `EMBEDDING_API_KEY`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_MODEL`
- `MEMORY_VECTOR_TOP_K`
- `MEMORY_VECTOR_SCORE_THRESHOLD`

## 6. 注意事项

- 只有明确、稳定、对后续对话有价值的信息才应进入长期记忆。
- 删除记忆时必须同步删除向量记录，避免检索命中已删除内容。
- 后台任务必须可恢复，不应只依赖内存中的 `asyncio.create_task`。
- 记忆内容属于用户数据，日志中不要输出完整隐私内容。

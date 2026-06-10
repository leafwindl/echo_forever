# Memory 模块

## 1. 业务目标

负责长期记忆的抽取、存储、管理和向量索引。它让 Echo 能跨会话记住用户明确表达的重要事实、偏好、称呼和长期目标。

## 2. 核心业务流程

### 完整长期记忆链路

1. 用户发送一条消息。
2. Chat 模块先用当前消息生成临时 query embedding。
3. Memory 模块用这个 query embedding 去 `memory_embeddings` 中召回相关长期记忆。
4. 如果召回到相关记忆，Chat 模块会把这些记忆整理成自然语言上下文。
5. Chat 模块将系统提示词、相关长期记忆、会话摘要、近期聊天历史和当前消息一起交给大模型生成回复。
6. 回复生成后，后端写入本轮用户消息和 AI 回复。
7. Memory 模块异步判断本轮对话是否值得抽取长期记忆。
8. 如果不值得保存，长期记忆流程结束。
9. 如果值得保存，Memory 模块调用大模型把原始对话清洗成稳定、干净、可复用的长期记忆。
10. 清洗后的记忆写入 `user_memories`。
11. Memory 模块对清洗后的长期记忆生成 embedding。
12. embedding 写入 `memory_embeddings`，供后续聊天语义召回。

注意：第 2 步的 query embedding 是临时查询向量，不会写入数据库；第 11 步的 memory embedding 才是长期保存的记忆向量。

### 记忆抽取流程

1. Chat 模块完成一轮回复后，把用户消息和 AI 回复交给 Memory 模块评估。
2. Memory 先用领域规则判断这轮对话是否包含值得长期保存的信息。
3. 如果不需要抽取，流程直接结束，不创建后台任务。
4. 如果需要抽取，创建可追踪、可恢复的后台任务。
5. 后台任务执行时，先锁定任务，避免重复处理。
6. 系统读取用户已有记忆，连同本轮对话一起交给大模型分析。
7. 大模型返回结构化的记忆操作，例如创建、更新、触碰或停用。
8. Memory 根据操作结果更新长期记忆表。
9. 对新增或更新的记忆尝试生成 embedding；如果 Embedding 服务未配置，则跳过向量写入，但不影响记忆本身保存。
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

### 记忆状态流转

1. `active` 表示当前有效，会参与长期记忆召回和 Prompt 注入。
2. `inactive` 表示这条记忆曾经有效，但现在不应再参与召回。它适用于用户纠正、撤销、忘记指令、偏好变化或被新事实替代的场景。
3. `deleted` 表示用户主动删除或清空后的软删除状态，默认不再展示，也不再召回。
4. 停用不是只给未来用户手动编辑使用，也用于系统自动维护记忆生命周期。例如用户说“我不喜欢咖啡了”时，旧的“用户喜欢咖啡”应被停用，而不是直接从历史中消失。
5. 停用或删除记忆后，都必须同步移除对应向量，避免旧内容继续被语义检索命中。

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
- `inactive` 用于保留“曾经记住过但现在不应再使用”的历史状态，适合用户纠正、撤销、偏好变化或被新事实替代的场景。
- `deleted` 用于用户主动删除或清空后的软删除状态，表示这条记忆不应再展示或召回。
- 删除记忆时必须同步删除向量记录，避免检索命中已删除内容。
- 后台任务必须可恢复，不应只依赖内存中的 `asyncio.create_task`。
- 记忆内容属于用户数据，日志中不要输出完整隐私内容。

## 7. 当前实现状态

已实现：

- 基于关键词的轻量触发判断，避免每轮对话都调用大模型抽取记忆。
- 基于大模型的结构化记忆抽取，支持 create、update、deactivate、ignore。
- 长期记忆持久化到 `user_memories`。
- 明显重复记忆检测，避免同类型同内容重复创建。
- 后台任务持久化到 `background_jobs`，服务重启后可恢复 pending/running 任务。
- 记忆列表、删除、清空接口。
- 删除或清空记忆时同步清理向量记录。
- embedding 写入、向量记录表、向量召回、历史记忆 backfill 的代码路径。

当前未实际启用或未充分发挥：

- 当前环境未配置 Embedding 服务时，不会写入 `memory_embeddings`，也不会使用向量召回。
- 没有 embedding 时，Chat 构建上下文会回退到按重要度读取 active 记忆。
- 记忆抽取质量主要依赖 LLM 返回的 JSON，目前还没有强 schema 校验和自动修复。
- 记忆合并策略还比较简单，目前主要依赖精确归一化重复检测。

## 8. 预留能力

- 向量索引：`memory_embeddings` 表和 vector index 已预留。
- Embedding Provider：可替换不同 embedding 服务。
- 后台任务重试：`background_jobs` 已记录 attempts、max_attempts、error、started_at、finished_at。
- 记忆类型扩展：当前支持 profile、preference、relationship、goal、event、boundary。
- 记忆状态扩展：当前使用 active、inactive、deleted；其中 inactive 更适合系统内部停用或用户纠正，deleted 更适合用户主动删除。
- 过期时间：`expires_at` 字段已预留，但当前未自动清理过期记忆。
- 事件机制：预留 `MemoryExtracted`、`MemoryDeleted`，当前还未落地事件总线。

## 9. 下一步建议

1. 配置 Embedding 服务，让新增记忆真正写入 `memory_embeddings`。
2. 调用 backfill 接口，为历史 active 记忆补齐 embedding。
3. 给记忆抽取结果加严格 schema 校验，减少 LLM 输出漂移导致的 ignored。
4. 优化记忆合并策略，从精确重复升级为相似度合并或同类型规则合并。
5. 增加记忆详情和编辑接口，让用户能修正 Echo 记错的内容。
6. 增加记忆可观测性：抽取命中率、created/updated/ignored 比例、embedding 写入失败率。
7. 落地事件机制，让记忆创建、删除、更新可以被其它模块订阅。

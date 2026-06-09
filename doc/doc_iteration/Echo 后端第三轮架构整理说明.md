# Echo 后端第三轮架构整理说明

## 目标

第三轮整理聚焦两个边界：

- 后台任务边界：让长期记忆抽取从纯内存 `asyncio.create_task` 变成可恢复、可追踪的任务。
- 外部供应商边界：把 LLM、Embedding、TTS 的具体供应商调用收敛到 provider 层，service 层继续使用兼容门面。

本轮仍保持轻量，不引入 Celery、Redis 等额外基础设施，避免项目过早变重。

## 改了什么

### 1. 新增 `background_jobs` 表

在 `Echo-backend/db/schema.py` 中新增通用后台任务表：

- `job_id`
- `job_type`
- `status`
- `payload`
- `attempts`
- `max_attempts`
- `error`
- `started_at`
- `finished_at`

当前主要用于长期记忆抽取，后续也可以复用给摘要、向量补齐、批量清理等异步任务。

### 2. 新增任务仓储

新增 `Echo-backend/repositories/job_repository.py`，提供：

- `create_job`
- `get_job`
- `claim_job`
- `complete_job`
- `fail_job`
- `list_runnable_jobs`
- `reset_running_jobs`

任务状态流转为：

```text
pending -> running -> completed
pending -> running -> retry -> running -> completed
pending -> running -> retry -> running -> failed
```

如果服务重启时发现旧的 `running` 任务，会先退回 `retry` 或标记为 `failed`，避免任务永远卡在运行中。

### 3. 改造长期记忆抽取调度

`Echo-backend/services/memory_extractor.py` 现在不再直接把抽取任务丢进内存任务集合，而是：

1. 先通过规则 gate 判断是否值得抽取。
2. 命中后创建 `memory_extraction` 任务记录。
3. 尝试在当前事件循环里调度执行。
4. 如果当前没有运行事件循环，任务仍保留为 `pending`。
5. 服务启动时调用 `resume_pending_memory_extraction_jobs()` 恢复 pending/retry 任务。

`MemoryGateResult` 增加了 `job_id`，`ChatTurnResult` 增加了 `memory_extraction_job_id`，便于后续调试和管理接口引用具体后台任务。

### 4. 服务启动时恢复任务

`Echo-backend/main.py` 的 lifespan 在 `init_db()` 后会调用：

```python
resume_pending_memory_extraction_jobs()
```

这让服务重启后，未完成的记忆抽取任务有机会继续执行。

### 5. 新增 provider 层

新增：

- `Echo-backend/providers/llm_provider.py`
- `Echo-backend/providers/embedding_provider.py`
- `Echo-backend/providers/tts_provider.py`

当前 provider 实现：

- `OpenAICompatibleLLMProvider`
- `OpenAICompatibleEmbeddingProvider`
- `EdgeTTSProvider`

原有兼容入口仍保留：

- `Echo-backend/llm_client.py`
- `Echo-backend/services/embedding_client.py`
- `Echo-backend/services/minimax_tts.py`

也就是说，现有业务代码仍可以调用 `request_llm()`、`create_embedding()`、`text_to_speech()`，但真实供应商调用已经下沉到 provider。

### 6. 移除 TTS service 对 FastAPI 异常的依赖

`services/minimax_tts.py` 之前会直接抛 `HTTPException`。现在 TTS provider 抛普通 `ValueError`，由 API router 统一转换为 HTTP 错误。

这让 service/provider 层不再依赖 FastAPI，边界更干净。

### 7. 补充测试

新增和扩展测试：

- `test_repositories.py`：验证后台任务生命周期、无事件循环时记忆抽取会排队。
- `test_providers.py`：验证 provider 输入校验。

测试仍使用临时 SQLite 数据库，不触碰真实 `echo_memory.db`。

## 怎么改的

### 记忆抽取任务化

原先：

```python
task = loop.create_task(_run_memory_extraction_job(...))
```

现在：

```python
job_id = create_job("memory_extraction", payload)
_schedule_memory_extraction_job(job_id)
```

真正执行时会先 `claim_job(job_id)`，成功后才调用 `extract_and_store_memories()`。成功则 `complete_job(job_id)`，异常则 `fail_job(job_id, error)`。

### Provider 门面

原先 `llm_client.py` 直接创建 HTTP 请求。

现在：

```python
provider = get_llm_provider()
return await provider.chat_completion(...)
```

Embedding 和 TTS 采用同样结构。这样后续如果要切换模型服务商、接入 mock provider、做灰度路由或多 provider fallback，service 层不需要大改。

## 为什么这么改

### 任务不能只存在于内存

长期记忆抽取是用户体验增强能力，失败不能影响当前回复，但也不应该在服务重启时悄悄丢失。持久化任务表能提供最小成本的可恢复性。

### 先轻量，不急着上队列中间件

当前项目还处在 MVP/快速迭代阶段。用 SQLite 表记录任务，比直接引入 Celery/Redis 更容易维护，也足够支撑下一阶段的稳定性需求。

### 外部供应商需要统一适配点

LLM、Embedding、TTS 都属于可替换基础设施。provider 层把供应商差异包起来，业务服务只面对稳定接口，后续更容易做：

- 模型切换
- 成本优化
- 失败重试
- mock 测试
- 多供应商 fallback

### 避免 FastAPI 向下渗透

HTTP 异常应该属于 API 层。provider/service 抛业务异常，router 再转换成 HTTP 响应，这样分层更清楚。

## 验证结果

已执行：

```bash
python -B -m py_compile Echo-backend\db\schema.py Echo-backend\repositories\job_repository.py Echo-backend\providers\llm_provider.py Echo-backend\providers\embedding_provider.py Echo-backend\providers\tts_provider.py Echo-backend\llm_client.py Echo-backend\services\embedding_client.py Echo-backend\services\minimax_tts.py Echo-backend\services\memory_extractor.py Echo-backend\services\chat.py Echo-backend\main.py Echo-backend\tests\test_repositories.py Echo-backend\tests\test_providers.py
```

结果：通过。

已执行：

```bash
python -B -m unittest discover -s Echo-backend\tests
```

结果：

```text
Ran 15 tests
OK
```

已执行应用装配检查：

```bash
python -B -c "import sys; sys.path.insert(0, 'Echo-backend'); import main; print(len(main.app.routes))"
```

结果：

```text
14
```

## 后续建议

第四轮建议继续做任务与供应商能力的工程化：

- 增加后台任务管理 API，例如查看 pending/failed 任务和手动重试。
- 为 provider 增加超时、重试、限流和结构化错误类型。
- 把 ASR 也纳入 provider 层，统一音频供应商边界。
- 为 LLM/Embedding provider 增加 mock/fake 实现，扩大 service 层单元测试覆盖。
- 增加结构化日志字段，例如 `job_id`、`conversation_id`、`user_id`。

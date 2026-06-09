# Echo 后端第四轮架构整理说明

## 目标

本轮开始按 `doc/Echo 后端架构与代码规范.md` 落地后端重构。为了避免大爆炸式迁移，本轮优先迁移最复杂的 `memory` 能力，并补上工程门禁。

目标：

- 将 `memory` 迁移到 feature-first 结构。
- 让 Domain/Application 不依赖 Infrastructure。
- 保留旧 `services.memory_extractor` 兼容门面，避免打断现有调用。
- 增加架构依赖检查脚本，让分层规范可执行。
- 增加 Black/Ruff/coverage 基础配置。

## 改了什么

### 1. 新增 feature-first 目录

新增：

```text
Echo-backend/features/
  memory/
    domain/
      entities.py
      repositories.py
      extraction_rules.py
    application/
      memory_extraction.py
    infrastructure/
      adapters.py
      container.py
    public.py
```

### 2. Domain 层

`features/memory/domain` 现在承载：

- `Memory`
- `MemoryImportance`
- `MemoryGateResult`
- `MemoryExtractionResult`
- `MemoryExtractionConfig`
- `MemoryRepository`
- `MemoryEmbeddingRepository`
- `MemoryExtractionJobRepository`
- `MemoryExtractionLLM`
- 记忆抽取 gate、JSON 解析、重复记忆判断等纯规则

Domain 不依赖 FastAPI、Pydantic、SQLite、httpx、repositories、providers 或 services。

### 3. Application 层

`features/memory/application/memory_extraction.py` 新增 `MemoryExtractionService`。

它负责：

- 判断是否需要抽取记忆。
- 创建后台任务。
- 恢复 pending/retry 任务。
- 执行记忆抽取。
- 调用 Domain 接口完成记忆增删改和 embedding 同步。

Application 只依赖 Domain 定义的接口，不依赖具体 repository/provider。

### 4. Infrastructure 层

`features/memory/infrastructure/adapters.py` 负责把现有实现适配到 Domain 接口：

- `MemoryRepositoryAdapter`
- `MemoryEmbeddingRepositoryAdapter`
- `MemoryExtractionJobRepositoryAdapter`
- `MemoryExtractionLLMAdapter`

具体数据库、provider、向量记录仍通过现有 repository/provider 实现承载。

### 5. 兼容门面

`Echo-backend/services/memory_extractor.py` 已压缩为兼容门面。

现有代码仍可继续：

```python
from services.memory_extractor import schedule_memory_extraction
```

但真实实现已经转发到 `features.memory`。

### 6. 工程门禁

新增：

- `pyproject.toml`
- `scripts/check_architecture.py`

`check_architecture.py` 当前检查 `Echo-backend/features` 下的分层 import，禁止：

- Domain import FastAPI、Pydantic、SQLite、httpx、providers、repositories、services、db、api、schemas。
- Application import Interface、DB、具体 repositories/providers、FastAPI、httpx、SQLite。
- Infrastructure import Interface、FastAPI、schemas。

## 怎么改的

### 记忆抽取迁移前

`services/memory_extractor.py` 同时承担：

- Domain 规则
- Application 编排
- Infrastructure 调用
- 后台任务调度

### 记忆抽取迁移后

```text
services.memory_extractor
  -> features.memory.infrastructure.container
    -> features.memory.application.MemoryExtractionService
      -> features.memory.domain Protocol
    -> features.memory.infrastructure adapters
      -> repositories/providers
```

这样旧入口保持兼容，新实现开始符合分层约束。

## 验证结果

已执行：

```bash
python -B scripts\check_architecture.py
```

结果：

```text
Architecture check passed
```

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

## 尚未完成

本轮不是全量迁移，仍有过渡结构：

- `services.chat`
- `services.context_builder`
- `services.conversation_summary`
- `services.vector_store`
- 顶层 `repositories`
- 顶层 `providers`
- `api/routers`

这些会在后续逐步迁移到 feature-first：

1. 迁移 `chat` feature。
2. 迁移 `voice` feature。
3. 将 `api/routers` 下沉到对应 feature/interface。
4. 将顶层 repository/provider 逐步收缩为 feature infrastructure 或 shared infrastructure。
5. 扩展 `scripts/check_architecture.py`，覆盖更多目录。

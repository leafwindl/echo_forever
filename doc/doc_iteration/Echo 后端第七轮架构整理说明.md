# Echo 后端第七轮架构整理说明

## 目标

本轮继续按 `doc/Echo 后端架构与代码规范.md` 推进，重点补齐 feature 的 Interface 层。

目标：
- 将 `chat`、`memory`、`voice` 的业务 HTTP 路由迁移到各自 feature 内部。
- 顶层 `main.py` 只负责应用装配和 router 注册。
- 将 memory 管理接口中的业务编排下沉到 Application。
- 保留旧 `api/routers` import 路径作为兼容入口。

## 改了什么

### 1. 新增 feature interface router

新增：

```text
Echo-backend/features/chat/interface/router.py
Echo-backend/features/memory/interface/router.py
Echo-backend/features/voice/interface/router.py
```

新的职责划分：
- Interface：HTTP 入参、依赖注入、response schema、HTTP 错误码映射。
- Application：业务用例编排。
- Domain：实体、错误类型、抽象协议。
- Infrastructure：适配数据库、向量索引、ASR/TTS、LLM 等具体实现。

### 2. `main.py` 改为注册 feature router

`main.py` 不再注册 `api.routers.chat/memory/voice`，而是直接注册：

```python
from features.chat.interface.router import router as chat_router
from features.memory.interface.router import router as memory_router
from features.voice.interface.router import router as voice_router
```

顶层应用现在更接近 Bootstrap 职责：创建 FastAPI、初始化数据库、恢复后台任务、注册 router、挂载静态目录。

### 3. 旧 `api/routers` 改为兼容转发

以下文件已压缩为薄兼容层：

```text
Echo-backend/api/routers/chat.py
Echo-backend/api/routers/memory.py
Echo-backend/api/routers/voice.py
```

它们只导出对应 feature router，避免出现两份路由逻辑。

### 4. 新增 Memory 管理用例

新增：

```text
Echo-backend/features/memory/application/memory_management.py
```

覆盖能力：
- 列出记忆。
- 删除单条记忆。
- 清空当前用户记忆。
- 为历史记忆补齐 embedding。

路由不再直接调用 `services.memory` 或 `services.vector_store`，而是通过 `features.memory.public` 调用 Application。

### 5. 扩展 Memory Domain 和 Infrastructure

Domain 新增：
- `MemoryListResult`
- `MemoryDeleteResult`
- `MemoryClearResult`
- `MemoryBackfillResult`
- `MemoryValidationError`
- `InvalidMemoryStatusError`
- `MemoryNotFoundError`
- `MemoryOperationError`
- `MemoryVectorIndex` 协议

Infrastructure 新增：
- `MemoryVectorIndexAdapter`
- `MemoryRepositoryAdapter` 的列表、删除、清空能力

## 为什么这么改

- feature 自己拥有接口契约，模块边界更清楚。
- `main.py` 不再承载业务路由细节，启动装配职责更单一。
- memory 路由中的业务判断、limit 保护、向量同步等流程进入 Application，后续 CLI、任务或其他接口也可以复用。
- 旧路径兼容保留，降低对现有 import 和测试的影响。

## 验证结果

已执行架构依赖检查：

```bash
python -B scripts\check_architecture.py
```

结果：

```text
Architecture check passed
```

已执行语法编译检查：

```bash
python -B -m py_compile ...
```

结果：通过。

已执行完整单元测试：

```bash
python -B -m unittest discover -s Echo-backend\tests
```

结果：

```text
Ran 27 tests
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

仍处于过渡结构：

- `auth` 和 `health` 仍在顶层 `api/routers`。
- `schemas` 仍是顶层目录，后续可迁到各 feature 的 `interface/schema.py` 或保留为 API contract 包。
- `services.vector_store` 仍被 Memory Infrastructure 适配器复用，后续可以进一步拆成 Domain 协议 + Infrastructure 实现。
- 错误响应尚未统一为 `{code, message, request_id}`。

下一轮建议：
- 抽出 `shared/config/settings` 和 provider registry，进一步减少 Infrastructure 对旧 `services` 的依赖。
- 或先统一 API 错误响应模型，为前端建立稳定错误契约。

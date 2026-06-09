# Echo 后端第五轮架构整理说明

## 目标

本轮继续按 `doc/Echo 后端架构与代码规范.md` 做渐进式迁移，重点迁移 `chat` 能力。

目标：

- 将一轮聊天回复的核心编排迁移到 `features/chat`。
- 让 Chat Application 只依赖 Domain 抽象。
- 保留 `services.chat` 兼容门面，避免影响现有 API 路由。
- 补充 Chat Application 纯单元测试。

## 改了什么

### 1. 新增 `features/chat`

新增结构：

```text
Echo-backend/features/chat/
  domain/
    entities.py
    repositories.py
    services.py
  application/
    generate_reply.py
  infrastructure/
    adapters.py
    container.py
  public.py
```

### 2. Domain 层

`features/chat/domain` 定义：

- `ChatValidationError`
- `ChatContext`
- `ChatTurnResult`
- `MemoryExtractionScheduleResult`
- `ChatConversationRepository`
- `ChatContextProvider`
- `ChatLLM`
- `ConversationSummaryUpdater`
- `MemoryExtractionScheduler`

Domain 不依赖 FastAPI、Pydantic、SQLite、httpx、repositories、providers 或 services。

### 3. Application 层

新增 `GenerateChatReply` 用例，负责：

- 清洗和校验输入。
- 获取或创建 conversation。
- 构建模型上下文。
- 调用 LLM 生成回复。
- 原子写入 user/assistant 消息。
- 尝试更新会话摘要。
- 调度长期记忆抽取。

Application 只依赖 Chat Domain 定义的接口。

### 4. Infrastructure 层

`features/chat/infrastructure/adapters.py` 将当前已有能力适配为 Chat Domain 接口：

- conversation/message repository
- context builder
- LLM provider
- conversation summary updater
- memory extraction scheduler

跨 feature 调用记忆抽取时，通过 `features.memory.public.schedule_memory_extraction`，不直接引用 memory 内部实现。

### 5. 兼容门面

`Echo-backend/services/chat.py` 已压缩为：

```python
from features.chat.public import ChatTurnResult, ChatValidationError, generate_chat_reply
```

现有 API 仍可继续：

```python
from services.chat import generate_chat_reply
```

### 6. 补充测试

新增 `Echo-backend/tests/test_chat_feature.py`。

测试使用 fake repository/provider，覆盖：

- 一轮对话能写入 turn、更新摘要、调度记忆。
- 空消息会抛 `ChatValidationError`。

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
Ran 17 tests
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

- `services.context_builder`
- `services.conversation_summary`
- `services.vector_store`
- `api/routers`
- 顶层 `repositories`
- 顶层 `providers`

下一轮建议迁移 `voice` feature，随后把 `api/routers` 下沉到对应 feature/interface。

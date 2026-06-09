# Echo 后端架构与代码规范

## 0. 使用原则

本文是 Echo 后端长期准入标准。后续新增功能、重构、修 bug、补测试，都必须先对照本文。

关键词：

- 必须：不满足不能合并。
- 禁止：发现后必须整改。
- 建议：默认采用，除非有明确理由。

目标：

- 分层清晰，高内聚、低耦合。
- 按业务能力组织模块，而不是按技术类型堆目录。
- Domain 模型优先，不被数据库表结构牵着走。
- 模块、前后端、外部系统之间用明确契约协作。
- 为未来扩展留接口，不留坑。
- 用自动化工具和测试把规范变成门禁。

## 1. 架构标准

### 1.1 分层与依赖方向

推荐分层：

```text
Interface -> Application -> Domain
Infrastructure -> Domain 接口
Bootstrap 负责装配所有实现
```

职责：

- Interface：HTTP API、request/response schema、OpenAPI、错误码映射。
- Application：用例编排、事务边界、调用 Domain 服务和接口。
- Domain：Entity、Value Object、Domain Service、Repository/Provider Protocol。
- Infrastructure：数据库实现、外部 provider、文件存储、任务执行器。
- Bootstrap：创建 app、读取配置、装配具体实现。

必须遵守：

- Application 只依赖 Domain 抽象，不依赖具体数据库、SDK、HTTP 框架。
- Domain 不依赖 FastAPI、Pydantic、SQLite、httpx、第三方 SDK、环境变量。
- Infrastructure 可以实现 Domain 接口，但不能被 Domain 反向依赖。
- Interface 不能写业务规则和 SQL。

禁止依赖：

```text
domain -> application
domain -> infrastructure
application -> interface
application -> concrete infrastructure
infrastructure -> interface
```

### 1.2 按 Feature 组织模块

新增大功能必须优先按业务模块组织：

```text
features/
  chat/
    domain/
    application/
    interface/
    infrastructure/
    public.py
  memory/
    domain/
    application/
    interface/
    infrastructure/
    public.py
shared/
bootstrap/
```

规则：

- `chat`、`memory`、`voice` 这类业务模块优先于 `utils`、`components`、`services` 这类技术目录。
- feature 对外只暴露 `public.py` 或 `__init__.py` 声明的稳定 API。
- 禁止跨 feature import 对方内部实现。
- 跨模块协作必须通过 Application API、Domain 接口、事件契约或 OpenAPI。

当前仓库中的 `api/`、`repositories/`、`providers/` 属于过渡结构。新增业务不应继续扩大纯技术目录；旧代码逐步迁移到 feature-first。

### 1.3 Domain 模型优先

设计顺序：

1. 定义核心 Entity、Value Object、Domain Service。
2. 定义 Repository/Provider Protocol。
3. 定义 Application 用例和 DTO。
4. 定义 Infrastructure 实现。
5. 定义 Interface 路由和 schema。

Domain 对象必须是 Plain Object：

- 不依赖框架。
- 不依赖数据库。
- 不直接读取配置。
- 不直接调用外部服务。

典型模型：

- Entity：`User`、`Conversation`、`ChatMessage`、`Memory`。
- Value Object：`UserId`、`ConversationId`、`MemoryImportance`、`EmbeddingVector`。
- Domain Service：记忆合并规则、摘要边界判断、消息状态流转。

### 1.4 依赖倒置

高层模块不依赖低层模块，二者都依赖抽象。

必须：

- Domain 定义 `UserRepository`、`MemoryRepository`、`LLMProvider` 等 Protocol。
- Infrastructure 实现 `UserRepositorySQLite`、`UserRepositoryMySQL` 等具体类。
- Application 通过构造函数接收接口实现。
- 具体实现只在 Bootstrap/Container 中装配。

禁止：

- Application 直接 new 数据库 repository。
- 业务逻辑直接调用 `localStorage`、SQLite、httpx、第三方 SDK。
- 在核心流程中不断追加供应商 `if/else`。

### 1.5 配置与代码分离

必须外置：

- API 地址、数据库连接、模型名称、超时时间、重试次数。
- API key、secret、feature flag、静态资源域名。
- 第三方服务 endpoint、provider 选择、任务开关。

规则：

- 配置集中在 settings/config 模块。
- 新增配置必须更新 `.env.example` 和文档。
- Domain 和 Application 禁止直接调用 `os.getenv()`。
- Infrastructure 优先通过构造函数接收配置值。
- 禁止把环境相关值硬编码在业务逻辑中。

### 1.6 插件与钩子

可能扩展的点必须定义标准接口：

- LLM、Embedding、ASR、TTS provider。
- 文件存储。
- 通知渠道。
- 支付方式。
- 内容安全审核。
- 任务执行器。
- 记忆抽取策略。

插件接口必须包含：

- 插件名称。
- 输入/输出契约。
- 错误类型。
- 配置 schema。
- 默认实现或 fake 实现。
- 注册方式。

新增插件时，只实现接口并注册；禁止修改核心流程来堆分支。

### 1.7 契约优先

必须先改契约，再改实现。

后端内部契约：

- Domain Protocol。
- Application input/output DTO。
- Provider Protocol。
- Domain Event。

前后端契约：

- FastAPI OpenAPI。
- Pydantic request/response schema。
- 必要时从 OpenAPI 生成 TypeScript 类型。

API 规范：

- 关键 API 必须有稳定 response schema。
- 错误响应应统一包含 `code`、`message`、`request_id`。
- 分页接口统一使用 `limit`、`cursor` 或明确说明偏移策略。
- 关键写接口必须考虑幂等键。
- 破坏性变更必须版本化或提供迁移期。

禁止跨模块传随意 dict；边界处必须转换为 DTO、schema 或 Domain 对象。

### 1.8 事务与数据迁移

事务规则：

- Application 用例决定事务边界。
- Domain 不 commit、不 rollback。
- Interface 不直接开事务。
- Repository 可接受外部 transaction/unit of work。

数据迁移规则：

- 禁止 destructive migration 自动在启动时执行。
- schema 变更必须向后兼容或提供迁移脚本。
- 迁移必须可重复执行。
- 重要迁移必须有回滚或修复方案。
- 新索引、新约束、新字段必须说明业务原因。
- Repository 测试必须覆盖新增 schema 行为。

### 1.9 后台任务

关键后台任务必须可追踪、可恢复。

任务必须包含：

- `job_id`
- `job_type`
- `status`
- `payload`
- `attempts`
- `max_attempts`
- `error`
- `started_at`
- `finished_at`

状态至少包括：

```text
pending -> running -> completed
pending -> running -> retry -> failed
```

服务启动时必须处理遗留 `running` 任务。禁止只依赖内存 `asyncio.create_task` 承载关键任务。

### 1.10 可观测性

必须记录结构化日志字段：

- `request_id`
- `user_id`
- `conversation_id`
- `job_id`
- `provider`
- `duration_ms`
- `error_code`

关键路径必须能观测：

- 登录成功率和失败原因。
- LLM/Embedding/ASR/TTS 调用耗时和失败率。
- 后台任务 pending/running/failed 数量。
- 数据库错误和慢查询。
- 关键 API 延迟。

禁止在日志中输出 API key、secret、完整 openid、敏感用户内容。

### 1.11 安全与隐私

必须：

- 所有用户数据按 `user_id` 隔离。
- API key/secret 只通过环境变量或密钥服务注入。
- 日志脱敏。
- 删除记忆、清空记忆等操作必须校验用户身份。
- 高风险接口考虑限流。
- 用户数据删除能力必须可设计、可验证。

禁止：

- 将 secret 写入代码或文档示例真实值。
- 在日志中打印完整用户隐私内容。
- 后端信任客户端传来的任意用户身份而不校验。

## 2. 代码规范

### 2.1 自动化工具

后端：

- Formatter：Black
- Linter：Ruff
- Type Check：mypy 或 pyright
- Test：pytest 或 unittest

前端：

- Formatter：Prettier
- Linter：ESLint
- Type Check：`tsc --noEmit`

提交前：

- 使用 Husky + lint-staged。
- 自动格式化、lint、类型检查、运行相关测试。

建议后端配置：

```toml
[tool.black]
line-length = 100
target-version = ["py311"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "C4", "ARG"]
ignore = []
```

### 2.2 命名

命名即文档。

推荐：

- `memory_extraction_job_id`
- `conversation_summary_boundary_message_id`
- `active_user_memories`

避免：

- `data`
- `temp`
- `obj`
- `handle`
- `res`
- `foo`

函数名必须表达业务动作，例如 `schedule_memory_extraction()`、`claim_background_job()`。

### 2.3 注释

注释写 Why，不写 What。

推荐：

```python
# 记忆抽取失败不影响当前回复，因为它只是体验增强能力。
```

避免：

```python
# 调用函数
# 设置变量
```

### 2.4 错误处理

规则：

- Domain 抛领域异常。
- Application 转换业务异常。
- Interface 映射 HTTP status code。
- Infrastructure 捕获 SDK/DB 异常并转换为可理解错误。

禁止在 Domain/Application/Provider 中直接抛 `HTTPException`。

### 2.5 测试

必须覆盖：

- Domain 纯逻辑测试。
- Application 用例测试，使用 fake repository/provider。
- Infrastructure repository 测试，使用临时数据库。
- Interface 路由测试，覆盖关键 API。
- 插件 registry 测试。
- 关键路径集成测试：登录、聊天发送、记忆抽取调度、语音回复。

覆盖率目标：

```text
Domain: >= 90%
Application: >= 80%
核心模块整体: >= 80%
```

没有测试的重构不能合并。

## 3. 工程强制门禁

代码合并前必须通过：

- 格式化检查。
- Ruff/ESLint。
- 类型检查。
- 单元测试。
- 关键集成测试。
- 覆盖率阈值。
- 架构依赖检查。

架构依赖检查至少禁止：

- Domain import FastAPI、Pydantic、sqlite3、httpx、providers。
- Application import Interface 或具体 Infrastructure 实现。
- Infrastructure import Interface。
- Feature 之间 import 对方内部实现。

建议新增脚本：

```text
scripts/check_architecture.py
```

CI 和 pre-commit 必须调用该脚本。

## 4. 当前项目迁移策略

当前 Echo 后端仍处于过渡结构。迁移原则：

### 新代码

必须尽量按 feature-first + clean architecture 编写。

### 旧代码

分批迁移：

1. 补契约和测试。
2. 抽 Domain 模型。
3. 抽 Application 用例。
4. 替换 Infrastructure 实现。
5. 收缩兼容门面。

### 兼容门面

以下门面可暂时存在，但不得继续扩大：

- `services.memory`
- `llm_client`
- `services.embedding_client`
- `services.minimax_tts`

新增业务不得依赖这些门面作为长期边界。

## 5. 提交前检查清单

每次改代码前后都检查：

- 是否违反分层依赖。
- 是否按 Feature 组织。
- 是否把业务逻辑写进 Interface。
- 是否让 Domain 依赖框架、数据库或 SDK。
- 是否定义或更新契约。
- 是否通过接口预留扩展，而不是只写 TODO。
- 是否把环境相关值放到配置。
- 是否避免在核心流程中堆 `if/else`。
- 是否补了必要测试。
- 核心模块覆盖率是否达标。
- 是否有可观测字段。
- 是否满足安全与隐私要求。
- 是否跑过格式化、lint、类型检查、测试、架构检查。

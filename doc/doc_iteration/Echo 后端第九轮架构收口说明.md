# Echo 后端第九轮架构收口说明

## 目标

本轮按新的架构规范做一次收口迁移：完成剩余兼容层迁移，并删除旧的兼容代码。

目标：
- 删除旧 `services`、`api`、`schemas`、`config.py`、`llm_client.py` 入口。
- 将 auth、health、schema、依赖注入迁移到 feature/shared 下。
- 将 chat context、会话摘要、memory vector、voice audio/asr 迁移到 feature/provider 下。
- 更新架构检查，防止旧兼容入口回流。

## 迁移后的稳定结构

```text
Echo-backend/
  main.py
  db/
  repositories/
  providers/
  shared/
    config/
    interface/
  features/
    auth/
    chat/
    memory/
    voice/
    system/
```

## 改了什么

### 1. 删除旧兼容入口

已删除：

```text
Echo-backend/config.py
Echo-backend/llm_client.py
Echo-backend/services/
Echo-backend/api/
Echo-backend/schemas/
```

这些目录/文件原本主要承担兼容门面或技术型聚合职责，现在对应能力已经迁移到 feature/shared/provider。

### 2. 新增 Auth Feature

新增：

```text
Echo-backend/features/auth/
  domain/
  application/
  infrastructure/
  interface/
  public.py
```

登录流程现在拆分为：
- Domain：`AuthError`、`UserIdentityRepository`、`WeChatSessionClient`。
- Application：`LoginWithWeChatCode`。
- Infrastructure：微信 code2session HTTP 适配、用户 upsert 适配。
- Interface：`/login` 路由和 request/response schema。

### 3. 新增 System Feature

健康检查迁移到：

```text
Echo-backend/features/system/interface/router.py
```

顶层 `main.py` 只注册 router，不再保留 `api/routers/health.py`。

### 4. Schema 下沉到各 Feature Interface

已迁移：

```text
features/auth/interface/schemas.py
features/chat/interface/schemas.py
features/memory/interface/schemas.py
features/voice/interface/schemas.py
```

`schemas/` 顶层目录已删除。

### 5. 共享接口依赖迁移

用户身份解析迁移到：

```text
Echo-backend/shared/interface/dependencies.py
```

`api/dependencies.py` 已删除。

### 6. Chat Infrastructure 收口

已迁移：

```text
features/chat/infrastructure/context_builder.py
features/chat/infrastructure/conversation_summary.py
```

`services.context_builder`、`services.conversation_summary`、`llm_client.py` 已删除。

### 7. Memory Vector 收口

已迁移：

```text
features/memory/infrastructure/vector_index.py
```

`services.vector_store`、`services.embedding_client` 已删除。

### 8. Voice Infrastructure 和 ASR Provider 收口

新增：

```text
features/voice/infrastructure/audio_storage.py
providers/asr_provider.py
```

`services.audio_storage`、`services.tencent_asr`、`services.minimax_tts` 已删除。

ASR 现在和 LLM/Embedding/TTS 一样，通过 provider registry 扩展。

### 9. `main.py` 只做 Bootstrap

`main.py` 当前职责：
- 创建 FastAPI app。
- 初始化数据库。
- 恢复 pending memory extraction jobs。
- 注册 feature routers。
- 挂载静态目录。

不再 import 旧 `api.routers` 或 `services`。

### 10. 架构检查增强

`scripts/check_architecture.py` 新增：
- 禁止旧兼容路径重新出现：
  - `services/`
  - `api/`
  - `schemas/`
  - `config.py`
  - `llm_client.py`
- Feature `interface` 层禁止 import `config/db/providers/repositories/services`。
- Feature `infrastructure` 层禁止 import `api/config/fastapi/schemas/services`。

## 为什么这么改

- 删除兼容层后，调用路径更短，职责更明确。
- Interface 跟随 feature，API 契约靠近业务边界。
- Application 不再需要知道配置、HTTP 框架、数据库或 provider 实现。
- Provider registry 覆盖 LLM、Embedding、TTS、ASR，外部供应商替换有统一扩展点。
- 架构检查把“不能回到旧结构”变成自动化约束。

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
Ran 30 tests
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

已反查旧入口：

```bash
rg --files Echo-backend | rg "^(Echo-backend\\(services|api|schemas)\\|Echo-backend\\config.py|Echo-backend\\llm_client.py)$"
```

结果：无输出。

## 后续建议

这轮已经删除旧兼容代码。后续不再是“兼容迁移”，而是增强工程质量：

- 统一 API 错误响应 `{code, message, request_id}`。
- 补 `.env.example`，列出所有配置项。
- 增加 OpenAPI 到前端 TypeScript 类型生成。
- 将 `repositories` 继续按 feature 拆分或引入 Unit of Work。
- 为 provider registry 增加按配置选择 provider 类型的能力。

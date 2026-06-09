# Echo 后端第八轮架构整理说明

## 目标

本轮继续按 `doc/Echo 后端架构与代码规范.md` 推进，重点处理配置与 provider 装配。

目标：
- 建立长期使用的 `shared/config` 配置入口。
- 保留旧 `config.py` 兼容导出，避免历史代码一次性断裂。
- 建立 provider registry，为替换 LLM、Embedding、TTS provider 留标准注册点。
- 将业务代码中的旧配置 import 切到 `shared.config`。
- 用架构检查禁止 Domain/Application 直接读取配置。

## 改了什么

### 1. 新增 `shared/config`

新增：

```text
Echo-backend/shared/config/settings.py
Echo-backend/shared/config/__init__.py
```

`Settings` 现在统一通过 `pydantic-settings` 从环境变量和 `.env` 读取配置，不再在配置类字段中散落 `os.getenv()`。

保留兼容字段：
- `settings.LLM_MODEL`

新增长期推荐字段：
- `settings.llm_model`

### 2. `config.py` 改为兼容门面

`Echo-backend/config.py` 不再定义真实配置，只 re-export：

```python
from shared.config import Settings, get_settings, settings
```

新代码必须使用：

```python
from shared.config import settings
```

### 3. 新增 provider registry

新增：

```text
Echo-backend/providers/registry.py
```

提供：
- `register_provider_factory()`
- `get_provider()`
- `reset_provider_registry_for_tests()`

`get_llm_provider()`、`get_embedding_provider()`、`get_tts_provider()` 已改为通过 registry 获取默认实现。

后续替换 provider 时，只需要注册新的 factory，不需要改 Application 或 feature 用例。

### 4. 迁移配置 import

以下模块已从旧 `config` 切到 `shared.config`：
- `providers/llm_provider.py`
- `providers/embedding_provider.py`
- `services/auth.py`
- `services/audio_storage.py`
- `services/context_builder.py`
- `services/tencent_asr.py`
- `services/vector_store.py`
- `features/memory/infrastructure/*`
- `features/voice/infrastructure/adapters.py`

同时，Voice TTS 默认音色改为从 `settings.minimax_tts_voice_id` 注入，不再在适配器中硬编码。

### 5. 更新架构检查

`scripts/check_architecture.py` 新增限制：
- Domain 禁止 import `config`、`shared.config`
- Application 禁止 import `config`、`shared.config`

配置只应由 Bootstrap/Infrastructure 读取，再通过构造函数注入到用例。

### 6. 补充测试

扩展 `Echo-backend/tests/test_providers.py`，覆盖：
- registry 替换 Embedding provider。
- registry 替换 TTS provider。
- 旧 `config.settings` 与新 `shared.config.settings` 指向同一对象。

## 为什么这么改

- 配置入口收敛后，环境相关变量不会继续散落在业务代码里。
- Provider registry 是插件化机制的第一步，后续换模型供应商、Embedding 服务或 TTS 实现时，不需要改业务层。
- 旧 `config.py` 保留兼容，可以降低迁移风险。
- 架构门禁把规则自动化，避免后续新增代码绕过分层规范。

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

## 尚未完成

仍处于过渡结构：

- `services.context_builder`、`services.vector_store` 仍是旧服务门面。
- ASR 还没有 provider registry，当前仍通过 `services.tencent_asr` 适配。
- Provider registry 还没有按配置选择 provider 类型，目前只支持注册替换。
- `.env.example` 尚未补齐所有配置项。

下一轮建议：
- 增加 ASR provider 抽象和 registry，完成 LLM/Embedding/TTS/ASR 四类外部 provider 的统一装配。
- 或统一 API 错误响应 `{code, message, request_id}`，为前端建立稳定错误契约。

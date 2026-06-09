# Echo 后端第一轮架构整理说明

## 目标

本轮整理聚焦后端的第一层结构边界：让 HTTP 入口更薄、让请求/响应模型集中管理、让用户身份解析有统一入口，并补上可以快速运行的基础测试。业务能力本身保持兼容，不主动改变现有前端调用路径。

## 改了什么

### 1. 收缩 `main.py`

原来的 `Echo-backend/main.py` 同时负责应用创建、路由声明、Pydantic 模型、文件上传、记忆管理、聊天、语音等逻辑。现在它只保留：

- 加载环境变量和日志配置
- FastAPI app 创建
- lifespan 启动时初始化数据库
- 注册各领域 router
- 挂载静态文件目录

这样 `main.py` 变成应用装配层，不再承载具体业务。

### 2. 新增按领域拆分的 API Router

新增目录：

- `Echo-backend/api/routers/health.py`
- `Echo-backend/api/routers/auth.py`
- `Echo-backend/api/routers/chat.py`
- `Echo-backend/api/routers/memory.py`
- `Echo-backend/api/routers/voice.py`

原有路径保持不变：

- `GET /`
- `POST /login`
- `POST /chat/send`
- `GET /memory/list`
- `DELETE /memory/{memory_id}`
- `POST /memory/clear`
- `POST /memory/backfill-embeddings`
- `POST /voice/asr`
- `POST /voice/reply`

拆分后，每个 router 只处理自己的 HTTP 入参、返回模型和异常映射，具体业务仍交给 `services` 层。

### 3. 新增集中式 Schema 层

新增目录：

- `Echo-backend/schemas/auth.py`
- `Echo-backend/schemas/chat.py`
- `Echo-backend/schemas/memory.py`
- `Echo-backend/schemas/voice.py`

这些文件承载 Pydantic request/response 模型。后续新增接口时，路由文件不再直接堆模型定义，API 契约会更容易查找和复用。

### 4. 新增统一用户身份依赖

新增 `Echo-backend/api/dependencies.py`：

- `CurrentUser`
- `resolve_current_user`
- `get_current_user`

当前为了兼容前端，仍支持从 body/query 读取 `user_id`；同时预留 `X-Echo-User-Id` header。如果 header 和 body/query 的用户身份冲突，会返回 `403 Conflicting user identity`。

这一步还不是完整 token 鉴权，但它把用户身份解析集中到了一个地方。后续接入 session/JWT 时，可以主要替换这个依赖，而不是逐个修改所有路由。

### 5. 修复依赖文件

`Echo-backend/requirements.txt` 之前含有 NUL 字节，且 `tencentcloud-sdk-python` 和 `edge-tts` 被粘连，容易导致新环境安装失败。本轮已整理为干净的文本依赖，并补上 FastAPI 文件上传需要的 `python-multipart`。

### 6. 收紧音频存储路径

`services/audio_storage.py` 之前在 import 阶段直接创建相对路径 `static/voices`。现在改为：

- 按 `Echo-backend` 目录定位静态语音目录
- 只在实际保存/读取语音目录时创建目录
- `/voice/asr` 和 TTS 保存共用同一个语音目录定位逻辑

这样从仓库根目录运行测试或导入 app 时，不会在错误位置创建 `static/voices`。

### 7. 新增基础测试

新增：

- `Echo-backend/tests/test_api_dependencies.py`
- `Echo-backend/tests/test_memory_extractor.py`
- `Echo-backend/tests/test_context_builder.py`

覆盖范围包括：

- 用户身份解析、缺失和冲突校验
- 记忆抽取 gate 的基础判断
- LLM JSON 结果解析
- 长期记忆格式化

这些测试不依赖真实数据库、LLM、微信、ASR 或 TTS，适合作为快速回归测试。

## 为什么这么改

### 降低入口层复杂度

入口文件越厚，后续越难判断一段代码属于 HTTP、业务编排、数据访问还是外部供应商适配。本轮先把 API 边界拆开，让每个文件职责更窄。

### 为真实鉴权做铺垫

当前接口仍然兼容 `user_id` 明文传参，但所有需要用户身份的路由已经统一走 `get_current_user`。后续只要把这个依赖替换为 token/session 校验，就能整体升级用户身份边界。

### 减少模块之间的直接耦合

路由不再直接定义 schema，也不再混在同一个巨型入口文件里。HTTP 层、schema 层、service 层的依赖方向更清晰：

`router -> schema / dependency -> service`

### 提升新环境可启动性

修复损坏的依赖文件后，后续新同学或新机器安装依赖时不会因为二进制污染的 `requirements.txt` 卡住。

### 给后续重构留测试护栏

第二轮如果继续拆 repository、任务队列、供应商 adapter，这些纯逻辑测试能先守住关键规则，避免结构调整时误伤现有行为。

## 验证结果

已执行：

```bash
python -B -m unittest discover -s Echo-backend\tests
```

结果：

```text
Ran 8 tests
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

下一轮建议处理数据层和事务边界：

- 拆分 `services/memory.py` 为 user、conversation、message、memory repository
- 把 SQLite 连接管理移到独立 `db` 模块
- 为“一轮聊天写入用户消息和 assistant 消息”建立明确事务边界
- 为后台记忆抽取引入可恢复任务表或轻量任务队列

# Echo Backend

Echo Backend 是 Echo AI 陪伴应用的服务端，基于 FastAPI、PostgreSQL 和 pgvector。当前生产版本为 `1.1.0`，负责身份会话、异步聊天、统一 Agent、长期记忆、关系状态、表情包、语音、每日来信、主动聊天、学习专注、通知和 Android 应用更新。

## 运行架构

后续开发以 [`Echo 后端架构与代码规范`](../doc/Echo%20后端架构与代码规范.md) 和根 `AGENTS.md` 为准。跨业务提示渲染已移入 `shared/prompting/`，当前四份通用规则从 `prompts/rules/` 的 Markdown 实际加载；旧 chat Renderer 入口已删除。完整六类资产注册与按需选择尚未实现，不创建未来占位接口。

```text
Nginx / HTTPS
  -> FastAPI interface
  -> application service
  -> domain policy
  -> PostgreSQL + pgvector
  -> LLM / Embedding / ASR / TTS providers
  -> COS / Getui
```

后端采用 feature-first Clean Architecture：

- `interface/`：HTTP、SSE、WebSocket、鉴权和请求校验。
- `application/`：业务用例和跨领域编排。
- `domain/`：实体、规则、协议和稳定错误。
- `infrastructure/`：PostgreSQL repository、provider 和外部服务适配。
- `main.py`：路由、Worker 和生命周期装配。

应用层和领域层不直接读取环境变量，不直接依赖具体数据库或厂商 SDK。Agent 通过 Tool Registry 调用受控业务工具，工具再进入对应 feature，不能绕过业务规则直接写表。

## 业务模块

```text
features/
  auth/                 手机号验证码、JWT access/refresh 会话
  assistant_persona/   Echo 固定人格版本
  persona/              首次引导和用户偏好
  relationship/         关系阶段和关系事件
  chat/                 异步消息、历史分页、SSE、摘要和通话回复
  agent/                模型循环、工具调用、运行轨迹和交付协议
  memory/               长期记忆、抽取任务和向量检索
  stickers/             上传、保存、语义搜索、冷却和生成任务
  voice/                PCM ASR、流式 ASR、TTS 和文件清理
  letters/              每日来信、偏好、未读和已读
  proactive_chat/       主动偏好、定时任务和到期 Worker
  push/                 个推 CID、通知 Outbox、重试和发送
  releases/             Android 版本元数据和安全下载
  system/               健康检查和版本信息
providers/              LLM、Embedding、TTS、ASR、图片和联网搜索适配
shared/                 配置、COS、鉴权、限流和日志过滤
db/                     PostgreSQL 连接和幂等 schema 初始化
```

## 核心数据流

### 异步文字聊天

```text
POST /chat/messages
  -> 校验 client_message_id 和消息内容
  -> 用户消息立即写入 PostgreSQL
  -> 创建或合并待处理 Chat Turn
  -> 返回 202，客户端可继续发送
  -> 后台 Worker 串行运行统一 Agent
  -> Agent 按需调用时间、搜索、表情包或任务工具
  -> 保存一至三段 Echo 文字和最多一张独立表情包
  -> SSE /chat/events 交付 typing、消息组和失败状态
```

`GET /chat/messages` 支持 `before_id` 向上分页和 `after_id` 断线补偿。聊天记录、具体消息、摘要和长期记忆是不同数据，生成摘要不会删除历史消息。

### 语音通话

```text
WS /voice/asr/stream 或 POST /voice/asr
  -> 得到识别文本
  -> POST /chat/send mode=call
  -> 同步运行 Agent，禁用表情包和主动任务工具
  -> CosyVoice 生成音频
  -> 返回 reply + audio_urls
```

通话输入只接受 16 kHz、单声道、PCM16LE。流式识别不可用时客户端上传整段 PCM；上传临时文件识别完成后立即删除，TTS 文件按保留期清理。

### 主动聊天与通知

```text
用户要求提醒 / Echo 创建一次性后续联系 / 主动策略命中
  -> chat_schedules / proactive_chat_jobs
  -> 到期 Worker 重新读取当前上下文
  -> 统一 Agent 生成普通 Echo 消息
  -> 消息先写入 chat_messages
  -> notification_outbox
  -> Getui 推送到已绑定 CID
```

通知不是消息本体。即使推送失败，用户重新打开 APP 后仍能从聊天历史读取主动消息。主动行为受开关、时区、安静时段、频率、未回复次数和任务状态约束。

## API 总览

除健康检查、版本检查和 Android 发布查询外，用户业务接口都要求 `Authorization: Bearer <access_token>`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/login/phone` | 请求手机号验证码 |
| `POST` | `/login/verify` | 校验验证码并签发会话 |
| `POST` | `/login/refresh` | 轮换 access/refresh token |
| `POST` | `/login/logout` | 撤销当前 refresh token |
| `GET/PUT/POST` | `/persona/me`、`/persona/me/reset` | 用户偏好和首次引导 |
| `GET/POST` | `/relationship/me`、`/relationship/me/reset` | 关系状态和重置 |
| `POST` | `/chat/messages` | 异步接受文字或表情包消息，返回 `202` |
| `GET` | `/chat/events` | SSE 实时消息和 typing 事件 |
| `GET` | `/chat/messages` | 聊天历史和游标分页 |
| `POST` | `/chat/send` | 仅供语音通话的同步 Agent + TTS |
| `POST` | `/chat/clear` | 清空聊天与摘要，不删除长期记忆 |
| `GET/DELETE/POST` | `/memory/*` | 长期记忆列表、删除和清空 |
| `GET/PUT/POST` | `/letters/*` | 每日来信和偏好 |
| `GET/POST/DELETE` | `/stickers/*` | 表情包上传、保存、删除和生成任务 |
| `WS` | `/voice/asr/stream` | PCM 流式 ASR |
| `POST` | `/voice/asr` | 整段 PCM ASR |
| `GET/PUT` | `/proactive/preferences` | 主动聊天偏好 |
| `GET/POST/PUT/DELETE` | `/proactive/schedules/*` | 定时任务管理 |
| `PUT/DELETE` | `/push/tokens/me/*` | 个推 CID 绑定和撤销 |
| `GET/POST` | `/releases/*` | Android 更新检查和下载授权 |
| `GET` | `/health/ready` | 数据库就绪检查 |
| `GET` | `/version` | 服务端、Prompt 和 Persona 版本 |

## Agent 工具

当前 Tool Registry 包含：

- `get_current_time`：按 IANA 时区读取可靠时间。
- `search_web`：可选联网搜索；只有配置 provider 后才返回结果。
- `search_stickers` / `send_sticker`：语义检索并发送当前可见表情包。
- `create_chat_schedule`：创建一次性、每日或每周任务；Echo 自主创建时只允许一次性任务。
- `list_chat_schedules` / `cancel_chat_schedule`：查询和取消用户可见任务。

每轮最多成功发送一张表情包。失败工具调用不消耗成功额度；表情包候选变化后可以重新选择，复用受对话轮次和时间冷却约束。通话模式只暴露允许的读取工具，不暴露表情包和任务工具。

## 数据与存储

- PostgreSQL 是唯一运行时业务数据库。
- pgvector 保存长期记忆向量，正文仍保存在 `user_memories`。
- 用户上传表情包当前保存在后端 `static/stickers/`，元数据保存在 PostgreSQL。
- APK 发布对象保存在私有 COS，服务端返回短期签名 HTTPS URL。
- 语音上传和 TTS 文件由清理 Worker 按配置保留期删除。
- `notification_outbox` 保存待发送通知，`push_targets` 保存用户设备 CID。
- schema 在服务启动时由 `db/postgres_schema.py` 幂等初始化。

## 配置

从 `.env.example` 创建被 Git 忽略的 `.env`：

```bash
copy .env.example .env
```

关键配置组：

- LLM、Prompt、Persona 和 Embedding。
- JWT、refresh token、验证码和短信服务。
- PostgreSQL、COS 和 Android 发布。
- 腾讯 ASR、CosyVoice TTS 和语音文件保留期。
- Agent、联网搜索、表情包和每日来信。
- 主动聊天 Worker、个推 RestAPI V2 和通知 Worker。

`GETUI_MASTER_SECRET`、`COS_SECRET_KEY`、模型 Key 和 JWT 密钥不得进入 Flutter、Git、日志或文档。APP 只需要个推 AppID，AppKey 和 MasterSecret 只属于服务端。

## 启动

从仓库根目录启动推荐环境：

```bash
docker compose up -d --build echo-postgres echo-backend
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8000/version
```

直接运行：

```bash
cd Echo-backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

直接运行时必须提供可访问的 `DATABASE_URL`。

## 生产状态与限制

- 生产 API：`https://api.echoaiforever.cn`。
- 生产数据库：PostgreSQL + pgvector。
- 当前个推凭证已通过 RestAPI V2 鉴权。
- 华为、荣耀、小米、OPPO、vivo 厂商离线通道尚未全部接入。
- 正式短信服务尚未接入时，只能用于封闭测试，不能公开发布固定验证码。
- 表情包图片生成和联网搜索默认关闭，只有配置服务商后才启用。
- Android APK 不在服务器构建，服务器只部署后端。

## 检查

```bash
python -B ../scripts/check_architecture.py
python -m pytest -q
```

当前发布结果：296 项后端测试通过，架构检查通过。

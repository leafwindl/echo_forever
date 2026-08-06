# Echo Backend 1.0

Echo Backend 基于 FastAPI，按 feature-first Clean Architecture 组织。v1.0 使用 PostgreSQL + pgvector 作为唯一运行时数据库。

## 启动

从仓库根目录启动：

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

直接运行时必须提供 `DATABASE_URL`。完整配置见 `.env.example`。

## 模块

```text
features/
  auth/                 手机号验证码、JWT access/refresh session
  assistant_persona/   Echo 固定人格
  chat/                 对话、Prompt、摘要、消息持久化
  agent/                统一模型编排和工具调用
  memory/               长期记忆和向量检索
  persona/              用户偏好和首次引导
  relationship/         关系阶段和事件
  stickers/             表情包上传、生成、搜索和发送
  letters/              每日来信
  voice/                PCM ASR、TTS 和音频文件生命周期
  system/               健康检查和版本信息
providers/              外部模型和语音服务适配
shared/                 配置、鉴权、限流、日志和基础设施
db/                     PostgreSQL 连接与幂等 schema 初始化
```

依赖方向：`Interface -> Application -> Domain`，`Infrastructure -> Domain Protocol`。provider、repository 和配置在容器或 `main.py` 启动边界装配；feature 的 application/domain 不直接导入 provider、数据库连接或配置对象。

## HTTP/WebSocket 契约

除系统健康检查外，用户接口都需要 `Authorization: Bearer <access_token>`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/login/phone` | 请求手机号验证码 |
| `POST` | `/login/verify` | 校验验证码并签发 access/refresh token |
| `POST` | `/login/refresh` | 刷新会话 |
| `POST` | `/login/logout` | 撤销当前 refresh token |
| `GET/PUT/POST` | `/persona/me`、`/persona/me/reset` | 用户偏好和首次引导 |
| `POST` | `/chat/send` | 文字或 `mode=call` 的完整回复 |
| `GET` | `/chat/messages` | 按消息 ID 游标分页读取当前会话历史 |
| `POST` | `/chat/clear` | 清空聊天记录和会话摘要 |
| `GET/DELETE/POST` | `/memory/*` | 长期记忆管理 |
| `GET/POST` | `/relationship/*` | 关系状态和重置 |
| `GET/PUT/POST` | `/letters/*` | 每日来信和偏好 |
| `GET/POST/DELETE` | `/stickers/*` | 表情包上传、生成、保存和删除 |
| `POST` | `/voice/asr` | 完整 PCM 识别降级链路 |
| `WS` | `/voice/asr/stream` | PCM 流式 ASR |
| `GET` | `/health/ready` | 数据库就绪检查 |
| `GET` | `/version` | 发布版本 |

`POST /chat/send` 在聊天模式返回文字、sources 和可选 content parts（表情包）；在通话模式额外返回 `audio_urls`，并禁用表情包工具。

## 运行约定

- 启动时 `db/postgres_schema.py` 幂等创建 PostgreSQL/pgvector schema。
- 语音上传只接受 `.pcm`；识别完成后删除临时上传文件。
- TTS 输出默认是 CosyVoice 生成的 `.mp3`，默认保留 1 小时；清理任务默认每 10 分钟运行一次。
- ASR 临时上传文件识别结束后立即删除，异常残留默认最多保留 5 分钟。
- 表情包搜索和发送由 Agent 工具完成，每轮最多成功发送一张。
- 日志经过敏感字段过滤，不记录 token、验证码、完整聊天正文或语音正文。

## 检查

```bash
python -B scripts/check_architecture.py
uv run pytest Echo-backend/tests -q
```

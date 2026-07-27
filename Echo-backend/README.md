# Echo Backend 1.0

Echo 后端基于 FastAPI，按 feature-first 与 Clean Architecture 组织。PostgreSQL + pgvector 是唯一存储实现。

## 启动

从仓库根目录启动：

```bash
docker compose up -d --build echo-postgres echo-backend
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8000/version
```

直接运行：

```bash
python -m pip install -r Echo-backend/requirements.txt
cd Echo-backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

直接运行时必须设置 `DATABASE_URL`。完整配置见 `.env.example`。

## 模块

```text
features/
  auth/                 微信登录与 Bearer 会话
  assistant_persona/    Echo 固定人格
  chat/                 对话、Prompt、摘要与记忆调度
  memory/               长期记忆与向量检索
  persona/              用户显式偏好与首次引导状态
  relationship/         关系阶段、边界和事件
  voice/                ASR、TTS 与音频生命周期
  system/               健康检查与版本
providers/              外部模型和语音供应商适配
shared/                 配置、鉴权、限流、日志安全
db/                     PostgreSQL 连接和幂等 schema
```

依赖规则：

```text
Interface -> Application -> Domain
Infrastructure -> Domain Protocol
Bootstrap 装配具体实现
```

跨 feature 调用经对方 `public.py`；Application 不直接访问数据库、FastAPI、配置或供应商 SDK。

## HTTP 契约

除 `/login`、健康检查和版本接口外，用户接口仅使用 Bearer Token 鉴权。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/login` | 微信登录并签发 Token |
| `GET/PUT` | `/persona/me` | 读取或保存用户偏好 |
| `POST` | `/persona/me/reset` | 恢复默认偏好，不重做首次引导 |
| `POST` | `/chat/send` | `mode=chat|call` 的完整回复 |
| `POST` | `/chat/clear` | 清除聊天上下文 |
| `GET/DELETE/POST` | `/memory/*` | 查看、删除和清空长期记忆 |
| `GET/POST` | `/relationship/me*` | 查看或重置关系阶段 |
| `POST` | `/voice/asr` | 完整 MP3 识别降级链路 |
| `WS` | `/voice/asr/stream` | 实时 ASR |

`POST /chat/send` 请求示例：

```json
{
  "message": "今天有点累",
  "mode": "chat"
}
```

响应只包含规范字段：

```json
{
  "reply": "听起来今天挺消耗人的。",
  "audio_urls": []
}
```

`call` 模式会注入口语渠道约束并生成 `audio_urls`；TTS 失败不会回滚已经生成和保存的文字回复。

## 配置重点

```dotenv
APP_VERSION=1.0.0
BUILD_REVISION=unknown
PROMPT_VERSION=echo-v1.0.0
DATABASE_URL=postgresql://echo:password@127.0.0.1:5432/echo
AUTH_TOKEN_SECRET=
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.deepseek.com
LLM_MODEL=
WECHAT_APPID=
WECHAT_SECRET=
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
TENCENT_APP_ID=0
VOICE_STREAMING_ASR_ENABLED=true
TTS_PROVIDER=cosyvoice
TTS_VOICE_ID=
DASHSCOPE_API_KEY=
DASHSCOPE_WORKSPACE_ID=
COSYVOICE_MODEL=cosyvoice-v3.5-flash
PUBLIC_BASE_URL=https://api.example.com
```

`PUBLIC_BASE_URL` 必须与小程序合法 HTTPS 域名一致，用于生成可访问的语音文件 URL。

## 数据库

应用启动时通过 `db/postgres_schema.py` 幂等初始化表和 pgvector 扩展。1.0 不读取或迁移 SQLite。

核心表包括 `users`、`conversations`、`chat_messages`、`user_personas`、`relationship_states`、`relationship_events`、`user_memories`、`memory_embeddings`、`background_jobs` 和 `voice_files`。

## 检查

从仓库根目录执行：

```bash
python -B scripts/check_architecture.py
python -B -m unittest discover -s Echo-backend/tests -v
```

部署后检查：

```bash
curl https://api.example.com/health/ready
curl https://api.example.com/version
docker compose logs --tail=200 echo-backend
```

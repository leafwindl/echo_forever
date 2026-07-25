# Echo Backend

Echo 后端是基于 FastAPI 的 AI 伴侣服务，当前已按 feature-first + clean architecture 收口。业务能力按模块拆分到 `features/`，顶层 `main.py` 只负责应用装配。

## 1. 快速启动

先启动 PostgreSQL + pgvector：

```bash
docker compose up -d echo-postgres
```

再启动后端：

```bash
cd Echo-backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

服务默认运行在：

```text
http://localhost:8000
```

## 2. 配置

配置集中在 `shared/config/settings.py`，通过环境变量或 `.env` 注入。

常用配置：

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
PROMPT_VERSION=echo-v0.3.0
PERSONA_PROMPT_MAX_TOKENS=400
MEMORY_PROMPT_MAX_TOKENS=800
SUMMARY_PROMPT_MAX_TOKENS=800
EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
WECHAT_APPID=
WECHAT_SECRET=
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
PUBLIC_BASE_URL=http://localhost:8000
DB_PROVIDER=postgres
DATABASE_URL=postgresql://echo:echo_dev_password@127.0.0.1:5432/echo
```

生产或预发布环境需要将 `PUBLIC_BASE_URL` 配置为当前后端公网 HTTPS 域名。该值会用于拼接语音文件访问地址，必须与小程序 `develop/trial/release` 环境中的 API 域名保持一致。

## 3. 数据库

当前默认数据库为：

```text
PostgreSQL + pgvector
```

本地直连示例：

```dotenv
DB_PROVIDER=postgres
DATABASE_URL=postgresql://echo:echo_dev_password@127.0.0.1:5432/echo
```

旧 SQLite 文件只作为迁移输入使用，默认位置仍是：

```text
data/echo_memory.db
```

本地直跑迁移脚本：

```bash
python -B scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path data/echo_memory.db \
  --database-url postgresql://echo:echo_dev_password@127.0.0.1:5432/echo
```

Docker Compose 部署时，先停止后端写入，再执行一次性迁移：

```bash
cp .env.compose.example .env
# 编辑根目录 .env，确保 POSTGRES_PASSWORD 与 DATABASE_URL_DOCKER 中的密码一致。
docker compose stop echo-backend
cp data/echo_memory.db data/echo_memory.pre-postgres.db
docker compose up -d echo-postgres
docker compose build echo-backend
docker compose run --rm echo-backend \
  python /app/scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path /app/data/echo_memory.db
docker compose up -d echo-backend
```

只修改 `DB_PROVIDER` 和 `DATABASE_URL` 不会自动搬运旧数据，迁移脚本成功输出各表数量后才表示数据导入完成。

根目录 `.env` 服务于 Docker Compose 和 PostgreSQL 容器；`Echo-backend/.env` 服务于后端业务配置。两者用途不同，均已被 Git 忽略。

## 4. 架构说明

当前后端按以下方向组织：

```text
Interface -> Application -> Domain
Infrastructure -> Domain 接口
Bootstrap 负责装配
```

目录结构：

```text
Echo-backend/
  main.py                 # FastAPI app 装配
  db/                     # 数据库连接与 schema 初始化
  providers/              # LLM / Embedding / TTS / ASR provider 与 registry
  shared/
    config/               # 配置入口
    interface/            # 跨 feature 的 HTTP 依赖
  features/
    auth/
    chat/
    memory/
    persona/
    voice/
    system/
```

每个业务 feature 尽量保持：

```text
feature/
  domain/                 # Entity、Value Object、Protocol、领域错误
  application/            # 用例编排
  infrastructure/         # DB/provider/file/外部服务适配
  interface/              # HTTP router 和 schema
  public.py               # 对其它模块暴露的稳定入口
  README.md               # 模块说明
```

## 5. 业务模块

- `features/auth`：登录与用户身份创建。
- `features/chat`：文本对话、上下文构建、会话摘要、记忆调度。
- `features/memory`：长期记忆抽取、管理、向量索引。
- `features/persona`：用户显式交流偏好、独立持久化与安全 API。
- `features/voice`：ASR、语音回复、TTS、音频文件存储。
- `features/system`：健康检查等系统级接口。

## 6. 架构检查与测试

```bash
python -B scripts/check_architecture.py
python -B -m unittest discover -s Echo-backend/tests
npx tsc --noEmit -p Web/tsconfig.json
```

架构检查会阻止旧兼容入口回流，例如：

```text
services/
api/
schemas/
config.py
llm_client.py
```

## 7. Docker Compose 部署

项目根目录已提供轻量后端容器部署：

```bash
docker compose up -d --build
docker compose logs -f echo-backend
```

容器会启动 PostgreSQL + pgvector，并将语音静态文件挂载到 `Echo-backend/static/`。详细部署和迁移说明见：

```text
doc/deploy/后端 Docker Compose 部署说明.md
```

## 8. 开发约束

- 新业务优先放入对应 `features/<module>`。
- Application 只能依赖 Domain 抽象，不直接依赖 DB、provider、FastAPI 或配置。
- Interface 只做 HTTP 契约、依赖注入和错误码映射。
- Infrastructure 负责适配数据库、第三方 SDK、文件系统和 provider；运行时数据库实现默认使用 PostgreSQL repository。
- 跨 feature 调用优先使用对方 `public.py`。
- 新增配置必须进入 `shared/config/settings.py`。
- 新增 provider 优先通过 `providers/registry.py` 注册。

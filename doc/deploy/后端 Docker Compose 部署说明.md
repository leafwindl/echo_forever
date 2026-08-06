# Echo 后端 Docker Compose 部署说明

> 历史部署记录：本文面向微信小程序和迁移阶段，不适用于 v1.0。当前部署请以仓库根目录 `deploy/README.md` 为准。

## 1. 部署目标

本方案只容器化 Echo 后端服务。微信小程序前端仍通过微信开发者工具上传，Nginx/HTTPS 后续在服务器宿主机上配置。

运行结构：

```text
微信小程序
  -> http://服务器IP:8000              # 域名未完成前仅用于后端自测
  -> https://api.xxx.cn               # 域名和 HTTPS 完成后的正式入口
  -> Nginx                            # 后续负责 HTTPS 和反向代理
  -> Docker Compose / FastAPI
  -> PostgreSQL + pgvector + static voice files
```

## 2. 服务器目录建议

建议服务器上使用固定目录：

```text
/opt/echo/app       # 项目代码
/opt/echo/data      # 旧 SQLite 迁移输入和临时数据
/opt/echo/logs      # 预留日志目录
/opt/echo/static    # 预留静态文件目录
```

当前 `docker-compose.yml` 默认在项目根目录挂载：

```text
./data                 -> /app/data
./Echo-backend/static  -> /app/Echo-backend/static
```

因此迁移服务器时，旧库迁移前要保留 `data/`，语音静态文件仍需保留 `Echo-backend/static/`。

## 3. 准备配置

在服务器上复制环境变量模板：

```bash
cp Echo-backend/.env.example Echo-backend/.env
```

域名未完成前，可先使用服务器 IP 自测：

```dotenv
PUBLIC_BASE_URL=http://服务器公网IP:8000
```

域名和 HTTPS 完成后改为：

```dotenv
PUBLIC_BASE_URL=https://api.xxx.cn
```

Docker Compose 会覆盖数据库运行配置：

```dotenv
DB_PROVIDER=postgres
DATABASE_URL=postgresql://echo:echo_dev_password@echo-postgres:5432/echo
```

旧 SQLite 文件只在执行迁移脚本时作为输入使用。

同时确认 `.env` 中已经配置：

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=
LLM_MODEL=

WECHAT_APPID=
WECHAT_SECRET=

TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
TENCENT_APP_ID=

MINIMAX_API_KEY=
MINIMAX_GROUP_ID=
MINIMAX_TTS_VOICE_ID=

EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=
EMBEDDING_MODEL=
```

不要把真实 `.env` 提交到 Git。

## 4. 启动后端

在项目根目录执行：

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f echo-backend
```

健康检查：

```bash
curl http://127.0.0.1:8000/
```

预期返回：

```json
{"status":"ok"}
```

## 5. 停止与更新

停止服务：

```bash
docker compose down
```

更新代码后重建：

```bash
git pull
docker compose up -d --build
```

只重启容器：

```bash
docker compose restart echo-backend
```

不要随意执行带 `-v` 的清理命令，避免误删 volume 数据。

## 6. 数据备份

当前默认使用 PostgreSQL，数据保存在 Docker volume：

```text
echo-postgres-data
```

旧 SQLite 数据迁移到 PostgreSQL：

```bash
python -B scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path data/echo_memory.db \
  --database-url postgresql://echo:echo_dev_password@127.0.0.1:5432/echo
```

PostgreSQL 自动备份已由 `echo-postgres-backup` 服务实现，默认每日备份并保留 7 天：

```bash
docker compose up -d echo-postgres-backup
docker compose logs -f echo-postgres-backup
ls -lah data/backups/postgres
```

手工备份和恢复命令见 `doc/deploy/上线安全与运维说明.md`。生产环境还应把备份同步到 COS，避免服务器磁盘故障时在线库和本地备份同时丢失。

## 7. 域名完成后的调整

域名审核、备案和 HTTPS 完成后：

1. 将 DNS `api.xxx.cn` 指向服务器公网 IP。
2. 配置 Nginx，将 `https://api.xxx.cn` 反向代理到 `http://127.0.0.1:8000`。
3. 将 `Echo-backend/.env` 的 `PUBLIC_BASE_URL` 改为 `https://api.xxx.cn`。
4. 将 `Web/miniprogram/utils/env.ts` 中的 `trial.apiBaseUrl` 改为 `https://api.xxx.cn`。
5. 在微信公众平台配置 `request`、`uploadFile`、`downloadFile` 合法域名。
6. 重启后端并上传小程序体验版测试。

Nginx 示例：

```nginx
server {
    listen 80;
    server_name api.xxx.cn;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

HTTPS 证书配置完成后，再开启 443。

## 8. 上线前仍需完成

- 鉴权复核：体验版必须保持 `ENABLE_LEGACY_USER_ID_AUTH=false`。
- 风控复核：应用配额已实现；服务器仍需应用 Nginx 请求体限制，并在第三方服务商控制台配置预算告警。
- 隐私合规：在微信后台配置隐私保护指引、用户协议、录音用途和长期记忆说明。
- 监控告警：当前已有最小请求日志和数据库就绪检查；仍需配置外部告警、磁盘监控和第三方 API 失败率统计。
- 存储升级：用户增长后将音频文件迁移到腾讯云 COS，将自建 PostgreSQL 迁移到托管数据库。

基础体验版发布前逐项执行 `doc/deploy/小程序基础体验版发布清单.md`。

# Echo 后端 Docker Compose 部署说明

## 1. 部署目标

本方案只容器化 Echo 后端服务。微信小程序前端仍通过微信开发者工具上传，Nginx/HTTPS 后续在服务器宿主机上配置。

运行结构：

```text
微信小程序
  -> http://服务器IP:8000              # 域名未完成前仅用于后端自测
  -> https://api.xxx.cn               # 域名和 HTTPS 完成后的正式入口
  -> Nginx                            # 后续负责 HTTPS 和反向代理
  -> Docker Compose / FastAPI
  -> SQLite + static voice files
```

## 2. 服务器目录建议

建议服务器上使用固定目录：

```text
/opt/echo/app       # 项目代码
/opt/echo/data      # SQLite 数据库
/opt/echo/logs      # 预留日志目录
/opt/echo/static    # 预留静态文件目录
```

当前 `docker-compose.yml` 默认在项目根目录挂载：

```text
./data                 -> /app/data
./Echo-backend/static  -> /app/Echo-backend/static
```

因此迁移服务器时，至少要保留 `data/` 和 `Echo-backend/static/`。

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

`ECHO_DB_PATH` 已由 `docker-compose.yml` 覆盖为 `/app/data/echo_memory.db`，通常不需要在 `.env` 中重复配置。

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

当前 MVP 使用 SQLite，核心数据在：

```text
data/echo_memory.db
```

建议至少每天备份一次：

```bash
cp data/echo_memory.db data/backup/echo_memory_$(date +%Y%m%d_%H%M%S).db
```

生产公开前建议补充更稳的备份策略，后续用户增长后再迁移到托管数据库。

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

- 正式鉴权：登录后签发 token，生产环境不再信任前端传入的 `user_id`。
- 基础风控：输入长度、语音大小、请求频率、第三方 API 成本保护。
- 隐私合规：隐私政策、用户协议、录音用途说明、长期记忆说明。
- 监控告警：错误日志、第三方 API 失败率、接口耗时、磁盘占用。
- 存储升级：用户增长后将音频文件迁移到腾讯云 COS，将 SQLite 迁移到托管数据库。

# Echo 1.0

Echo 是一个原生 Flutter 客户端 + FastAPI 服务端组成的 AI 陪伴应用。v1.0 聚焦稳定的基础体验：手机号登录、首次引导、文字聊天、Agent 工具编排、表情包、长期记忆、每日来信、人物显示和 PCM 语音通话。

## 目录

```text
app/                    Flutter Android/iOS 客户端
Echo-backend/           FastAPI 服务端
assets/                 客户端与设计素材
doc/                    业务、部署和研究文档
deploy/                 Docker/Nginx 部署文件
scripts/                架构检查和运维脚本
docker-compose.yml      PostgreSQL、后端和依赖服务编排
```

## 架构边界

后端采用 feature-first Clean Architecture：

```text
Interface -> Application -> Domain
Infrastructure -> Domain Protocol
Bootstrap/main.py 负责装配具体 provider、repository 和配置
```

运行时数据库只有 PostgreSQL + pgvector。LLM、Embedding、ASR、TTS、图片生成和联网搜索都通过 provider 适配层接入。应用层和领域层不读取环境配置，也不直接依赖具体 SDK。

Flutter 按 `core / features / shared` 组织。页面只负责状态展示和用户交互，网络请求集中在 feature 的 data 层，领域模型不依赖 Dio 或 Flutter UI。

## 本地启动

```bash
docker compose up -d --build echo-postgres echo-backend
curl http://127.0.0.1:8000/health/ready
```

后端配置复制 `Echo-backend/.env.example` 到 `Echo-backend/.env`。不要把生产密钥写入 Git。

Flutter 调试：

```bash
cd app
flutter pub get
flutter run -d <device> --dart-define=ECHO_BASE_URL=http://localhost:8000
```

## 语音约定

- APP 录音格式：16 kHz、单声道、PCM16LE 裸音频。
- 流式识别：`WS /voice/asr/stream`。
- 整段降级识别：`POST /voice/asr`，上传 `.pcm`，媒体类型 `audio/L16`。
- 通话回复：`POST /chat/send` 的 `mode=call`，CosyVoice 生成 MP3 供 APP 播放。
- 通话模式不启用表情包工具。

## 验证

```bash
python -B scripts/check_architecture.py
uv run pytest Echo-backend/tests -q
cd app
flutter analyze
flutter test
```

业务流程、数据流、数据库表和扩展方式见 [`doc/Echo v1.0 业务流程与数据流.md`](doc/Echo%20v1.0%20业务流程与数据流.md)。

## 版本

- APP：`1.0.0+1`
- Backend `APP_VERSION`：`1.0.0`
- Prompt：`echo-v1.0.0`
- Persona：`echo-persona-v1`

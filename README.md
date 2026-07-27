# Echo 1.0

Echo 是原生微信小程序形态的 AI 陪伴产品。1.0 聚焦一条可发布的基础体验：首次认识用户、文字聊天、独立语音通话、稳定人格、用户偏好、关系阶段和长期记忆。

## 1.0 用户流程

1. 小程序启动后通过 `wx.login()` 建立 Bearer 会话。
2. 新用户先填写称呼、聊天风格、支持方式、关系节奏和可选自述。
3. 完成首次设置后进入 Echo 人物与文字聊天页。
4. 点击“通话”进入独立电话界面，按住说话；松手后完成 ASR、对话和 TTS 播放。
5. 用户可在设置中修改偏好、管理长期记忆或重置关系进度。

已完成首次设置的用户会直接进入聊天页。恢复默认偏好不会重复触发首次引导。

## 核心契约

- 所有用户接口只接受 `Authorization: Bearer <token>`，不接受请求体、查询参数或自定义 Header 中的 `user_id`。
- `POST /chat/send` 使用 `mode=chat|call`。`chat` 只返回文字；`call` 使用更口语化的 Prompt，并返回 `audio_urls`。
- 文字和 TTS 均在完整生成后一次返回。电话 ASR 优先使用 WebSocket 实时识别，失败时自动上传完整 MP3 降级识别。
- PostgreSQL + pgvector 是 1.0 唯一数据库实现，不承接旧 SQLite 数据。

## 项目结构

```text
Echo-backend/             FastAPI 后端
  features/               feature-first 业务模块
  providers/              LLM / ASR / TTS / Embedding 供应商适配
  shared/                 配置、鉴权、限流与日志安全
  db/                     PostgreSQL 连接与 schema
Web/miniprogram/           原生微信小程序
  pages/                  onboarding / chat / call / persona / memory
  services/               录音流、ASR 上传和音频播放
  utils/                  API、环境与登录态
scripts/                   架构检查、数据库初始化和运维脚本
doc/                       研究、测试与部署资料
```

后端模块依赖方向：

```text
Interface -> Application -> Domain
Infrastructure ---------> Domain Protocol
main.py 负责应用装配
```

前端依赖方向：

```text
Page -> services / utils
services -> utils
utils 不依赖 Page
```

## 本地启动

```bash
docker compose up -d --build echo-postgres echo-backend
docker compose ps
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8000/version
```

微信开发者工具打开 `Web/`。开发环境 API 默认为 `http://127.0.0.1:8000`，体验版和正式版使用 `https://api.echoaiforever.cn`，配置位于 `Web/miniprogram/utils/env.ts`。

后端配置复制自 `Echo-backend/.env.example`。部署必填项包括微信凭据、Token 密钥、PostgreSQL、LLM；语音通话还需要腾讯 ASR 和 CosyVoice 凭据及定制音色 ID。

## 验证

```bash
python -B scripts/check_architecture.py
python -B -m unittest discover -s Echo-backend/tests -v
npx tsc --noEmit -p Web/tsconfig.json
```

发布前还应在微信真机完成：新用户首次引导、已有用户直达聊天、文字消息、通话权限拒绝与重试、ASR 降级、TTS 播放、登录过期、记忆删除和清空。

## 版本

- 应用版本：`1.0.0`
- Prompt 版本：`echo-v1.0.0`
- 用户偏好 schema：`3`
- Echo 助手人格：`echo-persona-v1`

运行版本以 `/version` 返回值为准。

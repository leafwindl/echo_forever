# Echo

Echo 是一个面向个人用户的 AI 陪伴应用，由 Flutter 客户端和 FastAPI 服务端组成。它把连续文字聊天、主动联系、定时提醒、语音通话、学习专注、表情包、长期记忆和每日来信放在同一条可持久化的陪伴链路中。

当前生产版本：**v1.1.9**

| 部件 | 当前值 |
| --- | --- |
| Android APK | `1.1.9+25` |
| Android 包名 | `cn.echoaiforever.echo_app` |
| 公网 API | `https://api.echoaiforever.cn` |
| APK 下载域名 | `https://download.echoaiforever.cn` |
| 生产分支 | `master`；实际版本以 `/health` 返回为准 |
| 数据库 | PostgreSQL 16 + pgvector |
| 推送 | 个推 RestAPI V2 主通道 |

## 当前能力

- 手机号验证码登录、刷新会话和安全退出。
- 首次引导、Echo 人格、用户偏好和关系阶段。
- 异步文字聊天：用户可以连续发送文字或表情包，Echo 回复以多段文字和独立图片逐步到达。
- SSE 实时交付、断线补偿和聊天历史游标分页；聊天记录保存在服务端，不因退出 APP 消失。
- Agent 工具编排：可靠时间、可选联网搜索、表情包搜索与发送、主动聊天任务管理。
- 表情包库：官方表情包、用户私人表情包、语义标签、优先级和冷却机制。
- 长期记忆、对话摘要、关系事件和用户可管理的记忆页面。
- PCM 语音通话：16 kHz、单声道、PCM16LE，WebSocket 流式 ASR 失败时降级为整段 PCM 识别，CosyVoice 返回语音。
- 每日来信：独立的来信生成、发布、未读和已读链路。
- 主动聊天与提醒：每日/每周/一次性任务、安静时段、频率策略、未回复暂停和任务管理。
- 个推通知：前台提醒、后台通知、点击进入聊天；消息先落库，通知只是到达提醒。
- 应用内更新：服务端发布版本元数据，客户端校验包名、版本号、SHA-256 后请求 Android 安装器。
- Echo 人物显示：使用 `app/assets/character/` 中的 idle 和 sit 素材。
- 产品展示站：实时读取公开 Android 发布记录，展示当前版本、发布日期和更新说明。
- Windows 电脑节点：独立桌面客户端显示连接状态和操作日志；可配置总是允许，打开网易云音乐、控制播放、看屏幕和单次看摄像头；图片只转成文字描述，不落盘。

## 仓库结构

```text
app/                    Flutter 客户端
Echo-backend/           FastAPI 服务端
assets/                 官方表情包、Echo 品牌和设计素材
doc/                    业务流程、展示说明、部署和测试文档
deploy/                 Docker、Nginx 和发布说明
site/                   Echo 产品展示站
desktop_node/           独立的 Windows 电脑节点（Python，不混入 App）
scripts/                架构检查、COS、APK 和电脑节点配对脚本
docker-compose.yml      PostgreSQL、后端和备份服务编排
```

## 架构边界

后续开发与清理统一遵守 [`doc/Echo 后端架构与代码规范.md`](doc/Echo%20后端架构与代码规范.md)，根目录 `AGENTS.md` 是开发入口。共享提示渲染现位于 `Echo-backend/shared/prompting/`；六类提示资产的完整注册与按需选择尚未实现，不预建占位目录或接口。

```text
Flutter UI
  -> feature data/repository
  -> authenticated HTTP / SSE / WebSocket
  -> FastAPI interface
  -> application service
  -> domain policy
  -> PostgreSQL / provider adapters / COS / Getui
```

服务端采用 feature-first Clean Architecture。接口层负责鉴权、校验和 HTTP 契约，应用层编排业务，领域层保存规则，基础设施层连接 PostgreSQL、模型、语音、COS 和个推。Agent 只能通过注册工具访问业务能力，不能直接写数据库。

客户端采用 `core / features / shared` 分层。文字聊天和主动消息走异步消息链路，语音通话走独立的同步链路；通话不触发主动聊天和表情包工具。

## 本地开发

### 1. 启动服务端依赖

```bash
copy Echo-backend/.env.example Echo-backend/.env
docker compose up -d --build echo-postgres echo-backend
curl http://127.0.0.1:8000/health/ready
```

真实密钥只写入被 Git 忽略的 `Echo-backend/.env`。本地可以使用固定验证码进行封闭测试，生产环境必须替换为正式短信服务。

### 2. 运行 Flutter 客户端

```bash
cd app
flutter pub get
flutter run -d <device> --dart-define=ECHO_BASE_URL=http://localhost:8000
```

生产 APK 在本地构建，服务器只运行后端：

```powershell
cd app
flutter build apk --release --no-pub `
  --dart-define=ECHO_ENV=production `
  --dart-define=ECHO_BASE_URL=https://api.echoaiforever.cn `
  --dart-define=APP_VERSION=1.1.0
```

APK 构建后由发布脚本上传 COS，并把版本元数据写入生产 PostgreSQL。不要在服务器构建 APK，也不要把签名文件、个推服务端密钥或 COS 密钥提交到 Git。

## 生产部署边界

- 服务器目录：`/opt/echo/app/`。
- 服务器只拉取仓库、构建并运行后端 Docker 服务。
- PostgreSQL 和后端端口只绑定本机，公网入口由 Nginx/API 域名提供。
- APK 从本机生成后直接上传 COS，用户从 APP 内检查更新并由 Android 系统安装。
- 生产环境的个推 `AppKey`、`MasterSecret`、LLM、TTS、ASR 和 COS 密钥只保存在服务器 `.env`。
- 当前个推主通道可用于在线、后台和锁屏测试；华为、荣耀、小米、OPPO、vivo 厂商离线通道尚未全部配置，不能把进程被系统彻底清理后的到达率当作最终承诺。

部署命令和证书、COS 细节见 [`deploy/README.md`](deploy/README.md)。

## 检查

```bash
python -B scripts/check_architecture.py
uv run pytest Echo-backend/tests -q
cd app
flutter analyze
flutter test
```

当前发布检查结果：Flutter analyze 0 issues，客户端 119 项测试通过，后端 296 项测试通过，架构检查通过。

## 文档入口

- [`Echo-backend/README.md`](Echo-backend/README.md)：服务端模块、接口、配置和数据流。
- [`app/README.md`](app/README.md)：客户端页面、消息交互、构建和测试。
- [`doc/Echo v1.0.9 当前功能与扩展基线.md`](doc/Echo%20v1.0.9%20当前功能与扩展基线.md)：当前版本的业务逻辑、对话/来信边界和新功能接入规则。
- [`doc/Echo v1.0 业务流程与数据流.md`](doc/Echo%20v1.0%20业务流程与数据流.md)：v1.0 早期业务链路历史基线，仅用于追溯。
- [`doc/Echo v1.0.7 功能业务与展示站说明.md`](doc/Echo%20v1.0.7%20功能业务与展示站说明.md)：v1.0.7 展示站历史快照，仅用于追溯。
- [`doc/README.md`](doc/README.md)：文档索引和历史资料边界。

## 安全原则

不要在代码、Flutter 构建参数、APK、日志、截图或文档中写入服务端密钥。聊天正文、语音正文、验证码、访问令牌和个推 CID 不进入普通日志。所有新增功能都应先确定数据归属、权限、失败状态和清理策略，再接入 Agent 或前端页面。

# Echo App

Echo App 是 Echo 的 Flutter 客户端。当前生产 APK 为 `1.0.7+12`，用户可见版本显示为 `v1.0.7`；`+12` 是 Android 用于判断升级顺序的内部 `versionCode`，不会显示在聊天界面。

| 项目 | 当前值 |
| --- | --- |
| 包名 | `cn.echoaiforever.echo_app` |
| 生产 API | `https://api.echoaiforever.cn` |
| 架构 | `core / features / shared` |
| Android 推送 | 个推 Flutter 插件 vendored 到 `third_party/getuiflut/` |
| 人物素材 | `assets/character/echo_idle.png`、`assets/character/idle_sit.png` |

## 用户功能

### 登录与首次使用

1. 输入手机号请求验证码。
2. 验证成功后保存 access/refresh session 到 secure storage。
3. 首次进入 onboarding，填写用户称呼、偏好等信息。
4. 完成后进入聊天首页；下次启动恢复会话和聊天历史。

### 文字聊天

- 用户消息先在本地显示，再以 `client_message_id` 提交服务端。
- 文字和表情包都是独立消息，可以在 Echo 回复期间继续发送。
- Echo 的多段文字按顺序逐段显示，段间保留短暂延迟，形成自然的打字节奏。
- Echo 回复中的文字和表情包分开渲染，图片不会被包进文字气泡。
- 前十条历史在进入页面时加载；向上滚动时通过 `before_id` 懒加载更早消息。
- SSE 断线后按 `after_id` 补回遗漏消息，不依赖本地缓存作为唯一历史来源。
- “清除聊天上下文”会删除当前聊天消息、摘要和未完成回合，但不删除长期记忆、人格偏好或关系数据。

### 表情包

- 表情包库支持查看、上传、保存和删除。
- 上传时必须填写描述和语义标签，服务端保存元数据并校验图片类型与大小。
- 用户点击表情包后立即发送为独立消息，不经过文字输入框。
- Echo 通过 Agent 的 `search_stickers -> send_sticker` 工具选择表情包。
- 官方表情包优先但不会绝对独占；私人表情包也可参与语义排序。
- 每轮最多成功发送一张，最近使用的表情包会按轮次和时间冷却。

### 语音通话

- 录音格式固定为 16 kHz、单声道、PCM16LE。
- 优先通过 `WS /voice/asr/stream` 获取 partial/final 识别结果。
- 流式链路失败时上传整段 PCM 到 `/voice/asr`。
- 识别文本提交 `/chat/send` 的 `mode=call`，返回 CosyVoice 音频并在客户端播放。
- 通话是独立的同步链路，不发送表情包、不创建主动任务，也不触发系统通知。

### 主动聊天、提醒与通知

- “主动聊天设置”页面管理主动开关、频率档位、时区、安静时段和通知正文预览。
- “定时任务”独立页面管理一次性、每日、每周任务；用户可以查看、暂停、恢复和删除任务。
- 已执行或过期的一次性任务由服务端自动清理，任务列表只展示进行中和已暂停的任务。
- Echo 自主创建的后续联系必须是用户可见的一次性任务，并受频率和未回复暂停策略约束。
- 前台收到主动消息时显示应用内提示；后台收到个推通知时，点击通知进入聊天页。
- 消息已经先写入服务端聊天历史，通知失败不会丢消息。

### 其他页面

- 个性化设置：查看和编辑用户偏好。
- 长期记忆：查看、删除或清空 Echo 已保存的记忆。
- Echo 来信：查看每日来信、未读数量和已读状态。
- 检查更新：读取服务端发布信息，下载、校验并启动 Android 安装器。
- 人物显示：聊天收起时使用 idle 素材，展开输入时使用 sit 素材。

## 客户端数据流

```text
页面操作
  -> Riverpod Controller
  -> feature Repository / Dio
  -> Bearer HTTP、SSE 或 WebSocket
  -> 服务端持久化和 Worker
  -> 事件、历史或通知回到客户端
  -> 状态合并、动画和 UI 展示
```

客户端不保存服务端密钥。个推 AppID 通过 Android `local.properties` 或构建环境注入，AppKey 和 MasterSecret 永远只在后端。

## 路由

| 路径 | 页面 |
| --- | --- |
| `/login`、`/verify` | 手机号登录和验证码 |
| `/onboarding` | 首次引导 |
| `/chat`、`/home` | 聊天首页和人物显示 |
| `/call` | PCM 语音通话 |
| `/persona` | 个性化设置 |
| `/memory` | 长期记忆 |
| `/letters` | Echo 来信 |
| `/stickers` | 表情包库 |
| `/notification-settings` | 通知设置 |
| `/proactive-chat-settings` | 主动聊天设置 |
| `/scheduled-tasks` | 定时任务管理 |

## 本地运行

```bash
flutter pub get
flutter run -d <device> --dart-define=ECHO_BASE_URL=http://localhost:8000
```

模拟器使用宿主机后端时可以使用 `http://localhost:8000`；真机调试需要按照当前网络环境配置 `adb reverse` 或使用可访问的开发 API 地址。

## 构建生产 APK

服务器只部署后端，APK 在本地构建并上传 COS：

```powershell
flutter build apk --release --no-pub `
  --dart-define=ECHO_ENV=production `
  --dart-define=ECHO_BASE_URL=https://api.echoaiforever.cn `
  --dart-define=APP_VERSION=1.0.7
```

`android/key.properties`、`android/local.properties` 和 COS/个推服务端密钥都被 Git 忽略。发布脚本会校验包名、版本号、文件大小和 SHA-256，然后上传 COS 并登记 `app_releases`。

## 通知限制

当前 APP 接入个推主通道，在线、普通后台和部分锁屏场景可测试。华为、荣耀、小米、OPPO、vivo 的厂商离线通道尚未全部配置；用户手动“强行停止”APP 时不承诺通知到达。系统通知正文默认隐藏，用户可以在通知设置中开启预览。

## 检查

```bash
flutter analyze
flutter test
```

当前发布结果：Flutter analyze 0 issues，111 项测试全部通过。

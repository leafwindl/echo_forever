# Echo 微信小程序迁移 Flutter APP 开发计划

> 文档状态：开发基线草案  
> 适用版本：Echo APP v2.0  
> 目标平台：Android 优先，随后开启 iOS  
> 工程位置：monorepo 根目录下 `app/`，与 `Echo-backend/`、`Web/` 并列  
> 契约核对日期：2026-08-03

## 1. 概述与目标

### 1.1 迁移目标

本项目将 Echo 的原生微信小程序客户端迁移为 Flutter APP，保持 Echo 作为 AI 陪伴助手的核心体验，同时获得独立 APP 在后台音频、系统通知、平台权限和后续原生能力扩展方面的能力。

v2.0 的目标如下：

- 新建 Flutter 双端工程，先完成并验收 Android，再开启 iOS 构建、签名与平台适配。
- 复用 `Echo-backend/` 的 FastAPI、Clean Architecture、PostgreSQL 与 pgvector 能力；除认证域、推送 token 存储和本文明确列出的兼容性门禁外，不重写后端业务。
- 以手机号、短信验证码和 JWT 登录替换微信 code 登录，建立 access token 自动刷新及 refresh token 轮换机制。
- 完整迁移小程序的七个页面：`onboarding`、`chat`、`call`、`persona`、`memory`、`stickers`、`letters`。
- 一期完成工程骨架、认证、聊天和电话模式，其中电话模式必须包含流式 ASR、整段 ASR 降级、TTS 播放、前后台切换与 Android 后台音频保活。
- 二期迁移 `persona`、`memory`、`stickers`、`letters`、`onboarding`，接入通知，并完成 Android 发布级收口。
- v2.0 角色展示继续使用静态图和轻量动效；通过 `CharacterRenderer` 抽象隔离渲染实现，为后续官方 Live2D SDK 原生桥接保留接入点。

### 1.2 迁移范围

客户端范围包括：

- Flutter 工程、Android/iOS 平台壳、环境配置、路由、主题、权限和生命周期管理。
- Dio 网络层、认证会话、错误映射、统一日志与敏感信息脱敏。
- Riverpod 状态管理及 feature-first 模块边界。
- 文本聊天、消息来源、表情内容、清除上下文和电话模式。
- 麦克风采集、WebSocket 流式 ASR、HTTP 整段 ASR 降级、分段音频播放、音频焦点、后台播放与通知栏控制。
- Persona、关系进度、长期记忆、表情包、Echo 来信和首次个性化引导。
- APNs、FCM、推送 token 上报、通知点击路由。
- 本地安全存储、偏好缓存、测试基础设施、监控埋点和发布验收。

后端范围包括：

- 认证 feature 改造：短信挑战、手机号验证、标准 JWT access token、refresh token 轮换/撤销。
- `users` 表增加唯一手机号字段并移除仅服务微信登录的 `openid` 字段；新增短信挑战与 refresh token 的持久化结构。
- 新增 `push_tokens` 表及最小 token 注册/注销契约。
- 保留现有聊天、Persona、记忆、关系、来信、表情包和语音业务契约。

### 1.3 非目标

以下内容不进入 v2.0：

- 不重写 AI、记忆、关系、Persona、信件、表情包、ASR 或 TTS 业务逻辑。
- 不把服务端聊天记录全量同步为离线消息数据库；现有后端没有历史会话查询契约，v2.0 不另行扩展。
- 不做 Live2D 成品接入、模型制作或动画状态编排；仅保留抽象接口。
- 不在首发阶段接入华为、小米、OPPO、vivo 等厂商推送；国内 Android 聚合通道后置到个推/极光方案评估。
- 不实现端到端加密聊天、多人会话、音视频通话或实时双工语音打断。
- 不在一期公开发布一个绕过个性化引导的版本；一期是内部可验收增量，公开发布需完成二期。
- 不在客户端保存短信验证码、原始录音、完整通话转写或长期聊天正文。
- 不兼容或继续运行小程序代码，不迁移任何小程序数据，包括登录态、聊天、记忆和关系数据。

### 1.4 现状基线与来源

本文描述现有行为时以仓库代码为唯一基线。规划中的新接口会明确标注为“目标契约”，不得与现状混用。

| 主题 | 对齐文件 | 已确认现状 |
| --- | --- | --- |
| 小程序 HTTP 封装 | `Web/miniprogram/utils/api.ts` | BaseURL、Bearer header、各业务响应字段和 401/409/429 的页面语义 |
| 小程序登录态 | `Web/miniprogram/utils/session.ts` | 微信 `wx.login`、`/login`、本地 `user_id/access_token`；当前没有 refresh token |
| WebSocket ASR | `Web/miniprogram/services/voice-stream.ts` | `/voice/asr/stream`、Bearer header、`ready/partial/final/error`、`stop/cancel`、5 秒连接与 15 秒 final 超时 |
| 整段 ASR | `Web/miniprogram/services/voice-asr.ts` | `multipart/form-data` 字段名 `audio`，响应 `user_text`，401/413/429 分支 |
| TTS 播放 | `Web/miniprogram/services/audio-player.ts` | 顺序播放 `audio_urls`，播放当前段时预下载下一段，可取消 |
| 小程序录音/电话状态 | `Web/miniprogram/pages/call/call.ts` | 最长 60 秒、16 kHz、单声道、MP3、4 KB 分片、流式失败回退整段 ASR |
| 七页面交互 | `Web/miniprogram/pages/*` | 页面状态、表单规则、跳转、确认操作、空态及错误态 |
| 角色组件 | `Web/miniprogram/components/character/*` | `idle/sit` 两张静态图按聊天展开状态切换 |
| 当前认证后端 | `Echo-backend/features/auth/interface/router.py`、`schemas.py`、`application/login.py` | `POST /login` 用微信 code 换身份；返回 access token；没有刷新接口 |
| 当前 token 校验 | `Echo-backend/shared/security/token_service.py`、`shared/interface/dependencies.py` | 当前 token 是自定义两段 HMAC token，不是标准三段 JWT；业务接口统一解析 Bearer token |
| HTTP 业务契约 | `Echo-backend/features/*/interface/router.py`、`schemas.py` | FastAPI 原生响应；错误体主要为 `{"detail": ...}`，当前没有统一业务 `code` |
| WS 服务端协议 | `Echo-backend/features/voice/interface/router.py` | 连接关闭码、二进制帧、文本控制消息和服务端 JSON 消息 |
| 腾讯流式 ASR 适配 | `Echo-backend/features/voice/infrastructure/streaming_asr.py` | 当前上游 `voice_format=8`，即 MP3；引擎默认 `16k_zh`，VAD 静音 800 ms |
| 语音限制 | `Echo-backend/shared/config/settings.py` | 默认上传上限 10 MiB、5 次/60 秒、每用户每日 30 次、final 超时 10 秒 |
| 数据库基线 | `Echo-backend/db/postgres_schema.py` | `users` 目前有 `openid`，没有 `phone`、refresh token 和 push token 表 |

### 1.5 关键原则

- 先冻结契约，再写 UI；认证和语音必须先通过契约测试。
- feature-first 目录用于隔离业务，跨 feature 能力只能进入 `core` 或 `shared`，禁止页面直接依赖 Dio、插件或本地存储实现。
- access token、refresh token、手机号和推送 token 均按敏感信息处理，不写明文日志。
- 网络恢复不能制造重复消息；聊天发送、上传和删除等有副作用请求不做盲目自动重试。
- Android 先形成可发布闭环；iOS 共享 Dart 业务层，但平台权限、音频会话、APNs 和商店合规单独验收。

## 2. 技术栈与依赖清单

### 2.1 基础技术栈

| 层级 | 选型 | 用途与理由 |
| --- | --- | --- |
| UI/跨端 | Flutter + Dart | 一套业务代码覆盖 iOS/Android；平台音频与通知仍可通过插件或原生桥接实现 |
| 状态管理 | Riverpod | 依赖注入、可组合异步状态、自动释放和测试 override 机制适合 feature-first 架构 |
| 路由 | `go_router` | 支持登录守卫、冷启动 deep link、通知点击重定向和声明式页面栈 |
| HTTP | `dio` | 拦截器、请求取消、multipart、超时配置及细粒度错误信息满足现有 API 封装迁移 |
| 实时通道 | `web_socket_channel` | 跨平台 WebSocket 抽象轻量，足以实现现有二进制帧 + JSON 控制协议 |
| 录音 | `record` | 提供 Android/iOS 麦克风权限与音频流，目标采集 16 kHz、16-bit、mono、little-endian PCM |
| 播放 | `just_audio` | 支持 URL/播放列表、预加载、音频焦点协作和低延迟顺序播放 |
| 后台音频 | `audio_service` | Android 前台服务、通知栏媒体控制及 iOS 后台音频入口，是 APP 相对小程序的核心增量 |
| 音频会话 | `audio_session` | 统一录音/播放切换、音频焦点、耳机和系统中断处理，避免采播互相抢占 |
| 推送 | `firebase_core`、`firebase_messaging` | Android 通过 FCM；iOS 由 Firebase Messaging 对接 APNs token/消息回调，Dart 层共享处理入口 |
| 安全存储 | `flutter_secure_storage` | access/refresh token、设备标识等敏感数据使用 Android Keystore 与 iOS Keychain |
| 轻量偏好 | `shared_preferences` | 保存非敏感、可丢失的 UI 偏好和 schema version；不存 token 或聊天正文 |
| 权限 | `permission_handler` | 统一麦克风和通知权限查询、申请及跳转系统设置 |
| 网络图片 | `cached_network_image` | 表情包和远程资源的缓存、占位及失败态 |
| 图片选择 | `image_picker` | 迁移小程序 `chooseMedia` 的单图选择能力 |
| 外链 | `url_launcher` | 打开聊天来源链接；APP 不再以复制链接作为唯一行为 |
| 标识 | `uuid` | 设备安装 ID、客户端 request ID 和本地临时实体标识 |
| 文件路径 | `path_provider` | 管理录音降级文件和播放器临时缓存目录 |
| 模型序列化 | `json_annotation`、`json_serializable`、`build_runner` | 降低 snake_case 契约的手工解析错误；生成物纳入静态检查 |
| 不可变模型（可选） | `freezed`、`freezed_annotation` | 用于状态联合类型和不可变 copy；一期 spike 后决定，避免仅为少量模型引入过多生成代码 |
| 日志 | `logging` 或项目内轻量 logger facade | 统一级别、request ID、脱敏和生产关闭策略；业务层不直接 `print` |
| 单元/Mock | `flutter_test`、`mocktail` | Riverpod、repository、状态机和插件适配层测试 |
| 集成测试 | `integration_test` | Android/iOS 真机流程、权限、生命周期、推送点击和音频链路回归 |

### 2.2 版本策略

- Flutter 使用项目启动时的最新 stable channel；Dart SDK 约束跟随该 Flutter stable 自带版本。
- 所有运行时依赖在工程初始化日选择 pub.dev 最新稳定版，不使用 beta、dev、git commit 或未发布分支。
- `pubspec.yaml` 使用兼容的 caret 约束；`pubspec.lock` 必须提交，CI 与发布构建严格按 lockfile 解析。
- `dio`、`flutter_riverpod`、`go_router`、`record`、`just_audio`、`audio_service`、`firebase_messaging` 属于受控升级包：升级必须经过 changelog 检查、Android 真机语音回归和通知冷启动回归。
- 每月执行一次依赖审计；安全修复可走补丁升级，主版本升级独立 PR，不与功能开发混合。
- Android `minSdk`、`targetSdk`、Gradle/AGP/Kotlin 和 iOS deployment target 由所选 Flutter stable 与插件最新稳定版共同决定，并在工程骨架里锁定；不得为了兼容过旧设备而降级安全组件。
- 依赖清单中的“可选”包只有在一期 spike 证明收益后加入，避免无使用场景的依赖膨胀。

### 2.3 平台配置边界

- Android 首期完成 package name、签名占位、网络安全配置、麦克风/通知/前台服务权限、Firebase 配置和音频服务声明。
- iOS 工程随 Flutter 一起保留，但在 Android 一期通过后才配置 bundle ID、证书、APNs key、Background Modes、隐私说明和 TestFlight。
- `google-services.json`、`GoogleService-Info.plist`、APNs `.p8`、短信服务密钥和后端服务账号均不提交公开仓库；通过 CI secret 与环境注入管理。

## 3. 工程结构

目标目录如下。此树表示最终工程边界，不表示本计划文档阶段创建这些文件。

```text
app/
├── android/
│   └── app/
├── ios/
│   └── Runner/
├── assets/
│   ├── images/
│   │   └── character/
│   ├── animations/
│   └── fonts/
├── docs/
│   └── development-plan.md
├── integration_test/
│   ├── auth_flow_test.dart
│   ├── chat_flow_test.dart
│   ├── call_flow_test.dart
│   └── notification_route_test.dart
├── lib/
│   ├── main.dart
│   ├── bootstrap.dart
│   ├── app.dart
│   ├── core/
│   │   ├── config/
│   │   │   ├── app_config.dart
│   │   │   ├── app_environment.dart
│   │   │   └── build_info.dart
│   │   ├── network/
│   │   │   ├── dio_client.dart
│   │   │   ├── endpoints.dart
│   │   │   ├── interceptors/
│   │   │   │   ├── auth_interceptor.dart
│   │   │   │   ├── error_interceptor.dart
│   │   │   │   ├── request_id_interceptor.dart
│   │   │   │   └── safe_log_interceptor.dart
│   │   │   ├── token_refresh_coordinator.dart
│   │   │   └── network_status.dart
│   │   ├── auth_session/
│   │   │   ├── session_controller.dart
│   │   │   ├── session_snapshot.dart
│   │   │   └── session_events.dart
│   │   ├── storage/
│   │   │   ├── secure_store.dart
│   │   │   ├── preferences_store.dart
│   │   │   └── storage_keys.dart
│   │   ├── routing/
│   │   │   ├── app_router.dart
│   │   │   ├── route_names.dart
│   │   │   ├── auth_redirect.dart
│   │   │   └── pending_route_store.dart
│   │   ├── errors/
│   │   │   ├── app_exception.dart
│   │   │   ├── error_code.dart
│   │   │   └── error_message_mapper.dart
│   │   ├── lifecycle/
│   │   │   ├── app_lifecycle_observer.dart
│   │   │   └── connectivity_recovery.dart
│   │   ├── observability/
│   │   │   ├── app_logger.dart
│   │   │   ├── redaction.dart
│   │   │   └── metrics.dart
│   │   └── theme/
│   │       ├── app_theme.dart
│   │       ├── app_colors.dart
│   │       └── app_typography.dart
│   ├── features/
│   │   ├── auth/
│   │   │   ├── data/
│   │   │   │   ├── auth_api.dart
│   │   │   │   ├── auth_repository_impl.dart
│   │   │   │   └── dto/
│   │   │   ├── domain/
│   │   │   │   ├── auth_repository.dart
│   │   │   │   ├── auth_session.dart
│   │   │   │   └── phone_verification.dart
│   │   │   └── presentation/
│   │   │       ├── phone_login_page.dart
│   │   │       ├── verification_code_page.dart
│   │   │       └── auth_controller.dart
│   │   ├── chat/
│   │   │   ├── data/
│   │   │   │   ├── chat_api.dart
│   │   │   │   ├── chat_repository_impl.dart
│   │   │   │   └── dto/
│   │   │   ├── domain/
│   │   │   │   ├── chat_repository.dart
│   │   │   │   ├── chat_message.dart
│   │   │   │   ├── chat_content_part.dart
│   │   │   │   └── chat_source.dart
│   │   │   └── presentation/
│   │   │       ├── chat_page.dart
│   │   │       ├── chat_controller.dart
│   │   │       └── widgets/
│   │   ├── call/
│   │   │   ├── data/
│   │   │   │   ├── voice_api.dart
│   │   │   │   ├── voice_socket_client.dart
│   │   │   │   └── call_repository_impl.dart
│   │   │   ├── domain/
│   │   │   │   ├── call_repository.dart
│   │   │   │   ├── call_state.dart
│   │   │   │   ├── audio_frame.dart
│   │   │   │   └── transcript_update.dart
│   │   │   ├── infrastructure/
│   │   │   │   ├── recorder_adapter.dart
│   │   │   │   ├── audio_player_adapter.dart
│   │   │   │   ├── background_audio_handler.dart
│   │   │   │   └── audio_session_manager.dart
│   │   │   └── presentation/
│   │   │       ├── call_page.dart
│   │   │       ├── call_controller.dart
│   │   │       └── widgets/
│   │   ├── onboarding/
│   │   │   ├── data/
│   │   │   ├── domain/
│   │   │   └── presentation/
│   │   ├── persona/
│   │   │   ├── data/
│   │   │   ├── domain/
│   │   │   └── presentation/
│   │   ├── memory/
│   │   │   ├── data/
│   │   │   ├── domain/
│   │   │   └── presentation/
│   │   ├── stickers/
│   │   │   ├── data/
│   │   │   ├── domain/
│   │   │   └── presentation/
│   │   ├── letters/
│   │   │   ├── data/
│   │   │   ├── domain/
│   │   │   └── presentation/
│   │   ├── relationship/
│   │   │   ├── data/
│   │   │   └── domain/
│   │   └── push/
│   │       ├── data/
│   │       │   ├── push_api.dart
│   │       │   └── push_repository_impl.dart
│   │       ├── domain/
│   │       │   ├── push_repository.dart
│   │       │   └── notification_payload.dart
│   │       └── infrastructure/
│   │           ├── push_service.dart
│   │           └── notification_router.dart
│   └── shared/
│       ├── character/
│       │   ├── character_renderer.dart
│       │   ├── static_character_renderer.dart
│       │   ├── character_pose.dart
│       │   └── character_state.dart
│       ├── models/
│       │   ├── paged_result.dart
│       │   └── operation_status.dart
│       ├── widgets/
│       │   ├── async_state_view.dart
│       │   ├── echo_error_view.dart
│       │   ├── echo_loading_view.dart
│       │   ├── confirm_action_sheet.dart
│       │   └── primary_button.dart
│       └── utils/
│           ├── date_formatter.dart
│           └── input_validators.dart
├── test/
│   ├── core/
│   ├── features/
│   ├── fixtures/
│   ├── fakes/
│   └── golden/
├── analysis_options.yaml
├── pubspec.yaml
└── pubspec.lock
```

### 3.1 分层规则

- `presentation` 只负责 Widget、页面状态和用户意图，不直接调用 Dio、WebSocket、录音或安全存储插件。
- `domain` 不依赖 Flutter 和第三方插件，定义实体、repository 接口和状态机。
- `data` 负责 DTO、API 和 repository 实现，snake_case 只存在于 DTO 边界。
- `infrastructure` 封装录音、播放、推送等平台插件；测试通过接口替换为 fake。
- `core` 仅放全局单例和横切能力；不得把业务模型堆入 `core`。
- `shared` 放至少被两个 feature 使用的 UI/纯模型；角色渲染属于跨聊天和电话复用能力。
- feature 之间不直接读取对方 controller；通过 domain 接口、路由参数或明确的 session event 协作。

### 3.2 `CharacterRenderer` 边界

`CharacterRenderer` 接收角色状态（如 `idle`、`listening`、`thinking`、`speaking`、`sitting`）和布局约束，返回可嵌入页面的渲染结果。v2.0 的 `StaticCharacterRenderer` 使用现有 `echo_idle.png`、`idle_sit.png` 及淡入、轻微呼吸、缩放/位移动效。未来 Live2D 实现通过独立 adapter 和 platform channel 接入，不允许 Live2D SDK 类型泄漏到 chat/call feature。

## 4. 后端 API 变更设计

### 4.1 通用约定

- BaseURL 延续小程序环境：开发默认 `http://127.0.0.1:8000`，测试/生产为 `https://api.echoaiforever.cn`，实际值由构建环境注入，不在业务代码硬编码。
- JSON 使用 UTF-8 和 snake_case；时间使用带时区 ISO 8601；有效期字段单位为秒。
- 受保护接口使用 `Authorization: Bearer <access_token>`。
- 客户端发送 `X-Request-ID: <uuid>`；服务端在响应回传同一值，便于问题追踪。
- 新认证接口的错误体引入稳定 `code`；现有业务接口仍兼容 FastAPI 的 `detail` 结构，逐步统一不作为 v2.0 阻断项。
- 认证错误示例：

```json
{
  "code": "AUTH_CODE_INVALID",
  "detail": "验证码错误或已过期",
  "request_id": "4b3f9b2b-2a42-4ff2-b923-23b653ef289d"
}
```

### 4.2 现有认证契约与替换策略

现有 `POST /login` 接收 `{code, client_id}`，通过微信 code 或开发模式 client ID 创建用户，只返回单个 access token。该现状对齐 `Echo-backend/features/auth/interface/router.py`、`schemas.py`、`application/login.py` 和小程序 `utils/session.ts`。

目标状态：APP 仅使用以下手机号接口，不调用 `POST /login`。正式切换时直接停用并移除旧 `/login`；现有小程序数据均为测试数据，不保留旧登录态或账号数据，也不提供旧账号绑定、合并或恢复入口。

### 4.3 `POST /login/phone`：发送短信验证码

鉴权：公开，不携带 Bearer token；旧认证 token 不参与手机号登录或注册，也不能用于指定 `user_id`。

请求：

```json
{
  "phone": "+8613800138000",
  "device_id": "76e8584a-1c97-43eb-a560-555eaabeaca9",
  "purpose": "login"
}
```

字段规则：

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `phone` | 是 | 服务端归一化为 E.164；首期支持中国大陆 `+86` 手机号，展示时脱敏 |
| `device_id` | 是 | 安装级 UUID；重装可变化，不作为用户身份 |
| `purpose` | 是 | v2.0 仅允许 `login`；保留枚举结构供未来注销或其他认证场景扩展 |

成功响应：HTTP 202。

```json
{
  "request_id": "sms_01JX7Y4J5H8N2D7F2P4P3F5E6A",
  "expires_in": 300,
  "resend_after": 60,
  "phone_masked": "+86 138****8000"
}
```

安全与限流：验证码 6 位、5 分钟有效、同一 challenge 最多失败 5 次；同手机号 60 秒内不能重发，并按手机号、IP、device ID 和全局维度限流。无论手机号是否已注册都返回相同结构，避免枚举账号。生产环境不得在响应或日志中返回验证码。

错误：

| HTTP | `code` | 含义 | 客户端行为 |
| --- | --- | --- | --- |
| 400 | `AUTH_PHONE_INVALID` | 手机号格式或地区不支持 | 聚焦手机号输入框 |
| 429 | `AUTH_SMS_RATE_LIMITED` | 触发发送频率限制 | 使用 `Retry-After` 倒计时 |
| 503 | `AUTH_SMS_PROVIDER_UNAVAILABLE` | 阿里云/腾讯云 SMS 暂不可用 | 保留手机号，允许稍后重试 |
| 422 | `REQUEST_VALIDATION_FAILED` | JSON 字段不合法 | 显示通用输入错误并记录 request ID |

### 4.4 `POST /login/verify`：验证并兑换 token

鉴权：公开；身份由短信 challenge 中的已验证手机号决定，客户端不能提交 `user_id`。手机号已注册时直接登录并返回该账号，不视为冲突或错误；手机号未注册时创建新账号。

请求：

```json
{
  "request_id": "sms_01JX7Y4J5H8N2D7F2P4P3F5E6A",
  "phone": "+8613800138000",
  "code": "482731",
  "device_id": "76e8584a-1c97-43eb-a560-555eaabeaca9"
}
```

成功响应：HTTP 200。

```json
{
  "user_id": "phone_90d4f9f4d31d87fb13d112ab",
  "access_token": "<jwt>",
  "refresh_token": "<opaque-random-token>",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_expires_in": 2592000,
  "is_new_user": true
}
```

约定：access token 为标准三段 JWT，建议 15 分钟有效；refresh token 为至少 256 bit 熵的不透明随机串，建议 30 天有效。客户端只依赖响应中的有效期，不硬编码时长。新用户在一个事务中创建 `users`、默认 Persona/关系状态及 token；已有手机号返回原 `user_id`。

错误：

| HTTP | `code` | 含义 | 客户端行为 |
| --- | --- | --- | --- |
| 400 | `AUTH_CHALLENGE_INVALID` | `request_id` 与手机号/device 不匹配 | 返回手机号页重新发送 |
| 400 | `AUTH_CODE_INVALID` | 验证码错误 | 显示剩余重试提示，不清空手机号 |
| 410 | `AUTH_CODE_EXPIRED` | challenge 已过期或已使用 | 返回发送页重新获取 |
| 423 | `AUTH_CODE_ATTEMPTS_EXCEEDED` | 错误次数达到上限 | challenge 作废，重新发送 |
| 429 | `AUTH_VERIFY_RATE_LIMITED` | 验证请求过频 | 按 `Retry-After` 等待 |
| 503 | `AUTH_SERVICE_UNAVAILABLE` | 数据库或认证服务不可用 | 不重复快速提交 |
| 422 | `REQUEST_VALIDATION_FAILED` | 字段格式不合法 | 显示通用校验错误 |

### 4.5 `POST /login/refresh`：刷新并轮换 token

鉴权：不要求 access token；以 refresh token、device ID 和服务端 token 记录完成校验。

请求：

```json
{
  "refresh_token": "<opaque-random-token>",
  "device_id": "76e8584a-1c97-43eb-a560-555eaabeaca9"
}
```

成功响应：HTTP 200。每次都轮换 refresh token，旧 token 立即标记为已使用。

```json
{
  "user_id": "phone_90d4f9f4d31d87fb13d112ab",
  "access_token": "<new-jwt>",
  "refresh_token": "<new-opaque-random-token>",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_expires_in": 2592000
}
```

错误：

| HTTP | `code` | 含义 | 客户端行为 |
| --- | --- | --- | --- |
| 401 | `AUTH_REFRESH_INVALID` | token 不存在、签名/随机值错误或 device 不匹配 | 原子清空会话，进入手机号登录 |
| 401 | `AUTH_REFRESH_EXPIRED` | refresh token 过期 | 清空会话并登录 |
| 401 | `AUTH_REFRESH_REUSED` | 已轮换 token 被再次使用 | 撤销同一 token family，强制重新登录 |
| 403 | `AUTH_USER_DISABLED` | 用户状态非 active | 清空会话并展示账号状态 |
| 429 | `AUTH_REFRESH_RATE_LIMITED` | 刷新请求过频 | 短暂等待；不得无限循环 |
| 503 | `AUTH_SERVICE_UNAVAILABLE` | 服务暂不可用 | 保留 refresh token，显示可重试离线态 |

### 4.6 `POST /login/logout`：注销当前设备会话

鉴权：Bearer access token。请求体携带当前 refresh token 和 device ID；服务端撤销对应 token family。成功返回 HTTP 204。若 access token 已过期，客户端可先刷新再注销；若刷新失败，仍需完成本地清理并在下次登录时以 device ID 清理旧 token。

```json
{
  "refresh_token": "<opaque-random-token>",
  "device_id": "76e8584a-1c97-43eb-a560-555eaabeaca9"
}
```

### 4.7 JWT、refresh token 与数据表设计

access JWT 至少包含：

- `sub`：现有 `user_id`，保证所有业务 repository 无需改造。
- `typ`：固定 `access`，禁止把 refresh token 当 Bearer token 使用。
- `iat`、`exp`：签发与过期时间。
- `jti`：token 唯一 ID，便于审计和紧急撤销。
- `iss`、`aud`：固定 Echo 服务端与 APP audience。

签名密钥从部署 secret 注入，支持 `kid` 和密钥轮换。业务依赖仍通过 `get_current_user` 获得 `CurrentUser(user_id)`，因此聊天等 feature 不感知登录方式变化。

数据库变化：

| 表 | 变化/字段 | 说明 |
| --- | --- | --- |
| `users` | `phone TEXT UNIQUE`、`phone_verified_at TIMESTAMPTZ` | 手机号是新体系的唯一登录标识；移除仅服务微信登录的 `openid` 字段，手机号只在必要管理界面脱敏展示 |
| `sms_verification_challenges` | `request_id`、`phone`、`code_hash`、`purpose`、`device_id`、`attempts`、`expires_at`、`consumed_at`、审计时间 | `purpose` 当前仅允许 `login`；验证码只存带服务端 pepper 的 hash；多实例部署不能使用进程内 challenge |
| `auth_refresh_tokens` | `token_id`、`token_hash`、`token_family_id`、`user_id`、`device_id`、`expires_at`、`used_at`、`revoked_at`、`replaced_by`、审计时间 | 只存 refresh token hash；支持轮换、重放检测和单设备退出 |

短信 provider 通过 auth infrastructure adapter 抽象，阿里云/腾讯云 SMS 二选一为主、另一家可作为灾备；provider 错误转换成认证域错误，不把厂商错误或手机号写入客户端日志。

### 4.8 其他后端契约复用

下表均使用 Bearer access token，字段以对应 `interface/schemas.py` 为准。

| 能力 | 复用接口 | 关键请求/响应 | 对齐文件 |
| --- | --- | --- | --- |
| 文本/电话对话 | `POST /chat/send` | `{message, mode: chat\|call}` → `reply/audio_urls/content_parts/sources` | `features/chat/interface/router.py`、`schemas.py` |
| 清除上下文 | `POST /chat/clear` | → `deleted_messages/reset_conversations`，不清长期记忆 | 同上 |
| Persona | `GET/PUT /persona/me`、`POST /persona/me/reset` | 完整偏好模型；更新是完整 PUT | `features/persona/interface/router.py`、`schemas.py` |
| 长期记忆 | `GET /memory/list?status=&limit=`、`DELETE /memory/{id}`、`POST /memory/clear` | 软删除、批量清空 | `features/memory/interface/router.py`、`schemas.py` |
| 关系 | `GET /relationship/me`、`POST /relationship/me/reset` | 阶段、互动次数、活跃天数、亲近许可 | `features/relationship/interface/router.py`、`schemas.py` |
| 整段 ASR | `POST /voice/asr` | multipart 字段 `audio` → `{user_text}` | `features/voice/interface/router.py`、`schemas.py` |
| 流式 ASR | `WS /voice/asr/stream` | 二进制音频 + JSON 控制/结果 | `features/voice/interface/router.py`、`streaming_asr.py` |
| 来信 | `GET /letters`、`POST /letters/{id}/read` | `items/unread_count`、已读更新 | `features/letters/interface/router.py`、`schemas.py` |
| 表情包 | `GET /stickers`、`POST /stickers/upload`、`POST /stickers/{id}/confirm-save`、`DELETE /stickers/{id}` | multipart 字段 `file`；删除成功 204 | `features/stickers/interface/router.py`、`schemas.py` |

## 5. 网络层设计

### 5.1 Dio 客户端

全局只创建受 Riverpod 管理的 Dio 实例，按环境注入 BaseURL。默认配置：

- JSON 请求 `Content-Type: application/json`，响应按 JSON 解析；204 按空响应处理。
- connect timeout 10 秒、send timeout 30 秒、receive timeout 60 秒；`/chat/send` 可单独放宽 receive timeout，具体值以服务端 LLM 超时基线确定。
- 上传根据文件重新创建 multipart stream，不能复用已经消费的流。
- 每次请求附加 `X-Request-ID`、APP 版本、平台和 locale；不附加手机号或设备敏感信息到 URL query。
- 生产日志只记录 method、path、status、耗时、request ID 和错误类别；Authorization、token、短信 code、手机号、消息正文、Persona 文本及音频内容全部脱敏。

### 5.2 拦截器顺序

1. `RequestIdInterceptor`：生成或沿用 request ID。
2. `AuthInterceptor`：对白名单之外的接口注入最新 access token。
3. `SafeLogInterceptor`：记录脱敏后的请求开始/完成信息。
4. `ErrorInterceptor`：解析 FastAPI/认证错误并转换为统一 `AppException`。
5. 401 由 `TokenRefreshCoordinator` 协调刷新，再把最终失败交给 session controller。

白名单至少包含 `/login/phone`、`/login/verify`、`/login/refresh` 和健康检查。WebSocket 不走 Dio，但复用同一 token provider、request ID 和错误模型。

### 5.3 token 自动刷新流程

```text
业务请求
  ├─ access token 未接近过期 → 直接发送
  └─ 已过期/距过期不足安全窗口 → 进入 refresh single-flight
                                      ├─ 成功：原子写入新 token 对，继续请求
                                      └─ 失败：按错误类型保留离线态或清空会话

收到业务 401
  ├─ 本请求已经重试过 → 不再刷新，终止会话
  ├─ 服务端明确为账号禁用 → 终止会话
  └─ 其余鉴权失效 → single-flight 刷新 → 克隆原请求并仅重试 1 次
```

约束：

- 并发请求只能触发一个刷新请求；其他请求等待同一 Future，禁止刷新风暴。
- 新 access/refresh token 必须作为一组原子持久化。写入失败时不得只保留其中一个。
- 每个请求使用内部 `authRetryCount`，最多自动重放一次，`/login/refresh` 自身绝不进入刷新拦截。
- 401 发生在服务端鉴权阶段，因此普通 JSON 请求可在刷新后重放；multipart 必须通过 request factory 重建文件流。
- 网络超时、连接中断和 5xx 不自动重放 `POST /chat/send`，避免生成重复消息。后续若服务端增加 idempotency key，再开放安全重试。
- refresh 返回 `AUTH_REFRESH_INVALID/EXPIRED/REUSED` 时，清空安全存储、Riverpod 用户态、待处理通知路由和内存消息，跳转手机号登录。
- refresh 的 503/网络错误不立刻销毁仍可能有效的 refresh token；进入“暂时离线，可重试”状态。

### 5.4 统一异常模型

统一异常至少包含：`kind`、`http_status`、`server_code`、`detail`、`request_id`、`retry_after`、`is_retryable`。UI 只依赖 `kind/server_code`，不得匹配中文 `detail`。

现有后端没有统一业务 `code`。以下映射来自各 feature router 与 `shared/interface/dependencies.py`；对于旧错误体，客户端按 HTTP status + endpoint 生成稳定的本地错误类型。

| HTTP/网络 | 现有后端含义 | 客户端错误类型 | 默认 UI/处理 | 对齐来源 |
| --- | --- | --- | --- | --- |
| 无响应/断网 | DNS、socket、离线 | `networkUnavailable` | 保留输入，显示网络不可用 | Dio transport |
| connect/send/receive timeout | 请求超时 | `timeout` | 有副作用请求不自动重发 | Dio transport |
| 请求取消 | 页面离开或主动取消 | `cancelled` | 静默，不 toast | Dio cancel token |
| 400 | chat/persona/memory/voice/sticker 参数或格式错误 | `badRequest` | 显示服务端安全 `detail` 或字段提示 | 对应 feature router |
| 401 | header 缺失、格式错误、token 无效/过期 | `unauthorized` | 先单次刷新；失败后登录 | `shared/interface/dependencies.py` |
| 404 | 记忆、来信、表情包等资源不存在 | `notFound` | 刷新列表并提示已不存在 | memory/letters/stickers router |
| 409 | 同用户 chat 请求仍在处理中 | `requestInProgress` | 保留会话，提示稍后重试 | `features/chat/interface/router.py` |
| 413 | 语音上传超过配置上限 | `payloadTooLarge` | 提示缩短录音，不重试 | `features/voice/interface/router.py` |
| 422 | FastAPI/Pydantic 校验失败，`detail` 通常为数组 | `validation` | 解析字段；无法解析则通用提示 | FastAPI 默认行为、各 schemas |
| 429 | 登录/chat/voice 频率或每日限额 | `rateLimited` | 读取 `Retry-After`，禁用倒计时 | auth/chat/voice router |
| 500 | 现有业务内部错误 | `serverError` | 通用提示 + request ID | 各 feature router |
| 503 | 登录配置、表情生成或 readiness 不可用 | `serviceUnavailable` | 可恢复服务不可用态 | auth/stickers/system router |

FastAPI 现有错误体可能是 `{"detail":"..."}` 或校验数组，也可能是非 JSON；Dio mapper 必须容错。认证改造后的 `code` 优先于 status 映射。

### 5.5 生命周期与取消

- 页面 dispose 时取消仅属于该页面且不应继续的 GET 请求。
- chat 发送请求由 chat controller 持有；页面短暂进入后台不取消，退出账号必须取消。
- call 的 HTTP、WS、录音和播放由同一个 call session scope 管理，挂断时一次性释放。
- 网络恢复只触发幂等 GET 刷新，不自动重发 chat、上传、删除、清空或设置更新。

## 6. 语音链路设计

### 6.1 目标体验与状态机

电话页延续小程序的按住说话模式，不在 v2.0 扩展为全双工。状态机：

```text
connecting → idle → recording → recognizing → thinking → speaking → idle
                └──────── cancel/error ───────────────────────────→ idle
任意活动状态 ── hangup/logout/fatal error ──→ ended
```

状态迁移必须串行：录音开始前停止 Echo 播放；进入 `thinking` 前结束录音和 ASR；播放完成/中断后才回到 `idle`。controller 以 session generation ID 丢弃上一个会话迟到的 partial、final 或播放回调。

### 6.2 现有协议事实

现有小程序和后端的实际组合如下：

- 小程序 `call.ts`：`duration=60000`、`sampleRate=16000`、`numberOfChannels=1`、`format=mp3`、`frameSize=4`。
- 小程序 `voice-stream.ts`：连接 `WS /voice/asr/stream`，Bearer 放在握手 header；连接 5 秒未收到 `ready` 即失败；结束后 15 秒未收到 `final` 即失败。
- 后端 `voice/interface/router.py`：连接前校验开关、Bearer 和 voice quota；accept 后打开腾讯 ASR，再发送 `{"type":"ready"}`；二进制帧原样转发上游。
- 后端 `streaming_asr.py`：腾讯上游 `voice_format=8`，按腾讯定义为 MP3；默认 `engine_model_type=16k_zh`，`needvad=1`，`vad_silence_time=800`。
- 整段 `/voice/asr` 只接受 `audio/mpeg`/`audio/mp3`，不接受 WAV/PCM；依据 `features/voice/application/use_cases.py` 的 `SUPPORTED_VOICE_CONTENT_TYPES` 与“仅支持 MP3”错误。
- 后端总音频上限使用 `VOICE_UPLOAD_MAX_BYTES`，默认 10 MiB；小程序打开 WS 前最多缓存 1 MiB 分片。

其中 `voice_format=8` 对应 MP3、`voice_format=1` 对应 PCM，以及 16 kHz PCM 推荐每 200 ms 发送 6,400 字节，另由[腾讯云实时语音识别 WebSocket 官方文档](https://cloud.tencent.com/document/api/1093/48982)交叉确认。

### 6.3 PCM 目标参数与 P0 格式门禁

Flutter 既定方案要求 `record` 采集 PCM，目标参数冻结为：

| 参数 | 目标值 | 说明 |
| --- | --- | --- |
| 编码 | PCM signed 16-bit little-endian（s16le） | 不带 WAV header 的原始帧 |
| 采样率 | 16,000 Hz | 对齐 `16k_zh` 引擎 |
| 位深 | 16 bit | 每样本 2 字节 |
| 声道 | mono | 单声道 |
| 原始码率 | 256,000 bit/s | `16000 × 16 × 1` |
| 发送节奏 | 每 200 ms 一帧 | 每帧 6,400 字节；平台回调不等长时先在客户端重分帧 |
| 单次录音上限 | 60 秒 | 与小程序一致；理论 PCM 约 1.92 MiB，低于默认 10 MiB |

当前后端把二进制帧按 MP3 转发，而 Flutter 目标是 PCM；直接发送会导致识别失败。这不是客户端可忽略的细节，也是仓库现状与“后端语音 100% 不改”约束之间的冲突。

一期 P0 契约门禁必须在 UI 开发前关闭：

1. 用固定语音样本在 Android 真机采集 s16le PCM，验证每帧长度、端序、节奏和时长。
2. 后端测试环境明确上游格式为 PCM（腾讯 `voice_format=1`）并通过相同样本；WS 对外消息路径与 JSON 协议保持不变。
3. `/voice/asr` 降级路径也必须能接收同一录音产物，或提供经过验证的 MP3 编码产物；当前端点只收 MP3，不能假定 PCM 可上传。
4. 将最终编码写入契约测试和部署配置，禁止客户端格式与服务端 `voice_format` 各自硬编码且无版本标识。

要坚持 PCM 采集且保留整段降级，必须批准“语音 provider 编码配置/整段格式适配”这一最小后端兼容改动；它不改变 `/voice/asr/stream` 的业务路径和消息语义，但严格来说超出“只有认证层改造”。在该例外获得确认并通过契约测试之前，语音一期状态只能是 blocked，不能以模拟数据判定完成。不得静默改回 MP3，也不得把 PCM 伪装为 `audio/mpeg`。

### 6.4 WebSocket 对外协议

连接：

```text
wss://<api-host>/voice/asr/stream
Authorization: Bearer <access_token>
X-Request-ID: <uuid>   （目标新增；现状只要求 Authorization）
```

客户端在握手前检查 access token 剩余有效期；接近过期时先走 HTTP refresh。WebSocket 建立后无法替换 header，连接期间 token 到期不主动断线，但新连接必须使用最新 token。

服务端消息：

| 消息 | JSON 示例 | 客户端行为 |
| --- | --- | --- |
| 就绪 | `{"type":"ready"}` | 开始发送实时帧，并冲刷就绪前的有界缓存 |
| 中间结果 | `{"type":"partial","text":"你好"}` | 仅更新临时字幕，不写入聊天、不触发请求 |
| 最终结果 | `{"type":"final","text":"你好，今天怎么样"}` | 冻结转写，进入 `/chat/send mode=call` |
| 业务错误 | `{"type":"error","detail":"Streaming ASR failed"}` | 关闭流并尝试整段 ASR 降级 |

客户端消息：

| 消息 | 格式 | 时机 |
| --- | --- | --- |
| 音频帧 | WebSocket binary | `ready` 后按 200 ms 节奏发送 |
| 正常结束 | `{"event":"stop"}` | 用户松开发送；之后不再发送二进制帧，等待 final |
| 取消 | `{"event":"cancel"}` | 手势取消、挂断或录音失败；不使用已录内容 |

现有关闭码映射：

| Close code | 后端含义 | 客户端策略 |
| --- | --- | --- |
| 1000 | 正常 stop/cancel | 已收到 final 则完成；否则按用户取消或提前关闭区分 |
| 1009 | 总音频超过配置上限 | 提示录音过长；不得自动重连 |
| 1011 | 服务端/上游内部错误 | 尝试整段 ASR；记录 request ID |
| 4401 | Bearer 缺失或无效 | 若尚未发送音频，刷新后新建连接一次；否则走整段降级 |
| 4404 | 流式 ASR 未启用 | 本次会话直接使用整段 ASR，并上报能力降级指标 |
| 4429 | voice quota 超限 | 不做整段 ASR（同一 quota）；展示频率限制 |

对齐文件：`Echo-backend/features/voice/interface/router.py`。现有 WS 错误没有稳定业务 `code`，客户端按 close code 映射。

### 6.5 录音、缓冲与发送

1. 进入 call 页只检查权限和音频能力，不立即打开麦克风。
2. 用户按下按钮后停止当前播放、激活录音 audio session、创建本次本地临时录音 spool，并并行打开 WS。
3. `record` 输出的任意大小 chunk 进入 frame assembler；assembler 按 6,400 字节切出 200 ms PCM 帧，尾帧在 stop 时按实际长度发送，不补伪音频。
4. `ready` 前只缓存最近不超过 2 秒或 64 KiB 的帧；超过则判定流式启动失败并保留完整 spool 供整段降级，避免内存无限增长。
5. 收到 `ready` 后按采集节奏发送，不能把积压帧瞬间高速冲给上游；发送队列达到 1 秒高水位时停止实时流并转整段降级，防止延迟持续扩大。
6. 松开后停止 recorder，等待所有已产生帧入队，再发送 `stop`。连接就绪超时 5 秒；final 超时沿用客户端 15 秒，覆盖后端默认 10 秒 + 2 秒等待。
7. 取消时发 `cancel`、关闭 recorder/WS、删除 spool，不调用 `/chat/send`。

音量 UI 使用 PCM RMS/peak 的抽样值，仅保留瞬时数值，不保存音频。录音 permission denied、永久拒绝、来电/闹钟中断、蓝牙切换、无输入设备均必须产生确定状态迁移。

### 6.6 整段 ASR 降级

以下情况触发整段降级：WS 建立失败、4404、连接异常、final 超时、发送队列过载或服务端 `error`。4401 先按 token 策略处理；4429 与 1009 不重复消耗服务端资源。

降级文件必须与服务端接受格式一致，multipart 字段固定为 `audio`，响应读取 `user_text`。降级成功后仍只调用一次 `/chat/send`。失败后删除临时文件并回到 idle；不会在后台无限重试。

临时文件约束：

- 仅存在 app cache 目录，随机文件名，不进入相册、媒体库或备份。
- 一次 call session 只保留当前 utterance；成功、取消、挂断和 APP 下次启动清理超时文件。
- 日志只记时长、字节数、编码和耗时，不记路径中的用户信息、音频内容或转写全文。

### 6.7 `/chat/send mode=call` 与 TTS

final text 去空白后不能为空；有效文本调用现有 `POST /chat/send`：

```json
{
  "message": "识别后的用户文本",
  "mode": "call"
}
```

响应的 `reply` 用作字幕，`audio_urls` 用作语音。若 reply 有值但 `audio_urls` 为空，显示字幕并提示音频暂不可用，不重复生成 chat 请求。409 表示上一请求仍在处理，429 按 `Retry-After`；401 走统一刷新。

### 6.8 播放缓冲策略

- `just_audio` 与 `audio_service` 共享一个受 call session 管理的 player，不为每段 URL 创建全局 player。
- 保持小程序“当前段播放时准备下一段”的语义：第一段达到播放器可播放状态立即开始；下一段提前进入 playlist/preload，避免全量下载后才播放。
- 目标首段缓冲为约 300–500 ms，实际由 just_audio/平台数据源决定；弱网时以不卡顿优先，不强制固定字节阈值。
- 多段按服务端顺序播放，不并行发声；切段不得重复或跳段。所有 URL 播完才回 idle。
- 按下录音、挂断、退出账号、耳机拔出策略要求停止时，立即停止并清空队列；迟到回调通过 session ID 丢弃。
- URL 下载失败只重试当前 GET 一次（限尚未播放且无用户取消），不重发 `/chat/send`；仍失败时保留 reply 字幕。
- 使用 `audio_session` 申请 spoken-audio 属性：播放时 duck/pause 由平台策略处理；开始录音前释放播放焦点并切换 play-and-record/record 配置。

### 6.9 前后台切换与保活

Android：

- 用户进入并激活 call session 后，由 `audio_service` 启动前台服务；通知栏显示 Echo 通话状态及“结束”动作。
- 按当前 Android SDK/商店政策声明麦克风与媒体播放 foreground service 类型和权限；只能由前台用户动作开始麦克风，不能从后台偷偷启动。
- 通话播放/录音期间允许屏幕熄灭；不再依赖小程序的 `setKeepScreenOn`。是否常亮由页面提供显式选项，默认尊重系统。
- 系统杀进程、用户划掉任务或撤销通知权限后，不承诺恢复未完成的录音；重启只清理资源并回到 idle/login。

iOS（后期开启）：

- 开启 Audio background mode，并配置 AVAudioSession 的录放类别、蓝牙和扬声器策略。
- 仅在用户已开始的 call session 中维持音频；不能把 background mode 当作常驻保活。
- 系统中断、控制中心、耳机/蓝牙路由变化和锁屏分别真机验收。iOS 不保证任意时长后台网络任务，无法维持时安全结束本轮并保留可解释状态。

通用生命周期规则：

| 场景 | 录音 | WS | 播放 | 恢复策略 |
| --- | --- | --- | --- | --- |
| 短暂后台，活动 call 且平台允许 | 继续/按平台中断回调处理 | 继续 | 继续 | 回前台刷新状态 UI |
| 非 call 页面后台 | 不允许 | 关闭 | 普通短音频停止 | 无需恢复 |
| 来电/闹钟/其他 App 抢占 | pause/stop 当前 utterance | 视中断时长关闭 | pause | 不自动发送半段语音；提示重说 |
| 网络切换 | 继续写本地 spool | 失败即关闭 | 缓冲可继续 | 整段 ASR 或字幕降级 |
| 挂断/退出账号 | 立即停止 | cancel/close | stop | 释放 service、音频焦点和临时文件 |

### 6.10 异常恢复矩阵

| 异常 | 恢复 | 禁止行为 |
| --- | --- | --- |
| 麦克风未授权 | 解释用途并允许去设置 | 循环弹权限框 |
| recorder 启动失败 | 回 idle，释放 audio session | 仍发送空 `stop` |
| WS ready 超时 | 整段降级 | 无界缓存帧 |
| partial 乱序/迟到 | session ID 丢弃旧消息 | 把 partial 当 final 发 chat |
| final 为空 | 尝试整段降级；仍空则提示重说 | 发送空 chat message |
| token 在握手前过期 | 刷新后连接一次 | WS 内无限重连 |
| WS 中途断开 | 使用完整 spool 做整段 ASR | 从中间帧建立新 ASR 会话并假装连续 |
| 播放 URL 部分失败 | 显示 reply，跳出 speaking | 重发 chat 生成重复回复 |
| App 被系统终止 | 下次启动清理 orphan 临时文件 | 恢复/上传未经用户确认的旧录音 |

### 6.11 语音可观测指标

仅记录非内容指标：权限结果、录音时长/字节数、WS ready 耗时、首个 partial 耗时、final 耗时、帧队列高水位、fallback 原因、ASR 成功率、chat 耗时、首音频播放耗时、播放中断原因、后台服务状态。request ID 串联 WS、ASR 和 chat；不得上报原音频、手机号、token、消息全文或完整转写。

## 7. 推送设计

### 7.1 通道与阶段

- Android 首期使用 FCM；FCM 不可达的国内设备在 v2.0 显示能力降级，不伪造“已开启”。
- iOS 使用 APNs，Flutter 侧由 `firebase_messaging` 获取/刷新 APNs/FCM token 并统一消息回调；服务端 provider 层保留直接 APNs 与 FCM 的清晰边界。
- 后期评估个推或极光聚合华为、小米、OPPO、vivo 等厂商通道；业务 payload 不绑定具体厂商。

### 7.2 权限与初始化

- Android/iOS 都在用户看到通知价值说明后再申请权限，不在首次冷启动立即弹系统框。
- Android 按目标 SDK 处理通知运行时权限；iOS 请求 alert、badge、sound，临界/时效通知不在 v2.0 申请。
- 初始化顺序：Firebase core → 注册 background handler → 恢复登录态 → 获取 token → 登录成功后上报。
- 权限拒绝不阻塞聊天和电话；设置页展示状态并可跳系统设置。

### 7.3 token 上报契约

新增 `push_tokens` 表建议字段：`id`、`user_id`、`device_id`、`platform`、`provider`、`token`、`app_version`、`environment`、`locale`、`is_active`、`last_seen_at`、`created_at`、`updated_at`；以 `provider + token + environment` 唯一，token 需要受控访问和日志脱敏。

登录成功、token 刷新、APP 版本变化或 token rotation 时调用：

```text
PUT /push/tokens/me
Authorization: Bearer <access_token>
```

```json
{
  "device_id": "76e8584a-1c97-43eb-a560-555eaabeaca9",
  "platform": "android",
  "provider": "fcm",
  "token": "<provider-token>",
  "app_version": "2.0.0",
  "environment": "production",
  "locale": "zh-CN"
}
```

成功返回 HTTP 200 及 `registered_at`。退出账号调用 `DELETE /push/tokens/me/{device_id}`；服务端发送遇到 invalid/unregistered token 时将记录置为 inactive。一个用户可有多个设备，一个 token 在用户切换时必须重新归属，不能把前一账号通知发给后一账号。

### 7.4 payload 与点击路由

数据 payload 使用版本化、白名单路由，不接受服务端下发任意 URL：

```json
{
  "schema_version": "1",
  "type": "letter_ready",
  "route": "letters",
  "entity_id": "letter_01J...",
  "notification_id": "notice_01J..."
}
```

首期允许路由：`chat`、`letters`、`persona`。`entity_id` 只作为页面定位提示，页面仍通过鉴权 API 获取真实数据。

处理顺序：

- 前台收到：更新 Riverpod badge；是否显示本地横幅由通知类型决定，不强制系统通知。
- 后台点击：解析并校验 payload，恢复 session 后导航。
- 冷启动点击：先暂存 pending route，完成 secure session 恢复与必要 token refresh，再导航。
- 未登录点击：保存非敏感 route intent，登录成功后继续；若 payload 过期或路由不在白名单，进入 chat 首页。
- 重复点击：以 `notification_id` 去重；路由栈不得重复叠加同一详情页。

### 7.5 隐私与发送规则

锁屏通知默认不包含敏感聊天正文、Persona、记忆或转写；只使用“Echo 有一封新来信”等通用文案。服务端记录发送状态、provider message ID 和错误类别，不记录 provider 凭证或完整 token。营销/召回通知必须有独立用户开关与退订规则。

## 8. 页面与功能迁移清单

### 8.1 页面迁移表

| 页面/功能 | 小程序现状 | Flutter 实现要点 | 批次 |
| --- | --- | --- | --- |
| 认证（新增） | `session.ts` 调 `wx.login`，本地保存 user/access token，无独立登录页 | 手机号页、验证码页、倒计时、自动填充/粘贴、JWT 恢复、refresh single-flight、安全退出；与个性化 onboarding 分开 | 一期 |
| `chat` | 初始化 session + Persona；未 onboarding 重定向；内存消息、typing、来源、表情、未读来信、清上下文；角色区与聊天区可展开 | Riverpod chat controller；列表稳定滚动；2000 字限制；来源用外链；渲染 sticker；防重复发送；401 刷新；工具入口；保留当前会话内存语义 | 一期 |
| `call` | 按住录 MP3；WS partial/final；失败上传整段；`mode=call`；顺序播放 TTS；计时、字幕、挂断、常亮 | PCM/协议门禁、record adapter、WS 状态机、spool/fallback、just_audio playlist、audio_service、音频焦点、权限/中断、后台通知栏；静态角色 speaking/listening 动效 | 一期 |
| `onboarding` | 首次读取 Persona；称呼必填；表达风格、陪伴偏好、关系节奏、关于用户；PUT Persona 后进 chat | 作为手机号认证后的独立个性化流程；字段及默认值完全对齐；保存中防重复；公开发布前完成；返回用户不重复出现 | 二期 |
| `persona` | 启用开关、称呼、风格/长度/支持/主动/关系/亲近、最多 5 个避开话题、关于用户；重置 Persona/关系 | 表单状态与服务端 snapshot 分离；离开未保存提示；完整 PUT；40/300 字与 5 项规则；危险操作二次确认；401 统一处理 | 二期 |
| `memory` | active/deleted tab；最多 100；类型/重要度/置信度/更新时间；单删、清空 | 下拉刷新、空/错/加载态；软删除后刷新；清空只允许 active 且非空；确认文案明确不删聊天 | 二期 |
| `stickers` | 列表、单图选择上传、confirm-save、仅用户表情可删 | `image_picker` + multipart；上传/确认作为一个可恢复 UI 流程；格式/尺寸错误；缓存图片；删除 204；权限和大图内存控制 | 二期 |
| `letters` | 列表、未读数、打开即标记已读、overlay 展示全文 | 列表与详情路由/弹层；乐观或成功后已读；通知点击定位；失败可重试；chat badge 同步 provider | 二期 |
| `character` | `idle/sit` 静态图片切换 | `CharacterRenderer` + `StaticCharacterRenderer`；idle/sit/listening/thinking/speaking 轻动效；Live2D 不进入 v2.0 | 一期打底，二期复用 |

### 8.2 chat 细节保持

- 首次进入按 preferred name 生成本地问候；问候不是服务端消息，不写入后端。
- 发送后立即插入 user 消息和 Echo typing 占位；成功用 `reply`、第一个 sticker part 和全部 sources 替换。
- 消息仍只保证当前页面/session 内可见。APP 被杀后不承诺恢复，因为现有 API 没有历史拉取；避免客户端显示与服务端上下文不一致的伪历史。
- 清除上下文调用 `/chat/clear`，成功后清当前内存消息并显示重新开始问候；长期记忆不受影响。
- URL 来源允许系统浏览器打开，并提供复制操作作为补充；仅允许 `http/https` scheme。

### 8.3 一期与二期边界

一期包含工程骨架、手机号认证、session 恢复、chat、call、角色抽象和 Android 后台音频。由于个性化 onboarding 被确认放在二期，一期只供已有/fixture 中 `onboarding_completed=true` 的内部账号验收，不对新用户公开发布，也不通过生产代码绕过后端 onboarding 状态。

二期完成剩余五页、通知和首发收口后，才开放新手机号用户。登录后的路由规则为：

```text
无 session → phone login
有 session、Persona onboarding_completed=false → onboarding
有 session、onboarding_completed=true → chat
通知带合法 pending route → 完成上述守卫后进入目标页
```

## 9. 本地数据模型

### 9.1 存储分级

| 数据 | 存储 | 生命周期 | 说明 |
| --- | --- | --- | --- |
| access token | `flutter_secure_storage` + 运行时内存 | 到期/刷新/退出 | 启动恢复；日志永不输出 |
| refresh token | `flutter_secure_storage` | 轮换、过期、撤销或退出 | 与 access token 作为一组提交 |
| user ID | secure storage | 会话生命周期 | 仅用于本地 session snapshot，不作为接口请求身份参数 |
| device/install ID | secure storage | 安装生命周期 | 推送和 token 设备绑定；不用于广告追踪 |
| token expiry、schema version | secure storage | 随 token 更新 | 用于主动刷新和存储迁移 |
| 环境、主题、locale、通知说明是否展示 | `shared_preferences` | 可丢失 | 非敏感偏好 |
| Persona/relationship | Riverpod 内存，可选短 TTL 内存缓存 | 当前进程 | 含用户文本，不落 shared preferences |
| 当前 chat messages | Riverpod 内存 | 当前登录进程/session | 默认不落盘；退出、清上下文或进程结束清除 |
| 输入草稿 | 内存；如后续落盘需单独隐私评审 | 页面/session | v2.0 默认不持久化 |
| call partial/final、Echo caption | 内存 | 当前 utterance/call | 不持久化 |
| 原始录音 spool | cache 临时文件 | 当前 utterance | 成功/失败/取消/启动清理 |
| 图片/音频网络缓存 | 插件 cache | 系统/容量策略 | 不作为业务数据真源，可随时清理 |
| pending notification route | 非敏感最小结构，可放 preferences | 消费或过期 | 不保存通知正文；设置 TTL |

### 9.2 会话快照

会话快照至少包含 `user_id`、access expiry、refresh expiry、token family/device 关联的本地版本和登录时间。token 字符串由 secure store 单独读写，不允许整个 session JSON 被意外打印。

启动恢复：读取 → 校验字段/schema → access 可用则 authenticated → access 过期但 refresh 可用则单次刷新 → refresh 过期/记录损坏则原子清理并进入登录。系统时间明显回拨时以服务端 401/响应 Date 为准，不延长 token。

### 9.3 数据清理

- 退出账号：先尽力注销服务端 refresh/push token，再清本地；服务端失败也不能阻止本地退出。
- refresh 重放/无效：清 token、用户缓存、消息、pending route、音频队列和临时文件。
- 切换账号：清除前一用户全部内存 provider；网络图片公共缓存可保留，但不得保留带鉴权私有响应。
- APP 启动：按 cache 文件命名和最大保留时间清理 orphan 录音，目标是不恢复旧录音。
- storage schema 变更：迁移失败时安全退出，不尝试使用结构不明的 token。

## 10. 测试策略

### 10.1 测试金字塔

单元测试覆盖：

- 认证手机号归一化、验证码状态、session 恢复、token 原子轮换、并发 401 single-flight、refresh 重放分支。
- Dio 错误体解析：字符串 detail、数组 detail、空响应、非 JSON、各 HTTP status、`Retry-After`。
- chat controller 的 optimistic message、typing 替换、409/429/401、来源/sticker 映射、清上下文。
- call 状态机全部合法/非法迁移、session ID 防迟到回调、frame assembler 的 6,400 字节切帧、尾帧、队列高水位和 fallback 决策。
- Persona 表单枚举、字数、避开话题数量和完整 PUT；memory/letters/stickers repository 映射。
- 通知 payload schema、路由白名单、去重和未登录 pending route。
- secure/shared storage schema 迁移与登出清理。

Widget 测试覆盖：

- 每页 loading/empty/error/content/disabled 状态。
- 登录倒计时、验证码错误、键盘和无障碍 label。
- chat 长消息、typing、sticker、来源、多种屏宽与滚动。
- call 六状态、按住/松开/取消、权限拒绝、字幕溢出和后台恢复。
- Persona 危险操作确认、memory 删除/清空、letters 详情、stickers 上传态。
- 关键页面做 light/dark（若首期提供）和字体缩放 golden；至少覆盖小屏 Android 与主流宽屏。

集成/契约测试覆盖：

- 以真实 FastAPI 测试实例验证所有 DTO 与 snake_case，不用手工 mock 掩盖契约漂移。
- 新 auth 四接口、已注册手机号直接登录/新手机号注册、refresh rotation/reuse、短信 challenge 持久化和 `users.phone` 唯一约束。
- 现有 chat/persona/memory/relationship/letters/stickers/voice 响应 fixture 从对应 Pydantic schema 生成或校验。
- Android 真机完成登录 → chat → call → 后台/锁屏 → 播放 → 挂断。
- FCM 前台、后台、terminated 点击；登录守卫与重复点击。
- iOS 开启后重复 APNs、AudioSession、中断和 TestFlight 流程。

### 10.2 语音链路可测性

必须通过接口隔离四个外部组件：`RecorderAdapter`、`VoiceSocketClient`、`VoiceUploadClient`、`AudioPlayerAdapter`。测试 fake 可以按时间发出帧、partial/final、close code、播放器状态和生命周期中断。

协议测试样本包括：

- 200 ms、1 秒、60 秒 PCM 的字节数和端序。
- chunk 边界分别为小于、等于、大于 6,400 字节，确保重分帧不丢字节。
- ready 前 0/1/2 秒缓存、ready 超时、发送背压、stop 后迟到帧。
- partial 修正、空 partial、多段 partial、final、error、无 final 正常 close。
- 4401/4404/4429、1009、1011、网络切换和 token 刷新。
- WS 失败后整段 ASR 成功/失败；验证 `/chat/send` 最多一次。
- 多段音频预加载、首段失败、中段失败、用户打断、音频焦点丢失。
- 连续 20 轮按住说话及 10 分钟 call session 的资源泄漏检查（每轮录音仍不超过 60 秒）。

固定中文语音 golden 样本必须包含静音、短句、普通长句、噪声、弱网重传条件。样本不得来自真实用户；测试仓库中的授权样本需记录来源。

### 10.3 质量门禁

- `flutter analyze` 零 error；warning 需清零或在评审中明确豁免。
- 单元/Widget/契约测试全通过；关键 domain 与 core 分支覆盖率目标不低于 80%，不得用无意义测试追求总行覆盖率。
- Android 至少覆盖一个接近最低支持版本的真机、一个当前主流版本真机和一个国内厂商设备；语音不能只在模拟器验收。
- 不在日志、崩溃上报、截图或通知中泄露 token、手机号、验证码、聊天正文和音频。
- release 构建、签名、混淆/符号文件、Firebase 环境隔离和后端 production BaseURL 经独立检查。

## 11. 验收标准

### 11.1 一期：工程骨架 + 认证 + chat + call

功能验收：

- [ ] `app/` Flutter 工程可在约定 Flutter stable 上完成 Android debug/release 构建；环境切换不改源码。
- [ ] feature-first、Riverpod、go_router、Dio、secure storage 和统一错误模型落地，页面不直接依赖插件实现。
- [ ] 手机号发送、验证码验证、已注册手机号直接登录、新手机号注册、session 恢复、主动刷新、并发 401、refresh 轮换/重放和退出流程通过。
- [ ] chat 支持发送、typing、reply、sticker、sources、409、429、清上下文和来电入口；同一用户动作不会产生重复 `/chat/send`。
- [ ] call 完成权限、按住/松开/取消、partial/final、整段降级、`mode=call`、字幕、TTS 多段播放、用户打断和挂断资源释放。
- [ ] PCM 与后端 ASR 编码门禁已经通过，不存在 PCM 以 MP3 配置转发的情况。
- [ ] Android 活动 call 在后台/锁屏下按设计继续；通知栏可见且“结束”有效；系统不允许时能安全降级。
- [ ] 角色使用静态图和轻动效，chat/call 只依赖 `CharacterRenderer`，无 Live2D SDK。

质量验收：

- [ ] analyzer、单元、Widget、后端契约和 Android 集成测试全部通过。
- [ ] 在基准测试网络和指定真机上：WS `ready` P95 ≤ 5 秒；用户停止后 final P95 ≤ 15 秒；指标与当前客户端超时一致。
- [ ] 连续 20 轮通话无崩溃、无多播放器叠音、无 orphan 前台服务、无明显 recorder/WS 资源增长。
- [ ] 断网、401、4404、4429、1009、1011、权限永久拒绝和音频中断均有可理解 UI。
- [ ] release 日志抽检没有 token、手机号、验证码、消息正文、转写全文或音频路径泄露。
- [ ] 一期仅内部验收账号使用；未完成 onboarding 的新账号不会通过生产逻辑被绕过。

一期产出物：可安装 Android 内测包、锁定的 API/WS 契约测试、认证数据库 migration、语音真机报告、一期测试报告和已知问题清单。

### 11.2 二期：其余五页 + 推送 + Android 首发收口

功能验收：

- [ ] onboarding 完整迁移；新手机号用户完成个性化后进入 chat，返回用户不重复引导。
- [ ] Persona 全字段、边界校验、恢复默认和关系重置与小程序一致。
- [ ] memory active/deleted、刷新、单删和清空可用，危险操作文案准确。
- [ ] stickers 列表、单图上传、confirm-save、缓存和用户表情删除可用。
- [ ] letters 列表、未读 badge、详情和已读状态可用。
- [ ] Android FCM token 注册/轮换/退出注销可用；前台、后台、冷启动点击均通过路由守卫。
- [ ] `push_tokens` 多设备、换账号和 invalid token 失活行为通过后端测试。
- [ ] 七页面均有 loading/empty/error/offline/401 处理，返回栈与系统 back 行为一致。

质量验收：

- [ ] 七页面 Widget/golden/集成回归通过；至少完成一轮无障碍、字体放大和小屏适配检查。
- [ ] 生产 Firebase 与测试环境隔离，通知正文符合隐私规则。
- [ ] Android release 包完成签名、目标 SDK/权限/前台服务政策、隐私政策和商店素材检查。
- [ ] 崩溃率、ANR、登录成功率、chat 成功率、voice fallback 率和推送 token 上报率具备发布看板。
- [ ] 无 P0/P1 缺陷；P2 有明确规避方案与修复版本。

二期产出物：Android 发布候选包、完整七页面、FCM/APNs 服务端基础设施（iOS 开关可关闭）、发布检查单、监控看板和回滚方案。

### 11.3 iOS 开启阶段

- [ ] Dart 单元/Widget 测试无需分叉即可通过，平台差异集中在 adapter。
- [ ] bundle ID、签名、Keychain、APNs、Background Modes、麦克风/通知隐私说明配置完成。
- [ ] iOS 真机验证录音 PCM 参数、WebSocket header、AudioSession 中断、蓝牙/耳机、锁屏播放和后台限制。
- [ ] APNs 前台/后台/terminated、token rotation 和通知路由通过。
- [ ] TestFlight、隐私清单、审核说明和账号体验路径完成。

## 12. 迁移顺序与里程碑

### 12.1 总体顺序

严格按“契约 → 基础设施 → 垂直功能 → 发布”的顺序推进：

```text
M0 契约冻结/风险 spike
  → M1 Flutter 骨架与认证
    → M2 chat 垂直闭环
      → M3 call/语音/Android 后台闭环（一期完成）
        → M4 onboarding/persona/memory
          → M5 stickers/letters/push/Android 发布（二期完成）
            → M6 iOS 平台开启
              → M7 Live2D/国内推送等后续能力
```

### 12.2 M0：契约冻结与风险消除

任务：

- 为现有 HTTP schemas、错误 status/detail、WS 消息与 close code 建立 fixture/契约清单。
- 完成 PCM 16k/s16le/mono 真机采集 spike，关闭 `voice_format=8` 与 PCM 冲突；确定整段 fallback 编码。
- 冻结手机号 challenge、JWT claims、refresh rotation、`users.phone` 唯一约束和数据库 schema migration。
- 确定 Android application ID、环境名、最低支持系统、Firebase 项目与 CI secret 管理。
- 形成隐私数据分级、日志脱敏和指标字段清单。

产出：签字确认的契约、语音样本报告、数据库变更方案、风险登记表。PCM 门禁未关闭不得进入 M3，认证契约和手机号唯一约束未冻结不得进入 M1。

### 12.3 M1：Flutter 骨架与认证

任务：

- 初始化 `app/` Flutter 工程、feature-first 目录、Riverpod、路由、主题、环境和 CI。
- 完成 Dio、错误模型、secure storage、session controller、refresh coordinator 和脱敏日志。
- 完成手机号/验证码 UI 和 auth repository。
- 后端完成短信 provider、challenge、JWT、refresh token、`users.phone` 唯一约束与 `openid` 字段移除。
- 建立启动路由守卫及内部 fixture 账号通路。

产出：可安装 Android 骨架包、认证闭环、auth 契约测试与 migration。

### 12.4 M2：chat 垂直闭环

任务：

- 迁移 chat 模型、repository、controller 和 UI。
- 对齐 `reply/audio_urls/content_parts/sources`；实现 sticker/source、typing、错误和清上下文。
- 接入静态 `CharacterRenderer` 与聊天展开状态。
- 完成并发发送防护、401 重放一次、取消与列表滚动测试。

产出：Android 文本聊天内测版本、chat 契约/Widget/集成测试。

### 12.5 M3：call 与语音闭环（一期出口）

任务：

- 实现 recorder/socket/upload/player/audio-session adapter 和 call 状态机。
- 完成 PCM 分帧、ready 缓冲、背压、partial/final、stop/cancel、fallback 和临时文件清理。
- 完成 `mode=call`、TTS 顺序预加载、字幕、用户打断、音频焦点。
- 完成 Android `audio_service` 前台服务、通知栏结束、锁屏/后台/系统中断。
- 跑完真机矩阵、弱网、资源泄漏和日志隐私测试。

产出：一期 Android 内测包、语音协议测试、后台音频验收报告。该里程碑不等于公开首发。

### 12.6 M4：onboarding、Persona、memory

任务：

- 实现新用户路由守卫和 onboarding 完整表单。
- 迁移 Persona 所有枚举、输入限制、恢复默认与关系重置。
- 迁移 memory tab、列表、格式化、软删除和清空。
- 补齐跨页面缓存失效：Persona 更新后 chat 称呼刷新；关系重置后相关状态刷新。

产出：新用户可用的个性化闭环、三 feature 测试与迁移对照表。

### 12.7 M5：stickers、letters、push 与 Android 发布（二期出口）

任务：

- 迁移 stickers 选择、multipart、confirm-save、图片缓存和删除。
- 迁移 letters 列表/详情/已读，联动 chat 未读 badge。
- 完成 FCM、`push_tokens`、token rotation、通知 payload、点击路由和隐私文案。
- 完成全量回归、发布监控、商店合规、灰度和回滚预案。

产出：Android release candidate、二期验收报告、发布/回滚 runbook。

### 12.8 M6：iOS 平台开启

任务：

- 配置签名、bundle、Keychain、APNs、Background Modes 和 Firebase iOS。
- 验证 record/PCM、WebSocket、just_audio/audio_service、AudioSession 和通知生命周期。
- 处理 iOS 权限说明、路由恢复、safe area、键盘和系统返回差异。
- 完成 TestFlight 灰度、审核材料和 iOS 发布监控。

产出：iOS release candidate、平台差异说明、TestFlight/商店验收报告。

### 12.9 后续能力池（不进入 v2.0）

- 官方 Live2D SDK 通过原生桥接实现新的 `CharacterRenderer`。
- 个推/极光聚合国内 Android 厂商通道。
- 服务端幂等 key 后开放 chat 安全重试。
- 历史会话查询与经用户同意的加密本地消息缓存。
- 全双工语音、打断检测和更细粒度音频流协议版本化。

### 12.10 风险登记与阻断条件

| 风险 | 影响 | 处理/门禁 |
| --- | --- | --- |
| Flutter PCM 与后端固定 MP3 上游格式冲突 | 流式及整段 ASR 无法工作 | M0 必须批准最小 provider/格式兼容例外并用真机样本锁定；未关闭则 M3 blocked |
| 当前错误无统一业务 code | UI 可能依赖文案 | 旧接口按 status+endpoint 映射；新 auth 先引入稳定 code；契约测试保护 |
| 国内 Android FCM 不可达 | 推送覆盖不足 | v2.0 明示能力；二阶段评估个推/极光，不阻塞核心聊天 |
| Android/iOS 后台政策变化 | 录音/播放被中断或审核失败 | 每次 target SDK/插件升级做政策和真机复核；只维持用户主动 call |
| chat POST 超时结果不确定 | 盲重试产生重复回复 | v2.0 不自动重试；后续服务端 idempotency key |
| 一期未迁 onboarding | 新用户无法完成首用 | 一期限定内部账号；公开发布以二期 onboarding 完成为门禁 |
| 插件平台差异 | 模拟器正常、真机失败 | adapter 隔离 + Android 多厂商真机 + iOS 后开启独立矩阵 |

---

本计划的实现基线是：业务契约以仓库中的 FastAPI router/schema 为准，客户端行为以 `Web/miniprogram` 参考文件为准；任何与本文“现有协议事实”不一致的实现，必须先更新契约测试和本文，再进入开发。

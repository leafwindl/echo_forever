# Echo 硬件身份识别与 APP 设备接入方案

> 文档版本：v1.0  
> 编写日期：2026-08-20  
> 文档状态：阶段一至阶段二已实现，阶段四后端原型已实现，阶段三待接入  
> 适用范围：Echo APP、Echo Backend、Echo Bread Compact 固件  
> 当前原则：不修改已经稳定的实时语音播放链路，本文件只定义下一阶段方案

## 1. 本次对齐目标

当前 Bread Compact 已经能够稳定完成以下链路：

```text
用户说话
  -> Bread Compact 收音
  -> Echo Backend 实时 ASR
  -> Echo 使用统一人格、记忆和模型生成回复
  -> TTS 流式合成
  -> Bread Compact 播放
```

下一阶段需要解决四件事：

1. 取消 APP 内的语音通话，语音交互统一由硬件承担。
2. 硬件语音对话继续写入数据库，但不出现在 APP 主聊天框。
3. APP 增加“我的 Echo”设备连接和管理入口。
4. 增加声纹识别，让 Echo 判断当前说话者是不是主人。

## 2. 已确定的产品边界

| 项目 | 目标状态 |
| --- | --- |
| APP 文字聊天 | 保留 |
| APP 语音通话 | 取消 |
| Bread Compact 语音交互 | 保留，作为唯一语音入口 |
| 硬件语音消息入库 | 保留 |
| 硬件语音消息显示在主聊天框 | 取消 |
| 硬件语音参与 Echo 上下文 | 保留 |
| 硬件语音提取长期记忆 | 主人身份确认后允许 |
| APP 设备管理 | 新增 |
| APP 内 Wi-Fi 配网 | 分阶段新增 |
| 声纹识别位置 | Echo 服务器，不放在 ESP32 |

## 3. 目标系统职责

### 3.1 Bread Compact

设备负责：

- 唤醒、收音和音频上行。
- 接收服务器返回的 Opus 音频并播放。
- 展示连接、聆听、思考、说话和配网状态。
- 在配对和声纹录入期间展示操作提示。
- 保存 Wi-Fi 信息、设备身份和设备凭证。

设备暂时不负责：

- 本地 ASR。
- 本地 TTS。
- 本地大模型。
- 本地声纹模型。
- 人格和长期记忆存储。

### 3.2 Echo Backend

后端负责：

- 设备注册、绑定、鉴权、状态和解绑。
- ASR、LLM、TTS 和当前流式音频链路。
- 消息来源、展示范围和会话上下文管理。
- 声纹录入、特征提取、比对和置信度判断。
- 根据说话者身份决定可使用的记忆范围。
- 向 APP 提供设备管理 API。

### 3.3 Echo APP

APP 负责：

- 文字聊天。
- 人格、记忆和其他现有功能管理。
- 设备绑定、状态查看、重命名和解绑。
- 发起 Wi-Fi 配网。
- 发起声纹录入、查看录入状态和重新录入。

APP 不再负责：

- 手机麦克风录音。
- APP 内实时 ASR。
- APP 内 TTS 播放。
- APP 内语音通话状态机。

## 4. 取消 APP 语音通话

### 4.1 取消范围

APP 实施时应删除以下用户入口和业务代码：

- 聊天页右上角的电话按钮。
- `/call` 路由和 `RouteNames.call`。
- `app/lib/features/call/` 功能目录。
- `app/test/features/call/` 对应测试。
- APP 启动时清理通话临时音频的逻辑。
- 只为 APP 通话使用的录音、音频服务和临时文件依赖。
- Android 麦克风及麦克风前台服务权限。

依赖清理建议：

| 依赖 | 处理建议 | 原因 |
| --- | --- | --- |
| `record` | 删除 | 只用于 APP 通话录音 |
| `audio_service` | 删除 | 当前只用于 APP 通话播放 |
| `path_provider` | 删除前复查 | 当前搜索结果只用于通话临时文件 |
| `web_socket_channel` | 删除前复查 | APP 通话实际使用 `dart:io WebSocket`，当前依赖可能已无实际引用 |
| `audio_session` | 保留 | 学习专注功能仍在使用 |
| `just_audio` | 保留 | 学习专注功能仍在使用 |
| `permission_handler` | 保留 | 推送通知功能仍在使用 |

### 4.2 后端不能随 APP 一起删除的内容

以下后端能力仍被硬件使用，不能因为 APP 取消通话而删除：

- `features/voice/` 中的 ASR、流式 ASR 和 TTS 能力。
- `features/devices/` 中的设备 WebSocket 音频链路。
- `conversation_mode="call"` 的口语回复约束。
- `voice_asr` 和 `voice_reply` 消息类型。
- TTS Provider、音频编码、VAD 和延迟诊断。

现阶段可将后端的 `call` 理解为“口语交互模式”，而不是“APP 电话页面”。以后可以重命名为 `voice`，但本阶段不为改名扩大改动范围。

### 4.3 历史 APP 语音消息

由于 APP 语音通话将完全取消，建议主聊天框以后只展示明确属于文字聊天的消息。历史上没有来源字段的 `voice_asr` 和 `voice_reply` 也不再展示。

这样可以避免为了区分旧 APP 通话和旧硬件语音进行不可靠的数据猜测。历史消息仍留在数据库中。

## 5. 消息入库但不显示在主聊天框

### 5.1 当前问题

当前硬件调用普通 `call` 流程，保存以下两条消息：

```text
voice_asr    用户说的话
voice_reply  Echo 的回复
```

设备完成一轮对话后，后端还会发布 `chat.sync`，APP 因而立即把这两条消息合并到聊天框。

仅在 Flutter 页面过滤消息不可靠，会产生以下问题：

- 每页请求 10 条，APP 删除 8 条后页面只剩 2 条。
- `has_more` 和分页游标不准确。
- 实时事件仍可能把消息重新放回聊天框。
- 其他客户端可能继续显示这些消息。

因此过滤必须由后端查询和事件层共同保证。

### 5.2 推荐消息契约

建议为 `chat_messages` 增加两个独立概念：

```text
channel       消息来自哪种交互渠道
visibility    消息允许出现在哪种用户界面
```

建议枚举：

| 字段 | 值 | 含义 |
| --- | --- | --- |
| `channel` | `app_chat` | APP 文字聊天 |
| `channel` | `device_voice` | Bread Compact 语音 |
| `channel` | `proactive` | Echo 主动消息 |
| `channel` | `system` | 系统内部消息 |
| `visibility` | `main_chat` | 可展示在主聊天框 |
| `visibility` | `device_history` | 只允许未来的设备记录页使用 |
| `visibility` | `internal` | 不直接向用户展示 |

硬件一轮语音建议保存为：

```text
用户消息：message_type=voice_asr
          channel=device_voice
          visibility=device_history

Echo 回复：message_type=voice_reply
           channel=device_voice
           visibility=device_history
```

APP 文字聊天建议保存为：

```text
channel=app_chat
visibility=main_chat
```

### 5.3 查询和实时事件规则

主聊天历史接口只返回：

```sql
visibility = 'main_chat'
```

设备对话完成后：

- 不再向主聊天流发布包含语音消息的 `chat.sync`。
- 可以发布轻量的 `device.activity` 事件，供设备页刷新状态。
- 不在 APP 主聊天页显示用户语音文本或 Echo 语音回复。

### 5.4 上下文与记忆规则

`visibility` 只控制界面展示，不控制 Echo 是否能够理解这段对话。

推荐规则：

| 场景 | 短期上下文 | 长期记忆提取 |
| --- | --- | --- |
| APP 文字聊天 | 使用 | 使用 |
| 硬件语音，主人已确认 | 使用 | 使用 |
| 硬件语音，身份未知 | 只用于当前临时轮次 | 不写入主人记忆 |
| 系统内部消息 | 按功能决定 | 默认不提取 |

这样 Echo 在 APP 和硬件之间保持同一个人格，并且能够记得主人通过硬件说过的事情，但主聊天界面仍保持干净。

## 6. APP“我的 Echo”设备入口

### 6.1 页面入口

取消聊天页电话按钮后，建议将原位置改为设备按钮：

```text
图标：设备或音箱图标
名称：我的 Echo
路由：/devices
```

聊天页保留快捷入口，菜单中也可以增加“设备管理”。第一版不需要复杂的设备首页。

### 6.2 第一版页面能力

“我的 Echo”第一版建议包括：

- 当前是否已绑定设备。
- 设备名称。
- 在线或离线状态。
- 最后在线时间。
- 固件版本。
- 当前网络名称，只显示 SSID，不显示密码。
- 声纹状态：未录入、录入中、可用、需要重新录入。
- 重新配网。
- 重命名。
- 解绑。

### 6.3 设备数据模型

建议新增 `devices`：

```text
id
device_id
client_id
owner_user_id
display_name
firmware_version
status
last_seen_at
wifi_ssid
bound_at
created_at
updated_at
```

建议新增 `device_credentials`：

```text
id
device_id
credential_hash
status
issued_at
last_used_at
revoked_at
```

数据库只保存设备凭证的哈希，不保存明文凭证。

当前环境变量：

```text
ECHO_DEVICE_USER_MAP_JSON
ECHO_DEVICE_TOKEN
```

可在迁移阶段作为兼容回退，正式完成配对后不再作为主要身份系统。

### 6.4 设备绑定流程

推荐流程：

```text
未绑定设备启动
  -> 设备向 Echo Backend 请求一次性配对码
  -> OLED 显示六位配对码
  -> 用户在 APP“添加设备”中输入配对码
  -> APP 使用当前登录账号认领设备
  -> 后端建立 owner_user_id 绑定
  -> 后端签发该设备独立凭证
  -> 设备保存凭证并重新连接
  -> APP 显示设备在线
```

配对码建议：

- 六位数字。
- 五分钟过期。
- 只能使用一次。
- 连续输错需要限流。
- 解绑后原设备凭证立即失效。

### 6.5 建议 API

APP 登录态接口：

```text
GET    /devices
POST   /devices/pairings/claim
GET    /devices/{device_id}
PATCH  /devices/{device_id}
DELETE /devices/{device_id}
POST   /devices/{device_id}/credentials/rotate
```

设备接口：

```text
POST /devices/pairings
POST /devices/heartbeat
GET  /devices/firmware/config
WS   /devices/ws
```

接口名称可以在实现时按现有项目规范调整，本文件主要确认职责边界。

## 7. APP 内 Wi-Fi 配网

### 7.1 目标流程

```text
APP 点击“为 Echo 配网”
  -> 引导设备进入配网模式
  -> APP 连接设备 Xiaozhi-* SoftAP
  -> APP 调用 192.168.4.1 的本地配置接口
  -> 获取附近 Wi-Fi 列表
  -> 用户选择 Wi-Fi 并输入密码
  -> 配置信息写入设备
  -> 设备重启并连接目标 Wi-Fi
  -> 设备连接 Echo Backend
  -> APP 通过后端确认设备在线
```

### 7.2 固件需要提供的本地接口

建议固件不要让 APP 依赖 HTML 页面结构，而是提供稳定 JSON 接口：

```text
GET  /api/device
GET  /api/wifi/scan
POST /api/wifi/configure
GET  /api/wifi/status
POST /api/device/reboot
```

### 7.3 配网安全要求

- Wi-Fi 密码只发送给局域网内的设备配置接口。
- APP 不保存 Wi-Fi 明文密码。
- 后端不接收和存储 Wi-Fi 密码。
- 固件日志不得打印 Wi-Fi 密码。
- 配网模式应有超时退出机制。
- 最好要求用户按 BOOT 键或进行其他物理操作后才能进入配网模式。

### 7.4 分阶段策略

完整 APP 配网涉及 Android 和 iOS 的本地网络、热点切换和权限差异。建议：

1. 第一版先完成账号绑定、在线状态和解绑。
2. 保留当前 `192.168.4.1` 页面作为故障回退。
3. 第二版再让 APP 接管 Wi-Fi 扫描和配置。

## 8. 声纹识别

### 8.1 第一版目标

第一版只回答一个问题：

```text
当前说话的人是不是设备主人？
```

输出不是单纯的姓名，而是包含：

```text
speaker_profile_id
speaker_role = owner | unknown
confidence
model_version
```

第一版不同时识别多个家庭成员。后续可以扩展 `family_member` 和 `guest`。

### 8.2 为什么放在服务器

Bread Compact 已经将完整 PCM 音频传给后端，服务器可以在不增加设备硬件的情况下完成声纹处理。

建议并行流程：

```text
完整语音 PCM
  -> 实时 ASR 得到文字
  -> 声纹模型提取 embedding

ASR 最终结果 + 声纹判断
  -> 构建 Echo 对话上下文
```

声纹特征提取可以与 ASR 并行，避免串行增加明显等待时间。

### 8.3 声纹录入流程

```text
APP 点击“录入我的声音”
  -> 后端创建 enrollment_session
  -> 机器人收到录入指令
  -> 机器人提示用户朗读指定内容
  -> 采集 3 至 5 段不同句子
  -> 检查时长、音量、噪声和重复度
  -> 提取并聚合声纹 embedding
  -> 保存 speaker profile
  -> APP 显示录入完成
```

建议每段有效语音 3 至 8 秒。只说“嗯”“好的”等极短语音不适合作为可靠录入样本。

### 8.4 声纹数据模型

建议新增 `speaker_profiles`：

```text
id
owner_user_id
device_id
display_name
role
embedding
model_name
model_version
verification_threshold
status
created_at
updated_at
```

建议新增 `speaker_enrollment_samples`：

```text
id
speaker_profile_id
audio_duration_ms
quality_score
embedding
raw_audio_path
delete_after
created_at
```

建议新增 `device_voice_turns`：

```text
id
device_id
user_id
request_id
user_message_id
assistant_message_id
speaker_profile_id
speaker_role
speaker_confidence
verification_status
asr_text
audio_duration_ms
created_at
```

`device_voice_turns` 用于设备诊断、声纹判断和一轮语音追踪，不代替 `chat_messages`。

### 8.5 身份和记忆策略

推荐默认策略：

| 判断结果 | Echo 行为 |
| --- | --- |
| `owner` 且高置信度 | 使用主人称呼、关系状态、短期上下文和长期记忆 |
| `unknown` | 可以正常回答普通问题，但不读取敏感主人记忆 |
| 音频太短或质量差 | 按 `unknown` 处理，不猜测身份 |
| 模型不可用 | 按 `unknown` 降级，语音对话本身仍可继续 |

未知说话者的对话可以入库用于诊断，但默认不写入主人的长期记忆。

### 8.6 安全和隐私

- 声纹只用于个性化，不作为支付、开锁或高风险认证手段。
- 低置信度必须返回 `unknown`。
- 原始录入音频设置短期保留时间，到期删除。
- 长期保存 embedding，不长期保存每次日常对话的原始音频。
- 用户可以在 APP 中删除声纹并重新录入。
- 模型升级后记录模型版本，并支持提示用户重新录入。

## 9. 最终目标链路

```text
Bread Compact 收音
  -> Echo Backend 接收 PCM
  -> 实时 ASR 与声纹识别并行
  -> 确认 owner 或 unknown
  -> 按身份加载允许使用的人格、上下文和记忆
  -> LLM 流式回复
  -> TTS 流式合成
  -> Bread Compact 播放
  -> 写入 chat_messages，channel=device_voice
  -> 写入 device_voice_turns
  -> 不发布到 APP 主聊天框
  -> APP 设备页只更新最后活动时间和设备状态
```

## 10. 实施阶段

### 阶段一：收敛 APP 和消息边界

状态：已于 2026-08-20 完成代码实现和本地验证。

实施内容：

- 备份当前可用版本和数据库。
- 为消息增加 `channel` 和 `visibility`。
- 新产生的硬件语音标记为 `device_voice/device_history`。
- 主聊天历史 SQL 只查询 `main_chat`。
- 硬件语音完成后不再发布主聊天 `chat.sync`。
- 移除 APP 电话按钮、路由、通话模块和专属权限依赖。
- 保持后端硬件语音模式和实时链路不变。

验收标准：

- APP 中不存在语音通话入口。
- APP 首次启动不申请麦克风权限。
- APP 文字聊天正常。
- 机器人语音回复速度和完整度不退化。
- 硬件语音用户消息和回复均成功入库。
- 重启 APP、加载历史、翻页和接收实时事件时，主聊天框都不出现语音消息。
- Echo 在下一轮对话中仍能理解刚才通过硬件说过的内容。

实现结果：

- `chat_messages` 已增加 `channel` 和 `visibility`，旧语音消息会迁移为
  `device_voice/device_history`。
- 主聊天历史在 SQL 分页前只选择 `main_chat`，设备语音不进入历史和 SSE 同步。
- Bread Compact 继续复用后端 `call` 口语模式，实时 ASR、LLM、TTS 和播放协议未改变。
- APP 的电话入口、`/call` 路由、通话功能目录、录音依赖和 Android 麦克风权限已删除。
- 设备绑定、APP 设备页、Wi-Fi 配网和声纹识别仍按后续阶段推进。

### 阶段二：设备绑定和 APP 设备页

状态：已完成后端接口、一次性配对码、设备凭证、心跳、解绑、凭证轮换和 APP“我的 Echo”页面。

实施内容：

- 建立 `devices` 和 `device_credentials`。
- 增加一次性配对码。
- 将环境变量用户映射迁移为数据库绑定。
- APP 增加“我的 Echo”。
- 支持设备状态、重命名和解绑。
- 设备定期上报在线状态和固件版本。

验收标准：

- 新设备可以通过 APP 绑定到当前账号。
- 不修改服务器环境变量也能完成新设备绑定。
- 设备重启后仍能自动鉴权连接。
- APP 能正确显示在线、离线和最后在线时间。
- 解绑后设备无法继续访问原账号。
- 一个设备不能同时绑定到两个账号。

### 阶段三：APP Wi-Fi 配网

状态：未在本轮接入，继续保留 Bread Compact 的 `192.168.4.1` 浏览器配网作为稳定回退。

实施内容：

- 固件提供本地 JSON 配网接口。
- APP 完成热点引导、Wi-Fi 扫描和配置。
- 保留浏览器配网页面作为回退。

验收标准：

- 全新设备不依赖电脑即可完成配网。
- Wi-Fi 密码不进入 Echo Backend 和 APP 持久存储。
- 配网失败有明确重试入口。
- 更换路由器后可以通过 APP 重新配网。
- Android 和 iOS 分别完成真机验证。

### 阶段四：主人声纹识别

状态：后端声纹特征、录入接口、`owner/unknown` 上下文隔离和设备轮次记录已完成；APP/硬件引导式录入界面仍需下一轮接入。

实施内容：

- 建立声纹数据表和服务接口。
- APP 发起录入，机器人完成采样提示和收音。
- ASR 与声纹提取并行。
- 对话上下文加入可信说话者身份。
- 实现 `owner/unknown` 记忆权限策略。

验收标准：

- 主人在安静环境下多轮测试可稳定识别。
- 陌生人不会被高概率识别为主人。
- 短音频、噪声音频和模型异常均降级为 `unknown`。
- 声纹处理不会让当前首句播放延迟出现明显退化。
- `unknown` 无法读取或写入主人的长期私人记忆。
- 删除声纹后立即停止主人识别。

## 11. 风险与回滚

| 风险 | 处理方式 |
| --- | --- |
| 消息过滤造成分页错误 | 在 SQL 查询前过滤，并补充分页测试 |
| 删除 APP 通话误伤硬件 | 只删除 Flutter `features/call`，保留后端 `call` 口语模式 |
| 设备绑定失败导致无法使用 | 迁移期保留环境变量映射回退 |
| APP 配网兼容性不稳定 | 保留 `192.168.4.1` 页面 |
| 声纹误识别 | 阈值保守，低置信度统一 `unknown` |
| 声纹服务异常影响对话 | 身份模块失败时降级，不阻断 ASR、LLM 和 TTS |
| 隐藏语音后 APP 上下文看似跳跃 | 产品上接受跨终端记忆，不在聊天框补插语音文本 |

## 12. 本次需要确认的事项

以下内容确认后再进入代码实施：

1. APP 语音通话功能完全删除，不保留隐藏开关。
2. 主聊天框只展示文字聊天等 `main_chat` 消息，历史 `voice_asr/voice_reply` 也隐藏。
3. 硬件语音虽然不显示，仍参与主人跨 APP、硬件的统一上下文和长期记忆。
4. 未识别为主人的用户可以进行普通问答，但不能读取或写入主人长期记忆。
5. APP 第一版设备页先做绑定、状态和解绑，Wi-Fi 配网在下一阶段接入。
6. 声纹第一版只做“主人或未知”，暂不做多家庭成员识别。
7. 取消电话按钮后，原位置改为“我的 Echo”设备入口。

## 13. 明确不在本阶段处理的内容

- 机器人动作和电机控制。
- 摄像头和视觉识别。
- 室内导航。
- 多设备协同。
- 多家庭成员声纹管理。
- 完全离线 ASR、TTS 和大模型。
- 将后端 `conversation_mode="call"` 全面重命名。

这些能力可以在设备身份、消息通道和配对体系稳定后继续扩展。

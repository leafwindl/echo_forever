# Echo Phone Agent B 阶段记录

> 日期：2026-11-03  
> 设备：PJC110，Android 15（API 35）  
> 状态：B0/B1/B2 完成；B3 完成；截图固定采用 PC/ADB 桥，已打通。

## B0 产品边界

- [x] 独立 App，不塞进现有 Echo 聊天 App
- [x] 包名 `cn.echoaiforever.phone_agent`
- [x] 只用于专用测试手机
- [x] 不 Root
- [x] 无障碍服务由用户手动开启
- [x] 前台服务常驻
- [x] 配对令牌由后端签发
- [x] 截图采用 PC/ADB 桥
- [ ] 高风险操作确认
- [x] 操作审计和紧急停止

## B1 已实现

### App 骨架

- `MainActivity`
  - 显示无障碍服务连接状态
  - 显示系统开关、包名、前台服务状态
  - 打开无障碍设置
  - 启动/停止前台服务
  - 读取当前界面文本
  - 回到桌面
  - 本地配对令牌占位
- `AgentAccessibilityService`
  - 监听无障碍事件
  - 读取当前窗口
  - 遍历 UI 树并输出文本、resource-id、bounds
  - 按文字查找并点击
  - 支持 Home 等全局动作
- `AgentForegroundService`
  - 通知渠道
  - `startForeground`
  - 运行状态标记
- 资源
  - 无障碍服务配置
  - 中文文案

### 构建与安装

```text
Gradle assembleDebug：成功
APK：app-debug.apk
安装：ColorOS 第三方安装保护需要人工确认
```

### 真机验证

- 无障碍服务出现在系统“已下载的应用”
- 开启后系统显示安全提示，选择“保持开启”
- `dumpsys accessibility` 显示：

```text
Bound services:
  Echo Phone Agent 界面控制
Enabled services:
  cn.echoaiforever.phone_agent/...AgentAccessibilityService
Crashed services: {}
```

- App 状态显示“无障碍服务：已连接”
- 点击“启动前台服务”后，系统服务记录显示 `isForeground=true`
- “读取当前界面”和“回到桌面”按钮可用

## 已确认的限制

- ColorOS 开启无障碍时会弹出系统安全提示，必须人工确认；自动化安装/激活不能完全静默。
- Portal 的无障碍服务在同一台手机上曾报告故障；我们的 Echo 服务目前已成功绑定。
- 截图采用 PC ADB 桥，不依赖手机独立屏幕捕获。
- 通知读取、基础多步任务和操作审计已实现。
- 配对令牌保存在本机 SharedPreferences；当前版本是专用测试机骨架，不应作为生产安全实现。
- 当前 App 仅放行本地回环明文 HTTP，用于 adb reverse；其他地址必须 HTTPS。

## B2 基础通道

### 后端

新增 `mobile_agent` feature：

- 配对码生成和一次性消费
- 设备令牌哈希存储
- 设备在线状态
- WebSocket `/mobile-agent/ws`
- HTTP 命令：
  - `POST /mobile-agent/pair`
  - `GET /mobile-agent/devices`
  - `POST /mobile-agent/devices/{id}/command`

命令白名单：

- `observe`
- `launch_app`
- `action`：
  - `tap`
  - `tap_text`
  - `back` / `home` / `recents`
  - `text`

### 手机端

- 可配置后端地址
- 配对码输入和配对
- OkHttp WebSocket 客户端
- 前台服务持有连接
- 收到 command 后调用无障碍服务并回传 result
- 已实现 observe、按文字点击、坐标点击、文本设置、Home/Back/Recents、启动应用

### 本地端到端验证

测试链路：

```text
本地 FastAPI
  <- HTTP 配对
  <- WebSocket 长连接
  -> observe / home / launch_app
```

验证结果：

- App 配对成功，获得设备 ID
- 设备在线状态 `online=true`
- 远程 `observe` 返回当前界面 UI 树
- 远程 `action/home` 成功
- 远程 `launch_app` 启动设置，随后 `observe` 能读到新页面
- 后端全量测试：**531 passed, 8 skipped**
- 架构检查通过

### 生产验证

- 后端已部署到 `https://api.echoaiforever.cn`
- Nginx 增加 `/mobile-agent/ws` WebSocket 代理（与 `/desktop/nodes/ws` 相同的 Upgrade 配置）
- 手机使用生产地址重新配对成功
- 生产设备在线：
  - `name=Echo 测试手机`
  - `online=true`
- 生产远程 `observe` 返回当前界面 UI 树
- 生产远程 `action/home` 成功
- 后端 revision：`fdac59d`（手机端重连提交 `d77db00`）
- WebSocket 断开后前台服务每 5 秒重连一次

### B2 还缺

- 高风险操作确认
- 正式分发前关闭明文 HTTP

## B3 已实现

### 通知读取

- 新增 `AgentNotificationListener`
- 只读取当前通知的包名、标题、文本、时间
- 不点击通知、不读取通知历史
- 生产验证：返回淘宝、抖音、华为健康等当前通知
- 手机端可通过“打开通知读取设置”授权

### 操作审计

- 新增 `mobile_agent_actions` 表
- 每条远程命令记录：
  - action_id
  - device_id / user_id
  - action
  - running/completed/failed/timed_out
  - error_code
  - duration_ms
- 新增 `GET /mobile-agent/audit`
- 生产验证：`observe`、`notifications` 等动作均落入审计

### Agent 工具

后端已注册：

- `phone_status`
- `phone_observe`
- `phone_screenshot`（通过 PC/ADB 桥）
- `phone_launch_app`
- `phone_action`
- `phone_notifications`
- `phone_stop`
- `phone_run_task`（受限多步循环，最多 20 步）

工具通过 `mobile_agent/public.py` 访问稳定 API，不直接依赖 PostgreSQL。

### 解除配对与安全

- 手机端“解除本机配对”清除设备令牌和设备 ID，并尝试调用后端撤销
- 后端新增 `POST /mobile-agent/unpair`（设备令牌自撤销）
- 默认关闭明文 HTTP，仅放行 `127.0.0.1`、`localhost`、`10.0.2.2` 用于本地 adb reverse
- 生产地址继续使用 HTTPS

### 截图方案：PC ADB 桥（已定稿）

用户已确认后续开发固定采用 PC/ADB 截图，不要求手机独立运行。

已尝试并放弃/移除：

1. 无障碍 `takeScreenshot`
   - ColorOS 绑定后能力位不包含截图，调用不可用
2. MediaProjection
   - ColorOS/Android 15 授权后取不到有效帧
   - 不作为产品方案，相关代码已从 APK 主路径移除

因此 `phone_agent` 截图只依赖 PC 桥；手机端不再暴露“授权手机截图”按钮。

### ADB 截图桥（已接入）

在 PC 运行：

```powershell
.venv\Scripts\python.exe scripts/adb_screenshot_bridge.py --serial ce7f6baf
```

桥接服务会：

- 监听 `127.0.0.1:8765`
- 自动执行 `adb reverse tcp:8765 tcp:8765`
- 用 `adb exec-out screencap -p` 截全屏
- 返回 PNG base64

手机端 `screenshot` 请求 `http://127.0.0.1:8765/screenshot`；这是固定截图路径。

生产验证：

```text
observe   -> 200, 1053 chars
screenshot -> 200, image/png, 273140 chars
action/home -> 200
audit     -> 200, 12 items
```

这解决了开发期“手机能操作但没有截图”的问题，但要求手机连接 PC/ADB；
它不是手机独立运行方案。

### App Skill 框架与网易云音乐

新增后端 `features/mobile_agent/application/skills.py`：

- `AppSkill` 协议与 `SkillRunner`
- 统一执行手机 action / observe / wait
- UI 文本解析选择结果
- `NetEaseMusicSkill`
  - 打开 `orpheus://search`
  - 点击搜索框
  - 通过 PC 桥输入中文
  - 提交搜索
  - 选择单曲
  - 播放并验证 `播放暂停`

新增：

- `POST /mobile-agent/skills/netmusic/play`
- Agent 工具 `phone_play_music`
- PC 桥 `/text`、`/key`、`/open_uri`
- Android `open_uri`、`key` action
- 中文输入使用 ADBKeyboard（PC 桥广播，解决 `adb input` 不支持 Unicode）

本地验证：

```json
{
  "skill": "netmusic",
  "query": "晴天",
  "playing": true,
  "package": "com.netease.cloudmusic"
}
```

`playing=true`，网易云进入播放器并显示“晴天 (原唱 周杰伦)”。

### B3 还缺

- 高风险操作二次确认
- 完整多步任务状态推送和用户中断 UI
- 令牌加密存储/Keystore


## 双 APK（本地/生产）

为了避免切换配对时覆盖生产令牌，手机端提供两个独立包：

```text
生产版 cn.echoaiforever.phone_agent
本地版 cn.echoaiforever.phone_agent.local
```

构建：

```powershell
.\gradlew.bat assembleProdDebug assembleLocalDebug
```

两个包可同时安装，配对令牌、默认后端地址互不影响。本地版通过
`adb reverse tcp:8000 tcp:8000` 连接本地后端；生产版继续连接
`https://api.echoaiforever.cn`。截图和中文输入仍共用 PC 的 8765 桥。


## B站 App Skill

新增 `bilibili` 技能：

- `bilibili://search?keyword=...` 直接打开搜索结果
- 选择第一条结果
- 打开播放页
- `play`：确认视频页
- `comments`：切换到评论页

API：

```text
POST /mobile-agent/skills/bilibili/play
POST /mobile-agent/skills/bilibili/comments
```

Agent 工具：

```text
phone_bilibili
```

本地真机验证：

```json
{
  "skill": "bilibili",
  "query": "晴天",
  "playing": true,
  "comments_visible": true
}
```

只读视频和评论，不发评论、不登录账号。


## 抖音 App Skill

新增：

- 手机端 `swipe` 手势
- `snssdk1128://feed`
- `snssdk1128://search?keyword=...`
- `DouyinSkill`
  - `feed`：打开推荐流并连续上滑
  - `search`：搜索视频
  - `play`：打开第一条结果
  - `comments`：打开评论面板并可继续下滑

API：

```text
POST /mobile-agent/skills/douyin/feed
POST /mobile-agent/skills/douyin/search
POST /mobile-agent/skills/douyin/play
POST /mobile-agent/skills/douyin/comments
```

Agent 工具：

```text
phone_douyin
```

本地真机验证：

```json
{
  "feed": {"swiped": 2},
  "search": {"search_visible": true},
  "play": {"playing": true},
  "comments": {"comments_visible": true}
}
```

只做浏览，不发评论、不私信、不购物。


## 小红书 App Skill

新增：

- `XiaohongshuSkill`
- 通过 app 启动器打开小红书
- 搜索框输入中文，选择搜索
- 打开第一条笔记
- 进入评论并下滑评论
- 手机端新增 `launch_app` 的 PC 桥兜底

API：

```text
POST /mobile-agent/skills/xiaohongshu/feed
POST /mobile-agent/skills/xiaohongshu/search
POST /mobile-agent/skills/xiaohongshu/open
POST /mobile-agent/skills/xiaohongshu/comments
```

Agent 工具：

```text
phone_xiaohongshu
```

本地真机验证：

```json
{
  "feed": {"swiped": 1},
  "search": {"search_visible": true},
  "open": {"opened": true},
  "comments": {"comments_visible": true, "comments_scrolled": 2}
}
```

只做浏览，不发评论、不私信、不购物。


## 微信固定联系人技能

专用微信账号只有联系人“叶子”。新增 `WechatSkill`：

- 打开微信
- 打开“叶子”聊天
- 输入文本
- 点击发送
- 固定联系人，禁止任意联系人、群聊、图片、文件

API：

```text
POST /mobile-agent/skills/wechat/send
```

Agent 工具：

```text
phone_wechat_send
```

本地真机和生产环境都已实际发送测试消息，截图确认消息出现在“叶子”聊天中。


## 微信入站与共享内部上下文

微信是独立入口，不是展示同步：

- 主客户端和微信的界面仍各显示各的消息
- 两边消息写入同一 Echo 内部上下文
- 上下文带 `[主客户端]` / `[微信端]` 标签
- 微信消息 visibility=`wechat_history`，主客户端历史不返回
- 微信回复只发微信，主客户端回复只发主客户端

手机端：

- NotificationListener 监听 `com.tencent.mm`
- 只接受标题为“叶子”的通知
- 按通知 key + 文本 + 时间生成消息 ID 去重
- 通过 `POST /mobile-agent/wechat/inbound` 使用设备令牌上报

后端：

- `handle_wechat_inbound`
- `generate_chat_reply(..., message_channel="wechat")`
- 回复通过 `WechatSkill` 发回微信
- 内存消息 ID 去重 10 分钟

验证：

```text
微信入站 -> replied=true
同 message_id 第二次 -> duplicate=true, replied=false
主客户端 /chat/messages -> 不包含微信消息
get_history -> 同时包含 [主客户端] 与 [微信端]
```

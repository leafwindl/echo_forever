# Echo Phone Agent B 阶段记录

> 日期：2026-11-03  
> 设备：PJC110，Android 15（API 35）  
> 状态：B0 完成，B1 骨架完成，B2 基础配对/WebSocket/observe/action/launch_app 已在本地端到端验证。

## B0 产品边界

- [x] 独立 App，不塞进现有 Echo 聊天 App
- [x] 包名 `cn.echoaiforever.phone_agent`
- [x] 只用于专用测试手机
- [x] 不 Root
- [x] 无障碍服务由用户手动开启
- [x] 前台服务常驻
- [x] 配对令牌由后端签发
- [ ] 截图授权
- [ ] 高风险操作确认
- [ ] 操作审计和紧急停止

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
- 截图授权、MediaProjection、通知读取、任务多步规划和操作审计尚未实现。
- 配对令牌保存在本机 SharedPreferences；当前版本是专用测试机骨架，不应作为生产安全实现。
- 当前 App 允许明文 HTTP，仅用于本地 adb reverse 测试；正式分发前必须移除或限制。

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

### B2 还缺

- 生产后端部署验证
- MediaProjection 截图授权
- 通知读取
- 多步任务、任务进度、紧急停止
- 操作审计
- 高风险操作确认
- 正式分发前关闭明文 HTTP

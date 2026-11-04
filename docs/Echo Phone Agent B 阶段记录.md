# Echo Phone Agent B 阶段记录

> 日期：2026-11-03  
> 设备：PJC110，Android 15（API 35）  
> 状态：B0/B1/B2 完成；B3 的通知、审计、Agent 工具、解绑和安全加固已完成；手机截图受 ColorOS 权限限制，尚未打通。

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
- `phone_screenshot`（受手机截图能力限制）
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

### 截图限制

已尝试两种方案：

1. 无障碍 `takeScreenshot`
   - 配置 `canTakeScreenshot=true`
   - ColorOS 绑定后能力位未包含截图，调用返回不可用
2. MediaProjection
   - 已实现授权、VirtualDisplay、JPEG 编码
   - 当前 ColorOS/Android 15 上授权后取不到有效画面
   - 已确认系统创建了投影 token，但应用侧没有拿到可用帧
   - 未把失败方案包装成“已支持”

因此 B3 暂不宣称手机独立运行的 MediaProjection 截图完成。

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

手机端 `screenshot` 在投影和辅助功能截图都不可用时，会尝试请求
`http://127.0.0.1:8765/screenshot`。

生产验证：

```text
GET /mobile-agent/.../screenshot -> 200
mime=image/png
chars=273348
saved bridge-shot.png
```

这解决了开发期“手机能操作但没有截图”的问题，但要求手机连接 PC/ADB；
它不是手机独立运行方案。

### B3 还缺

- 可在 ColorOS 真机工作的截图方案（需要继续评估系统限制或改用专用设备）
- 高风险操作二次确认
- 完整多步任务状态推送和用户中断 UI
- 令牌加密存储/Keystore

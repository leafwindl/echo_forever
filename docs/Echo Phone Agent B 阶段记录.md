# Echo Phone Agent B 阶段记录

> 日期：2026-11-03  
> 设备：PJC110，Android 15（API 35）  
> 状态：B0 完成，B1 骨架完成；B2 网络协议与配对尚未接入。

## B0 产品边界

- [x] 独立 App，不塞进现有 Echo 聊天 App
- [x] 包名 `cn.echoaiforever.phone_agent`
- [x] 只用于专用测试手机
- [x] 不 Root
- [x] 无障碍服务由用户手动开启
- [x] 前台服务常驻
- [ ] 配对令牌由后端签发
- [ ] 截图授权
- [ ] 高风险操作确认

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
- 目前没有 WebSocket、配对、截图授权、MediaProjection、通知读取和后端审计。
- 当前配对令牌只是本机 SharedPreferences 占位，不安全，不能用于生产。

## 下一步 B2

- 设计手机端与后端的 WebSocket 消息协议
- 设备配对、令牌和在线状态
- `observe / action / launch_app / task` 消息
- 后端 `mobile_agent` 模块
- 截图授权与临时保存
- 操作审计和紧急停止

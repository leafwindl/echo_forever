# Echo Phone Agent

B 阶段独立安卓执行端。当前是 B0/B1 骨架，不是完整产品。

## 当前已实现

- 独立包名 `cn.echoaiforever.phone_agent`
- 无障碍服务：
  - 读取当前界面 UI 树
  - 按文字查找并点击
  - Home 等全局动作
- 前台服务：常驻通知、启动/停止
- App 状态页：无障碍开关、前台服务状态、界面读取、桌面返回
- 后端配对：地址、配对码、设备名
- OkHttp WebSocket 长连接
- 远程命令：observe、launch_app、tap、tap_text、home/back/recents、text、notifications、stop
- 通知读取：NotificationListenerService，只读当前通知
- 解除本机配对
- 默认关闭明文 HTTP，仅允许本地回环测试

## 开发期截图桥

当前 ColorOS 设备上无障碍截图不可用、MediaProjection 授权后取不到帧。
开发期可以启动 PC 侧 ADB 截图桥：

```powershell
.venv\Scripts\python.exe scripts/adb_screenshot_bridge.py --serial ce7f6baf
```

桥会自动 `adb reverse tcp:8765 tcp:8765`，手机 `screenshot` 兜底请求
`http://127.0.0.1:8765/screenshot`。要求手机连接 PC/ADB。

## 尚未实现

- 手机独立运行的可用远程截图
- 长按/滑动/滚动
- 多步任务状态推送
- 高风险操作二次确认
- 令牌 Keystore 加密

## 构建

需要 JDK 17（带 `jlink`）和 Android SDK。

```powershell
$env:JAVA_HOME='D:\develop\JDK'
.\gradlew.bat assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

首次安装可能触发 ColorOS 第三方安装保护，需要手动确认。

## 开启无障碍

1. 打开 Echo Phone Agent
2. 点击“打开无障碍设置”
3. 已下载的应用 → Echo Phone Agent 界面控制
4. 开启服务，按系统提示选择“保持开启”
5. 回到 App，状态应显示“无障碍服务：已连接”

## 本地联调

1. 启动本地后端
2. `adb reverse tcp:8000 tcp:8000`
3. App 后端地址填 `http://127.0.0.1:8000`
4. 从后端生成配对码
5. 点击“配对并连接”

配对成功后，后端 `GET /mobile-agent/devices` 应显示设备在线。

## 安全边界

- 仅用于专用测试手机
- 不 Root
- 不自动绕过锁屏、支付、生物识别
- 明文 HTTP 只放行 `127.0.0.1`/`localhost`/`10.0.2.2`，其余必须 HTTPS
- 截图和通知读取仍需要用户手动授权
- 当前是专用测试机工具，不是面向普通用户的成品

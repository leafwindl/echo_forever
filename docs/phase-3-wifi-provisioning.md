# Echo 第三阶段：APP Wi-Fi 配网

状态：已完成首版接入（2026-08-24）。

## 已实现

- APP 设备页增加“重新配网”入口。
- 复用 Bread Compact 固件自带的 `78/esp-wifi-connect` 本地接口：
  - `GET http://192.168.4.1/scan`
  - `POST http://192.168.4.1/submit`
- `/scan` 返回设备扫描到的 Wi-Fi、信号强度和认证模式。
- `/submit` 接收 JSON `{ "ssid": "...", "password": "..." }`，固件连接成功后返回 `{ "success": true }`。
- Android 通过 `WifiNetworkSpecifier` 临时连接 `Xiaozhi-*` 热点，并将本地请求绑定到该网络。
- 平台不支持自动切换时，APP 引导用户打开系统 Wi-Fi 设置，返回后可以重新扫描。
- 始终保留浏览器回退：打开 `http://192.168.4.1`。

## 安全边界

- Wi-Fi 密码只发送到设备的 `192.168.4.1`。
- Wi-Fi 密码不发送到 Echo Backend，不写入 APP 本地存储，也不写日志。
- 配网成功后设备退出热点并使用已保存的 Wi-Fi 连接 Echo Backend。

## 验收

- `flutter analyze`：通过。
- `flutter test`：通过，包含固件 `/scan`、`/submit` 协议测试。
- Android Debug APK：需在当前环境继续构建验证。
- Android 真机：需连接实际 `Xiaozhi-*` 热点验证自动切换和提交。
- iOS：首版走系统 Wi-Fi 设置和浏览器回退，待 iOS 真机后再决定是否增加专用 Wi-Fi 桥接。

## 后续

1. Android 真机确认热点自动连接、扫描、提交和设备回到家庭 Wi-Fi。
2. 如需要 iOS 全自动配网，再增加 `NEHotspotConfiguration` 原生桥接和本地网络权限说明。
3. 不修改固件，除非现场发现当前组件接口不足。

# Echo HarmonyOS NEXT 客户端

这是 Echo 的 ArkUI/ArkTS 原生迁移工程，目标为 HarmonyOS NEXT Stage 模型。

## 当前状态

已完成：

- Stage 工程目录、EntryAbility 和基础资源。
- HTTP API 客户端、Bearer 会话、刷新令牌和 Preferences 本地存储。
- 手机号验证码登录、聊天历史、文字消息发送和 SSE 解析入口。
- 设备、记忆、来信、表情包、人格、主动任务、学习专注和推送注册仓储接口。
- 主页面导航和各业务入口的基础 ArkUI 页面。
- BLE/BluFi、热点配网、声纹录音、个推、本地通知和 HAP 安装的统一平台抽象。

待在 DevEco 环境完成：

- HarmonyOS NEXT SDK/DevEco 构建验证。
- BLE 扫描、GATT 连接和 BluFi AES/DH/CRC 协议移植。
- SoftAP 自动连接和本地网络绑定。
- 麦克风 PCM 采集与声纹上传。
- 个推 HarmonyOS SDK、通知点击和厂商离线通道。
- 本地通知调度。
- HAP 下载校验和系统安装授权。
- 真机端到端验收。

## 打开与构建

在安装 DevEco Studio、HarmonyOS NEXT SDK、ohpm 和 hvigor 后，用 DevEco Studio 打开本目录。

需要配置：

- `bundleName`：在 `entry/src/main/module.json5` 和签名配置中设置正式值。
- `AppConfig.baseUrl`：生产或测试 API 地址。
- 应用签名和发布证书。
- 个推 HarmonyOS AppID、厂商配置和对应 HAR。
- HAP 更新文件的签名下载地址、版本号和 SHA-256。

当前仓库环境没有 DevEco/hvigor/ohpm/hdc，因此不能在这里确认 HAP 编译或真机运行。

## 后端兼容

当前后端发布接口仍声明 Android 平台。HarmonyOS 更新发布前，需要后端允许 `platform="harmonyos"`，并返回 HarmonyOS HAP 对应的 `package_name`、`version_code`、`sha256`、`size_bytes` 和下载地址。未完成后端调整前，应用内更新只能显示状态，不能安全安装 Android APK 作为鸿蒙更新包。

## 平台适配入口

实现文件：

`entry/src/main/ets/platform/PlatformBridge.ets`

建议按以下顺序接入：

1. BLE 扫描与设备选择。
2. BluFi 安全协商、Wi-Fi 配置和事件流。
3. SoftAP 连接和浏览器回退。
4. 麦克风 PCM 录音与声纹上传。
5. 个推和通知。
6. HAP 下载、校验和安装。

# Echo HarmonyOS NEXT 客户端

这是 Echo 的 ArkUI/ArkTS 原生迁移工程，目标为 HarmonyOS NEXT Stage 模型。

## 当前状态

已完成：

- Stage 工程目录、EntryAbility 和基础资源。
- HTTP API 客户端、Bearer 会话、刷新令牌和 Preferences 本地存储。
- 手机号验证码登录、聊天历史、文字消息发送和 SSE 解析入口。
- 设备、记忆、来信、表情包、人格、主动任务、学习专注和推送注册仓储接口。
- Android 对齐的聊天、来信、表情包、人格、记忆、主动任务和学习专注页面。
- 通知权限查询、授权和系统通知设置入口；学习结束本地提醒调度与取消。
- 我的 Echo 设备列表、检测、重命名、解绑确认和凭证轮换。
- 原生 BLE 扫描、GATT 连接及 BluFi v1 DH/AES/CRC 协议实现。
- 设备热点的扫描、Wi-Fi 提交及退出配网；系统 Wi-Fi 设置和浏览器回退。
- 16 kHz 单声道 PCM16LE 录音、声纹采样上传及硬件校准接口。
- HarmonyOS 更新检查、HAP 下载进度、文件大小/SHA-256 校验和安装程序拉起尝试。
- Android 等价的清除聊天上下文确认弹窗，仅确认后发起清除请求。
- 当前本地 DevEco/SDK 构建、签名、HAP 安装和 Mate 80 启动验证通过。

尚需配置或真机验收：

- 个推 HarmonyOS SDK/HAR、CID 注册、通知点击和厂商离线通道尚未接入；通知授权不等于远程推送已可用。
- BluFi v1 已实现，但需要真实 Echo 硬件验证安全握手、配网和绑定；尚未实现 BluFi v2。
- SoftAP 使用手动系统热点连接，不冒充自动连接成功。
- 声纹需实际录音及 Echo 硬件验证，不仅检查接口或编译。
- 当前调试版的下载、校验可用，但 `viewData` 打开本地 HAP 的安装交接已出现真机失败，不能作为可用的手机端自更新能力。
- 不使用 USB 的测试分发准备与操作见 [鸿蒙手机端安装与更新操作指南](../doc/鸿蒙手机端安装与更新操作指南.md)。内部测试签名材料、描述文件签名与系统安装入口尚待接入；不得把当前调试包下载地址当作手机安装入口。
- 客户端检查发布元数据的包名/版本、文件大小和 SHA-256；实际 HAP 的签名及 Bundle 身份由系统安装程序检查。
- 更新下载支持失败后重试，尚未实现跨进程断点续传。

## 打开与构建

开发阶段默认使用 USB 更新。手机开启并允许 USB 调试后，在项目根目录执行：

```powershell
& .\harmony_app\scripts\install-usb.ps1
```

脚本读取已构建签名 HAP 的真实版本，选择唯一已授权手机，覆盖安装、核对安装版本并启动 Echo；不会卸载或清除数据。多设备时显式传入 `-DeviceId`，工具不在默认位置时传入 `-HdcPath`。这是已构建包的安装入口，修改客户端后仍须先完成构建签名。

2026-10-23 已通过 USB 在连接手机上覆盖安装并启动 `1.1.8 (10108)`。

在安装 DevEco Studio、HarmonyOS NEXT SDK、ohpm 和 hvigor 后，用 DevEco Studio 打开本目录。

需要配置：

- `bundleName`：在 `AppScope/app.json5` 和签名配置中设置正式值；当前开发值为 `cn.echoaiforever.echo_app.dev`。
- `AppConfig.baseUrl`：生产或测试 API 地址。
- 应用签名和发布证书。
- 个推 HarmonyOS AppID、厂商配置和对应 HAR。
- HAP 更新文件的签名下载地址、版本号和 SHA-256。

当前 Windows 环境工具链在 `D:/Devstudio/DevEco Studio`。命令行构建需设置
`DEVECO_SDK_HOME`、`JAVA_HOME`，并将自带 JBR 的 `bin` 和 Node 目录加入 `PATH`。

回归测试：

```powershell
& 'D:/Devstudio/DevEco Studio/tools/node/node.exe' --test tests/startup-regression.test.cjs tests/platform-features.test.cjs
```

这些测试对原生 API 使用模拟实现，不替代硬件端到端验收。

## 后端兼容

仓库现有发布接口已支持 `platform="harmonyos"`。客户端继续使用 `/releases/latest` 和
`/releases/{release_id}/download`，渠道为 `internal`，版本取实际安装的鸿蒙应用版本。
发布时需要正确填写 `package_name`、`version_code`、`sha256` 和 `size_bytes`，
并提供 HTTPS 下载地址；客户端拒绝 Android APK 元数据和不匹配的包名。
本轮功能完善不修改后端业务代码或线上部署。

## 平台适配入口

实际页面直接调用下列实现；旧 `PlatformBridge.ets` 不作为已完成功能的依据：

- `DeviceCapabilities.ets`：权限、BLE 扫描、系统设置和 PCM 录音。
- `HarmonyBlufi.ets` / `BlufiProtocol.ets`：BluFi v1 安全配网。
- `DeviceNetwork.ets`：设备热点本地 HTTP。
- `HarmonyNotifications.ets`：原生通知权限和学习提醒。
- `HarmonyUpdater.ets` / `model/AppRelease.ets`：更新元数据、下载校验与安装交接。

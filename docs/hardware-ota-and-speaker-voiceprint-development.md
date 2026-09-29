# Echo 硬件 OTA 与声纹功能开发文档

状态：开发规划

2026-09-28 更新：声纹方案已调整为 CAM++ 多人员显式录入，原统计特征及主人授权
规划不再作为当前实现依据。请先阅读 [本地联调文档](local-device-and-speaker-lab.md)；
本文其余内容保留作历史设计与硬件 OTA 规划参考。

编写日期：2026-09-02

## 1. 目标

完善 Echo 设备的两项能力：

1. 硬件固件 OTA：让设备能够安全地发现、下载、校验、安装和回滚固件。
2. 声纹功能：让用户能够录入、查看、删除主人声纹，并在设备语音交互时识别主人或未知说话人。

第一阶段以 Android 和当前 Echo 硬件为主，不扩展到多板卡、多平台和复杂的声纹管理场景。

## 2. 当前基线

### 2.1 硬件 OTA 已有能力

固件端 `main/ota.cc` 已经具备：

- 启动或激活阶段请求 `/devices/firmware/config`。
- 上报 `Device-Id`、`Client-Id`、`Firmware-Version` 等信息。
- 解析服务器返回的 `firmware.version` 和 `firmware.url`。
- 比较当前版本和远端版本。
- 使用 ESP-IDF OTA API 写入备用分区。
- 设置备用分区为下一次启动分区。
- 重启设备并在启动后确认镜像有效。
- 启动失败时使用 ESP-IDF 的回滚机制。

目前缺少的是完整的固件发布后台、固件包完整性元数据、板卡兼容性策略和发布验证流程。

### 2.2 声纹已有能力

后端已经存在以下接口和基础逻辑：

```text
GET    /devices/{device_id}/speaker
POST   /devices/{device_id}/speaker/enrollment
DELETE /devices/{device_id}/speaker
```

后端当前可以：

- 接收 PCM 音频。
- 提取 embedding。
- 保存声纹 profile 和录入样本。
- 查询和撤销声纹 profile。
- 设备语音交互时计算相似度。
- 返回 `owner`、`unknown`、`verified`、`rejected` 等状态。
- 记录声纹 profile、置信度和验证状态。

App 端目前已经有 API、数据模型和部分控制器方法，但没有完整的录音录入页面和用户操作流程。

## 3. 非目标

本阶段暂不做：

- iOS 专用蓝牙声纹录入流程。
- 多个主人声纹和复杂家庭成员权限体系。
- 训练独立的深度声纹模型。
- 在设备端运行完整声纹模型。
- 静默安装硬件固件或绕过用户确认。
- 对所有历史硬件板卡提供统一固件。

## 4. 硬件 OTA 方案

### 4.1 发布流程

```text
构建指定 Echo 板卡固件
    -> 读取固件版本和板卡身份
    -> 计算 SHA-256 和文件大小
    -> 上传 COS 临时对象
    -> 校验 COS 对象大小和元数据
    -> 写入固件发布记录
    -> 激活发布
    -> 使用真实设备验证升级和回滚
```

固件发布必须绑定板卡身份，不能仅按版本号发布。错误板卡固件不得推送给设备。

### 4.2 数据表

建议新增独立的 `firmware_releases` 表，不复用 Android 的 `app_releases` 表。

```text
firmware_releases
- release_id
- platform              固定为 esp32
- board_type             板卡类型
- board_variant          板卡变体或构建名称
- firmware_version       例如 0.1.5
- minimum_version        最低允许升级版本
- cos_object_key
- sha256
- size_bytes
- release_notes          JSON 数组
- mandatory
- status                 draft / active / revoked
- published_at
- created_at
- updated_at
```

唯一约束建议为：

```text
(board_type, board_variant, firmware_version)
```

### 4.3 固件查询接口

保留现有设备端接口：

```text
GET/POST /devices/firmware/config
```

根据设备请求头和系统信息匹配固件：

```text
Device-Id
Client-Id
Firmware-Version
```

系统信息 JSON 中还应包含稳定的板卡身份，例如：

```json
{
  "board": {
    "type": "echo",
    "name": "echo-s3"
  }
}
```

有可用更新时返回：

```json
{
  "firmware": {
    "version": "0.1.5",
    "url": "https://download.example/firmware.bin",
    "sha256": "64 位小写十六进制字符串",
    "size_bytes": 3145728,
    "board_type": "echo",
    "board_variant": "echo-s3",
    "force": 0
  }
}
```

没有更新时返回空的 `firmware` 对象或不返回 `firmware` 字段，保持现有固件兼容性。

### 4.4 设备端增强

在现有 `Ota::Upgrade()` 基础上增加：

- 校验 HTTP `Content-Length` 与 `size_bytes`。
- 流式计算 SHA-256，下载完成后与服务器值比较。
- 校验目标固件的 ESP-IDF app description。
- 校验固件板卡身份与当前设备身份一致。
- 拒绝版本下降，除非明确配置允许回滚。
- 下载失败或摘要不一致时中止并清理 OTA 状态。
- 升级成功后上报新的 `Firmware-Version`。
- 保留现有启动确认和自动回滚逻辑。

敏感信息不得写入 OTA 日志；日志可以记录版本、大小、阶段和错误码，但不能记录设备凭证。

### 4.5 OTA 验收

- 当前版本低于目标版本时能正常升级。
- 当前版本等于目标版本时不重复下载。
- 版本下降默认被拒绝。
- 错误板卡不会获得更新。
- 文件大小错误时拒绝安装。
- SHA-256 不一致时拒绝安装。
- 下载中断后设备仍能启动旧固件。
- 新固件启动失败时自动回滚。
- 升级成功后设备列表显示新版本。
- 发布记录、COS 对象和设备实际版本一致。

## 5. 声纹方案

### 5.1 App 用户流程

在“我的 Echo”设备设置中增加“声纹设置”：

```text
未录入声纹
    -> 开始录入
    -> 录音样本 1
    -> 录音样本 2
    -> 录音样本 3
    -> 上传并生成声纹
    -> 显示已录入：主人
```

已有声纹时提供：

- 查看状态。
- 重新录入。
- 删除声纹。

录音页面需要具备：

- 麦克风权限申请。
- 录音开始、停止和取消。
- 录音时长显示。
- 音量过低提示。
- 最短时长校验。
- 上传中、成功、失败状态。
- 失败时保留旧声纹。

### 5.2 音频格式

App 统一向后端上传：

```text
PCM signed 16-bit
单声道
16000 Hz
Content-Type: audio/L16
```

录音格式转换必须在 App 端完成，不能把手机原始编码格式直接交给后端。

### 5.3 后端录入策略

每次录入至少收集 3 条有效样本。后端对每条样本执行：

1. 音频长度检查。
2. 静音和音量检查。
3. 音频质量评分。
4. embedding 提取。
5. 保存样本记录。

只有满足最低有效样本数后，才创建或替换 active profile。新录入失败时，旧 profile 必须继续可用。

建议 profile 保存：

```text
speaker_profiles
- speaker_profile_id
- owner_user_id
- device_id
- display_name
- role
- embedding
- model_name
- model_version
- verification_threshold
- status
- created_at
- updated_at
```

原始录音只用于短期处理，不作为长期声纹数据保存。embedding 和原始音频都不能写入普通日志。

### 5.4 识别策略

```text
设备上传语音
    -> 提取当前语音 embedding
    -> 读取设备 active profile
    -> 计算相似度
    -> 与阈值比较
    -> owner 或 unknown
```

识别结果至少包含：

```json
{
  "speaker_profile_id": "speaker_xxx",
  "speaker_role": "owner",
  "confidence": 0.91,
  "status": "verified"
}
```

当没有 profile、音频不可用或识别服务异常时，默认返回 `unknown`，不能默认当作主人。

只有 `owner` 才允许启用主人专属记忆或其他需要身份确认的能力。

### 5.5 声纹验收

- 用户可以从设备设置进入声纹页面。
- 首次录入 3 条有效样本后生成 profile。
- 录音过短、静音或质量不足时给出明确提示。
- 录入失败不会删除旧 profile。
- 查询接口能显示 active profile。
- 删除后查询不到 active profile。
- 主人语音在测试样本中识别为 `owner`。
- 陌生人语音识别为 `unknown`。
- 无 profile 时识别为 `unknown`。
- 解绑设备后声纹 profile 被撤销或无法继续使用。
- 不在日志中输出原始音频和 embedding。

## 6. 实施阶段

### 阶段一：硬件 OTA 后端

- 新增固件发布表和仓储。
- 新增固件上传/发布脚本。
- 固件包上传 COS 并校验大小。
- 改造 `/devices/firmware/config` 返回完整元数据。
- 增加板卡身份匹配。

交付物：可以发布一个指定 Echo 板卡的固件版本。

### 阶段二：硬件 OTA 设备端

- 增加 SHA-256 校验。
- 增加文件大小校验。
- 增加板卡和版本兼容性检查。
- 验证正常升级、断网恢复和启动回滚。

交付物：设备可以安全升级，并且失败后仍可恢复。

### 阶段三：声纹 App 录入

- 增加声纹设置入口。
- 增加 Android 录音权限和 PCM 录音流程。
- 增加三次录音和上传页面。
- 接通查询、录入、删除接口。

交付物：用户可以在 Android App 中完成声纹录入和删除。

### 阶段四：声纹质量与实机验证

- 完善质量阈值和多样本聚合。
- 测试主人、陌生人、噪声和无声纹四类场景。
- 验证设备语音流程中的 owner/unknown 行为。
- 检查解绑、重新录入和异常恢复。

交付物：声纹功能达到可试用状态。

## 7. 发布和回滚原则

- 硬件 OTA 发布必须使用新固件版本，不能覆盖已有版本记录。
- 生产发布前必须保存 APK/固件的 SHA-256、大小和发布 ID。
- 固件发布后先对一台测试设备升级，再扩大范围。
- 任何 SHA-256、板卡身份或版本校验失败都不得报告升级成功。
- 回滚只能恢复到已验证的兼容固件。
- 声纹模型或阈值调整应保留旧 profile 的可恢复路径。

## 8. 测试要求

代码测试：

- 后端发布接口和数据库仓储测试。
- 固件 JSON 解析和版本比较测试。
- OTA 元数据校验测试。
- 声纹录入质量和相似度测试。

设备测试：

- 当前 Echo S3 实机正常升级。
- 升级中断后重启。
- 错误固件和篡改固件拒绝安装。
- 声纹录入、主人识别、陌生人识别和删除。

App 测试：

- 更新弹窗、下载、校验和系统安装确认。
- 声纹权限、录音、上传和错误提示。
- 网络断开、权限拒绝和重复点击。

## 9. 推荐优先级

建议优先完成硬件 OTA 的发布后台和完整性校验，再做声纹 App 录入页面。原因是硬件 OTA 会影响设备可恢复性，应该先建立可控的发布和回滚机制；声纹则可以在现有后端能力上逐步补齐用户界面。

# Echo 桌面机器人第一阶段开发与烧录手册

## 1. 仓库边界

第一阶段使用两个独立仓库：

```text
AI_Chat
  Flutter APP
  Echo Backend
  设备协议与部署文档

echo-device-firmware
  ESP32-S3 固件
  Echo Bread Compact 板型
  固件构建、烧录和发布产物
```

设备服务端不单独建立第三个仓库。设备认证、WebSocket、ASR/Chat/TTS
编排属于 Echo Backend；音频采集、Opus、按键、OLED 和播放属于固件。

## 2. 第一阶段链路

```text
Bread Compact 16 kHz 麦克风
-> 60 ms Opus 帧
-> WSS /devices/ws
-> Opus 解码为 16 kHz PCM16LE
-> 腾讯 ASR
-> Echo Chat / Persona / Relationship / Memory
-> CosyVoice 或 Edge TTS
-> 24 kHz / 60 ms Opus 帧
-> Bread Compact 扬声器
```

同步语音业务复用现有 `conversation_mode=call`。用户语音和 Echo 回复以
`voice_asr`、`voice_reply` 类型写入正常聊天历史，APP 无需新增一套机器人
消息页面。

## 3. 第一版认证

第一版只供个人单设备使用，不先开发扫码绑定。设备通过三项信息认证：

```text
Device-Id  ESP32 MAC
Client-Id  固件保存在 NVS 中的 UUID
Token      Echo 独立设备密钥
```

服务器配置示例：

```dotenv
ECHO_DEVICE_TOKEN=<使用密码工具生成的随机长字符串>
ECHO_DEVICE_USER_MAP_JSON={"aa:bb:cc:dd:ee:ff|*":"你的 Echo user_id"}
ECHO_FIRMWARE_VERSION=0.1.0
PUBLIC_BASE_URL=https://api.echoaiforever.cn
```

设备 Token 不能与 APP access token、JWT secret 或第三方 API Key 相同。
完整镜像首次烧录可能生成新的 `Client-Id`，因此第一次启动可临时使用
`Device-Id|*`。从串口日志读到新的 `Client-Id` 后，应立刻改成精确映射。

## 4. 固件版本与板型

```text
固件版本：0.1.0
协议版本：echo-device-v1 / Xiaozhi WebSocket v1 compatible
板型目录：main/boards/echo/bread-compact-wifi
```

OLED 有两个互不兼容的构建变体：

```text
echo-bread-compact-wifi-128x32
echo-bread-compact-wifi-128x64
```

必须按实体 OLED 高度选择，不能凭感觉烧录。当前可用旧固件
`F:\tmp\bat\merged-binary.bin` 是恢复基线，在 Echo 固件实机通过以前不要删除。

## 5. 构建产物

固件构建必须输出：

```text
echo_device.bin     OTA 应用镜像
merged-binary.bin   完整首次烧录镜像
build.log           完整构建日志
manifest.json       版本、板型、ESP-IDF、大小和 SHA-256
```

个人开发仍然保存每个成功烧录版本的 manifest，避免以后不知道设备中到底运行
了哪个源码提交。

## 6. 首次实机前的检查

1. 旧固件仍能通过小智官方服务正常收音和播放。
2. Windows 设备管理器能看到 `USB-Enhanced-SERIAL CH343`。
3. 已确认实际 OLED 为 128x32 或 128x64。
4. 已保存旧固件、SHA-256 和烧录工具。
5. Echo 后端设备 WebSocket 已在测试环境通过。
6. 腾讯 ASR、Echo Chat、TTS 在服务器上均可正常调用。
7. 新固件容器构建成功，manifest 状态为 `succeeded`。

## 7. 你需要完成的实机动作

软件侧准备完成后，使用者只需要：

1. 保持现有接线不变，通过 Type-C 数据线连接电脑。
2. 从旧固件串口读取稳定的 `Device-Id`，用 `Device-Id|*` 配置首次启动。
3. 烧录后从 Echo 固件串口读取新 `Client-Id`，再改成精确映射。
4. 先擦除并烧录正确 OLED 变体的 `merged-binary.bin`。
5. 重新进行 Wi-Fi 配网。
6. 按住说话键说一句短句，松开等待 Echo 回复。
7. 验证 APP 聊天页能看到用户语音文本和 Echo 回复。

第一次烧录时不要调整杜邦线、引脚或音量电路。若失败，先用旧固件回刷，
再根据串口日志判断是固件、网络、认证、ASR、TTS 还是音频格式问题。

## 8. 第一阶段验收

- 连续完成 20 轮短句对话，无重启、卡死或重复播放。
- ASR 不明显丢失语句开头和结尾。
- Echo 能使用 APP 中已有的人格、称呼和长期记忆。
- APP 打开时能同步设备对话，刷新后历史仍存在。
- TTS 播放完整，无持续爆音，失败后设备能回到空闲状态。
- 断网恢复后可重新建立会话。
- 设备 Token 错误或设备 ID 未配置时连接被拒绝。

第一阶段不验收全双工打断、摄像头、MCP 动作、导航或 APP 扫码绑定。

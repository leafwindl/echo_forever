# Voice 模块

## 1. 业务目标

Voice 模块为电话模式提供流式 ASR、TTS 分段合成、音频存储与清理能力。Chat 模块仍负责对话、人格、记忆与消息落库，Voice 不重复编排聊天业务。

## 2. 当前链路

### 流式 ASR 主链路

1. 小程序用 MP3 格式录音，并通过 `RecorderManager.onFrameRecorded` 获取音频帧。
2. 小程序连接 `WS /voice/asr/stream`，用 `Authorization: Bearer <token>` 鉴权。
3. 后端限制每次连接的累计音频大小和用户/全局频率。
4. 后端用 FFmpeg 将连续 MP3 帧解码成 16 kHz、单声道、16-bit PCM。
5. PCM 通过内网 WebSocket 发送给 FunASR 2-pass 服务。
6. 在线结果以 `partial` 返回，用户松手后以 `final` 返回最终文本。
7. 小程序将最终文本交给现有 `POST /chat/send`，不建立第二套聊天链路。

### ASR 降级链路

如果流式 WebSocket、FunASR 或 FFmpeg 不可用，小程序保留本次完整 MP3 临时文件，自动调用 `POST /voice/asr`，继续使用腾讯离线 ASR。该临时文件识别结束后立即删除。

### 分段 TTS 链路

1. Chat 得到完整文字回复后调用 Voice。
2. Voice 优先按句号、问号、感叹号和分号切分，再按配置的最大字符数硬切。
3. 每段分别调用当前 TTS provider。
4. EdgeTTS 生成 MP3；MeloTTS 独立服务生成 WAV。
5. `POST /chat/send` 同时返回兼容字段 `audio_url` 和新字段 `audio_urls`。
6. 小程序按 `audio_urls` 顺序播放；挂断会停止当前段，并终止后续段播放。

当前“分段播放”指服务端完成各段合成后一次返回 URL 列表，并非边合成边下发音频流。

## 3. 对外契约

### HTTP / WebSocket

- `POST /voice/asr`：整段 MP3 识别，作为兼容和降级入口。
- `WS /voice/asr/stream`：MP3 帧流式识别。
  - 客户端二进制消息：MP3 frame。
  - 客户端文本消息：`{"event":"stop"}` 或 `{"event":"cancel"}`。
  - 服务端消息：`ready`、`partial`、`final`、`error`。
- `POST /chat/send`：电话模式传 `voice_reply_enabled=true`，响应包含 `audio_url` 与 `audio_urls`。

### 模块公开能力

- `recognize_voice(audio_bytes, content_type)`
- `open_streaming_voice_recognition()`
- `synthesize_voice_reply(text)`
- `cleanup_expired_voice_audio()`

## 4. Provider 与服务边界

- 腾讯 ASR：现有整段识别降级服务。
- FunASR：独立 Docker 服务，只负责实时/2-pass ASR。
- EdgeTTS：默认 TTS provider，保证未启用本地模型时功能可用。
- MeloTTS：独立 Python 3.9 Docker 服务，避免其模型依赖污染主后端 Python 3.11 环境。
- FFmpeg：安装在主后端容器，只负责 MP3 到 PCM 的流式解码。

供应商替换通过 `providers/` 和 Voice infrastructure adapter 完成，不修改 Application 用例。

## 5. 关键配置

```dotenv
TTS_PROVIDER=edge
TTS_VOICE_ID=zh-CN-XiaoxiaoNeural
TTS_SPEED=1.0
TTS_SEGMENT_MAX_CHARS=80
TTS_REPLY_MAX_CHARS=600
TTS_AUDIO_MAX_BYTES=10485760
MELOTTS_BASE_URL=http://127.0.0.1:9000
MELOTTS_TIMEOUT_SECONDS=60

VOICE_STREAMING_ASR_ENABLED=false
FUNASR_WS_URL=ws://127.0.0.1:10095
FUNASR_MODE=2pass
FUNASR_FINAL_TIMEOUT_SECONDS=15
FFMPEG_BINARY=ffmpeg
```

Docker Compose 会把主后端的 MeloTTS/FunASR 地址覆盖为同一网络内的服务名。启用 MeloTTS 时还需把 `TTS_VOICE_ID` 改为 `ZH`。

## 6. 文件与安全

- 上传目录：`static/voices/uploads/`，整段 ASR 完成后立即删除。
- 生成目录：`static/voices/generated/`，支持 `.mp3` 和 `.wav`，按保留时间清理。
- 流式 ASR 音频仅在内存、FFmpeg 管道和 FunASR 会话中传递，不写入本地文件。
- WebSocket 只接受 Bearer Token，不使用 query token，避免 token 出现在访问日志。
- `VOICE_UPLOAD_MAX_BYTES` 同时约束整段上传和单个流式会话累计字节数。
- 公网 Nginx 必须开启 WebSocket Upgrade，配置示例见 `deploy/nginx/echo-api.conf.example`。

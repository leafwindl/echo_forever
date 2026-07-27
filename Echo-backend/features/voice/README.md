# Voice Feature

Voice 为独立电话页提供实时 ASR、完整录音降级识别、TTS 合成、音频存储和过期清理。对话、人格、记忆与关系仍由 Chat 负责。

## 电话链路

1. 小程序通过 `WS /voice/asr/stream` 发送 MP3 录音帧，Bearer Token 位于 WebSocket Header。
2. 后端使用腾讯实时 ASR 返回识别片段。
3. WebSocket 不可用时，小程序将完整 MP3 上传到 `POST /voice/asr`。
4. 最终文本发送到 `POST /chat/send`，请求 `mode=call`。
5. Chat 生成口语化完整回复，Voice 使用 CosyVoice v3.5 Flash 合成音频。
6. API 一次返回完整文字和 `audio_urls`；小程序按顺序播放，挂断立即停止。

TTS provider 的 SDK 可以流式接收供应商音频，但 1.0 对客户端不暴露流式 TTS 或 SSE。

## 配置

```dotenv
VOICE_STREAMING_ASR_ENABLED=true
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
TENCENT_APP_ID=0
TENCENT_ASR_ENGINE_MODEL_TYPE=16k_zh
TENCENT_ASR_FINAL_TIMEOUT_SECONDS=10

TTS_PROVIDER=cosyvoice
TTS_VOICE_ID=
DASHSCOPE_API_KEY=
DASHSCOPE_WORKSPACE_ID=
COSYVOICE_MODEL=cosyvoice-v3.5-flash
COSYVOICE_WEBSOCKET_URL=
COSYVOICE_TIMEOUT_SECONDS=30
TTS_SEGMENT_MAX_CHARS=80
TTS_REPLY_MAX_CHARS=600
```

`DASHSCOPE_API_KEY`、Workspace 和音色 ID 必须属于同一业务空间。上传录音在识别后删除，生成音频由定时任务按保留期清理。

# Voice Feature

Voice 为独立电话页提供实时 ASR、完整录音降级识别、TTS 合成、音频存储和过期清理。对话、人格、记忆与关系仍由 Chat 负责。

一轮回复只发起一次 TTS 请求并生成一个音频文件，避免逐句重新起调和播放器拼接。Voice Domain 根据完整回复选择克制的自然、好奇、关心、轻快或认真表达；Infrastructure 只负责把选定指令传给具体 TTS Provider。

## 电话链路

1. 小程序通过 `WS /voice/asr/stream` 发送 MP3 录音帧，Bearer Token 位于 WebSocket Header。
2. 后端使用腾讯实时 ASR 返回识别片段。
3. WebSocket 不可用时，小程序将完整 MP3 上传到 `POST /voice/asr`。

## 音色自然度对比

固定语料位于 `tests/fixtures/voice_naturalness_cases.json`。比较当前设计音色、新设计音色或录音复刻音色时，必须使用同一模型参数和整批语料，每条按 1 至 5 分记录：

- 人声自然度：是否有合成感、播音腔或过度平滑。
- 韵律连贯性：句内轻重音和句间停顿是否像一次完整表达。
- 情绪匹配：表达是否符合语义，同时不过度夸张。
- 关系匹配：初识温暖但不过度亲密，好奇不呈现客服或审问感。

盲听时隐藏音色来源并随机播放顺序。先比较总分和各维度中位数，再决定是否更换音色；不要只凭单句印象调整 Persona 或供应商参数。
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
TTS_REPLY_MAX_CHARS=600
```

`DASHSCOPE_API_KEY`、Workspace 和音色 ID 必须属于同一业务空间。上传录音在识别后删除，生成音频由定时任务按保留期清理。

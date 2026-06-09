# Voice 模块

## 1. 业务目标

负责语音输入和语音回复能力，包括上传音频保存、ASR 识别、调用 Chat 生成回复、TTS 合成，以及生成可访问的音频 URL。

## 2. 核心业务流程

### ASR 识别流程

1. 接收用户上传的语音文件。
2. 校验音频格式，目前只接受 MP3。
3. 校验音频内容不能为空。
4. 将上传音频保存到本地静态目录。
5. 调用 ASR provider 识别音频内容。
6. 返回识别出的用户文本。

### 语音回复流程

1. 接收用户文本和当前用户身份。
2. 将文本交给 Chat 模块生成 AI 回复。
3. Chat 模块负责上下文构建、LLM 调用、消息落库、摘要更新和记忆调度。
4. Voice 模块拿到 AI 文本回复后，调用 TTS provider 合成音频。
5. 保存生成的音频文件。
6. 基于公开访问地址生成音频 URL。
7. 返回 AI 文本回复和音频 URL。

## 3. 对外契约

### HTTP API

- `POST /voice/asr`
  - Response: `VoiceASRResponse`
- `POST /voice/reply`
  - Request: `VoiceReplyRequest`
  - Response: `VoiceReplyResponse`

### 发布的事件

- 当前无已落地事件。
- 预留事件：`VoiceRecognized`、`VoiceReplyGenerated`。

### 依赖的其它模块接口

- Chat 模块：根据语音识别后的文本生成 AI 回复。
- ASR Provider：将音频识别为文本。
- TTS Provider：将 AI 文本回复合成为音频。
- 配置服务：读取公开访问地址、ASR 密钥和默认音色。

## 4. 数据库表

- `conversations`
- `chat_messages`
- `user_memories`
- `background_jobs`

## 5. 关键配置项

- `TENCENT_SECRET_ID`
- `TENCENT_SECRET_KEY`
- `MINIMAX_TTS_VOICE_ID`
- `PUBLIC_BASE_URL`

## 6. 注意事项

- 当前 ASR 只接受 MP3 content type。
- 语音回复中的对话落库仍由 Chat 模块统一处理。
- 生成音频保存在 `Echo-backend/static/voices/`，返回 URL 依赖 `PUBLIC_BASE_URL`。
- ASR/TTS 供应商替换应通过 provider registry，不要改 Application。

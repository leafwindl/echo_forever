# Voice 模块

## 1. 业务目标

负责语音输入和语音回复能力，包括上传音频保存、ASR 识别、调用 Chat 生成回复、TTS 合成，以及生成可访问的音频 URL。

## 2. 核心业务流程

### ASR 识别流程

1. 接收用户上传的语音文件。
2. 校验音频格式，目前只接受 MP3。
3. 校验音频内容不能为空。
4. 将上传音频保存到临时上传目录。
5. 调用 ASR provider 识别音频内容。
6. 无论识别成功或失败，都清理本次上传的临时音频。
7. 返回识别出的用户文本。

### 语音回复流程

1. 接收用户文本和当前用户身份。
2. 将文本交给 Chat 模块生成 AI 回复。
3. Chat 模块负责上下文构建、LLM 调用、消息落库、摘要更新和记忆调度。
4. Voice 模块拿到 AI 文本回复后，调用 TTS provider 合成音频。
5. 将生成音频保存到可公开访问的生成目录。
6. 基于公开访问地址生成音频 URL。
7. 返回 AI 文本回复和音频 URL。

### 文件清理流程

1. ASR 上传音频只用于本次识别，识别结束后立即删除。
2. TTS 生成音频需要给前端播放，按配置的保留时间定期清理。
3. 应用启动时会先执行一次清理，随后按固定间隔后台清理。
4. 清理只处理语音目录下的 `.mp3` 文件，并限制单次批处理数量。
5. 清理失败只记录日志，不影响聊天、ASR 或 TTS 主流程。

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
- `VOICE_GENERATED_RETENTION_SECONDS`
- `VOICE_UPLOAD_RETENTION_SECONDS`
- `VOICE_CLEANUP_INTERVAL_SECONDS`
- `VOICE_CLEANUP_BATCH_SIZE`

## 6. 注意事项

- 当前 ASR 只接受 MP3 content type。
- 语音回复中的对话落库仍由 Chat 模块统一处理。
- 上传音频保存在 `Echo-backend/static/voices/uploads/`，识别结束后会立即删除。
- 生成音频保存在 `Echo-backend/static/voices/generated/`，返回 URL 依赖 `PUBLIC_BASE_URL`。
- 历史版本遗留在 `Echo-backend/static/voices/` 根目录下的 MP3 也会按生成音频保留时间清理。
- ASR/TTS 供应商替换应通过 provider registry，不要改 Application。

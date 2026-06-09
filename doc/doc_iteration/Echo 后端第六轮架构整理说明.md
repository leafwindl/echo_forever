# Echo 后端第六轮架构整理说明

## 目标

本轮继续按 `doc/Echo 后端架构与代码规范.md` 做渐进式迁移，重点整理 `voice` 语音能力。

目标：
- 将 ASR 和语音回复编排迁移到 `features/voice`。
- 让 Voice Application 只依赖 Domain 抽象，不直接依赖 FastAPI、文件系统、ASR/TTS SDK。
- 保留现有 `/voice/asr`、`/voice/reply` API 契约。
- 为后续替换 ASR、TTS、音频存储实现预留标准接口。

## 改了什么

### 1. 新增 `features/voice`

新增结构：

```text
Echo-backend/features/voice/
  domain/
    entities.py
    services.py
  application/
    use_cases.py
  infrastructure/
    adapters.py
    container.py
  public.py
```

### 2. Domain 层

`features/voice/domain` 定义：
- `VoiceRecognitionResult`
- `VoiceReplyResult`
- `UnsupportedVoiceFormatError`
- `VoiceAudioStorage`
- `VoiceRecognizer`
- `VoiceSynthesizer`
- `VoiceChatResponder`

Domain 只保留语音业务概念和抽象协议，不依赖 FastAPI、Pydantic、文件系统、Tencent ASR、Edge TTS 或 Chat 具体实现。

### 3. Application 层

新增两个用例：
- `RecognizeVoice`：校验音频格式和内容，保存上传音频，调用 ASR，返回识别文本。
- `GenerateVoiceReply`：调用聊天回复能力，调用 TTS，保存生成音频，返回文字和音频 URL。

Application 只通过构造函数接收 Domain 协议实现，符合依赖倒置要求。

### 4. Infrastructure 层

`features/voice/infrastructure/adapters.py` 将现有能力适配为 Voice Domain 协议：
- `LocalVoiceAudioStorage` 适配本地音频存储。
- `TencentVoiceRecognizer` 适配腾讯 ASR。
- `EdgeVoiceSynthesizer` 适配当前 TTS provider。
- `ChatVoiceResponder` 通过 `features.chat.public.generate_chat_reply` 调用聊天能力。

跨 feature 调用只依赖对方 `public.py`，不引用对方内部 application/domain/infrastructure。

### 5. Interface 层

`api/routers/voice.py` 已改为调用 `features.voice.public`：
- `/voice/asr` 负责 HTTP 上传、错误码映射和 response schema。
- `/voice/reply` 负责用户身份注入、错误码映射和 response schema。

路由不再直接创建临时文件、不直接调用 ASR/TTS 具体实现。

### 6. 补充测试

新增 `Echo-backend/tests/test_voice_feature.py`，使用 fake storage/recognizer/synthesizer/chat responder 覆盖：
- MP3 音频识别主流程。
- 非 MP3 格式拒绝。
- 语音回复编排流程。

## 为什么这么改

- 将语音能力从技术型 service 调用推进到 feature-first 结构，边界更清楚。
- ASR、TTS、音频存储都变成可替换插件点，后续换云厂商或存储方式时，不需要改 Application。
- API 路由只做接口适配，业务流程集中在 Application，降低 Interface 和 Infrastructure 的耦合。
- 用 fake 实现测试 Application，避免测试依赖真实外部服务。

## 验证结果

已执行架构依赖检查：

```bash
python -B scripts\check_architecture.py
```

结果：

```text
Architecture check passed
```

已执行语法编译检查：

```bash
python -B -m py_compile Echo-backend\features\voice\domain\entities.py Echo-backend\features\voice\domain\services.py Echo-backend\features\voice\application\use_cases.py Echo-backend\features\voice\infrastructure\adapters.py Echo-backend\features\voice\infrastructure\container.py Echo-backend\features\voice\public.py Echo-backend\api\routers\voice.py Echo-backend\tests\test_voice_feature.py
```

结果：通过。

已执行完整单元测试：

```bash
python -B -m unittest discover -s Echo-backend\tests
```

结果：

```text
Ran 20 tests
OK
```

已执行应用装配检查：

```bash
python -B -c "import sys; sys.path.insert(0, 'Echo-backend'); import main; print(len(main.app.routes))"
```

结果：

```text
14
```

## 尚未完成

仍处于过渡结构：

- `api/routers` 还未下沉到各 feature 的 `interface` 层。
- `services.audio_storage`、`services.tencent_asr` 仍作为兼容基础设施存在。
- 顶层 `providers` 仍需逐步迁移到对应 feature 或 shared infrastructure。
- 错误响应还未统一为 `{code, message, request_id}`。

下一轮建议：
- 将 `api/routers/chat.py`、`api/routers/memory.py`、`api/routers/voice.py` 迁移到各 feature 的 `interface` 层，再由顶层 API 统一注册。
- 或者先抽出 shared `config/settings`，把 provider、超时、存储目录等环境相关配置集中注入。

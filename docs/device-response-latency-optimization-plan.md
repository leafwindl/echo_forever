# Echo 机器人语音回复速度优化方案

> 文档版本：v1.0  
> 编写日期：2026-08-15  
> 适用范围：Echo Bread Compact + Echo Backend 第一阶段语音机器人  
> 当前固件基线：`0.1.3`  
> 当前状态：阶段一、阶段二后端实现完成，阶段三实时 ASR 已进入服务器验证

## 1. 目标

本方案的目标不是单纯更换一个模型，而是把机器人从“整轮处理完成后才开始播放”改成“生成到一个自然短句就开始播放”。

目标分为三个层级：

| 层级 | 目标 |
| --- | --- |
| 第一阶段低风险优化 | 从当前约 4 秒开始出声，降低到约 2～2.5 秒 |
| 第二阶段流式优化 | LLM、TTS、Opus 同时处理，约 1.2～1.6 秒开始出声 |
| 第三阶段体验优化 | 实时 ASR、长连接、打断和回声处理，接近智能音箱体验 |

这里的“开始回复”指机器人开始播放第一段有意义的语音，不是整句话全部播放完毕。整句话的总播放时间会随着回答长度变化。

## 2. 当前系统

### 2.1 当前链路

```text
Bread Compact 说完
  -> 服务器等待静音端点
  -> 腾讯 ASR 一次性识别
  -> Echo 构建人格、记忆、历史上下文
  -> DeepSeek 生成完整文字
  -> CosyVoice 生成完整音频文件
  -> 服务器把完整音频转成 Opus
  -> WebSocket 发送给机器人
  -> 机器人播放
  -> APP 同步本轮消息
```

### 2.2 当前实测基线

2026-08-14 的线上实机测试记录如下：

| 环节 | 实测值 | 说明 |
| --- | ---: | --- |
| 自动静音端点 | 800 ms | 用户停止说话后才结束录音 |
| 腾讯 ASR | 143 ms | 仅代表本次短语音，不代表长语音固定耗时 |
| 上下文 + DeepSeek 完整回复 | 1608 ms | 当前等待完整结果 |
| CosyVoice 首个音频包 | 704 ms | API 内部已具备流式能力 |
| CosyVoice 完整合成 | 1297 ms | 当前后端等待到这里 |
| 播放启动延迟 | 120 ms | 服务器配置 |
| 完整处理轮次 | 约 7988 ms | 包含整段语音播放时间 |

当前最重要的问题是：**代码没有利用流式首包**。

CosyVoice 已经产生首个音频包，但 `SynthesizeVoiceReply` 会先收集完整音频、保存成文件；设备路由随后再次读取完整文件、全部转成 Opus，最后才开始发送。因此模型的流式优势被抵消了。

## 3. 核心设计原则

### 3.1 APP 和机器人保持同一个模型

为降低配置和维护复杂度，APP 与机器人继续使用同一个 DeepSeek 模型、同一套人格、记忆、关系阶段和历史对话。优化重点改为流式输出和音频流水线，不再把更换 LLM 作为既定方案。

```text
APP 文字聊天       -> 当前 DeepSeek 模型
机器人语音聊天     -> 同一个 DeepSeek 模型 + 通话短句约束 + 流式输出
```

只有交付方式不同，不增加第二套模型配置和供应商维护成本。

### 3.2 先优化“开始出声”，再优化“整句完成”

用户感知最强的是：

```text
我说完 -> Echo 什么时候开始回应
```

因此第一段回复应该尽快进入音频队列；完整回复、数据库持久化和 APP 同步可以在后台继续完成。

### 3.3 每一步都可回滚

所有新行为都用配置开关控制，不直接替换 APP 默认链路：

```text
DEVICE_LLM_ENABLED=false       回退到现有模型
DEVICE_STREAMING_ENABLED=false 回退到完整音频模式
DEVICE_REALTIME_ASR_ENABLED=false 回退到一次性 ASR
```

## 4. 第一阶段：低风险优化

这一阶段不改变设备协议，不要求重新烧录固件，主要改 Echo Backend 配置和调用策略。

### 4.1 保持统一模型并增加设备交付配置

设备继续复用现有 `OPENAI_BASE_URL`、`OPENAI_API_KEY` 和 `LLM_MODEL`。只增加设备交付相关配置：

```dotenv
ECHO_DEVICE_AUTO_SILENCE_MS=650
ECHO_DEVICE_AUTO_MINIMUM_SPEECH_MS=180
ECHO_DEVICE_AUTO_MAXIMUM_SPEECH_MS=30000
ECHO_DEVICE_STREAMING_ENABLED=false
ECHO_DEVICE_TTS_CHUNK_MAX_CHARS=18
```

实际 API Key 仍使用服务器已有的密钥管理方式，不写入代码和 Git。

### 4.2 机器人通话使用短回答约束

机器人语音不适合每次回答很长。建议只对 `conversation_mode=call` 增加约束：

```text
- 默认 1～2 句话
- 约 40～80 个汉字
- 先回答当前问题，不主动展开长解释
- 需要详细内容时，提示用户继续追问
```

APP 文字聊天保持现有长度，不受这个限制。

代码位置：

```text
Echo-backend/features/chat/infrastructure/context_builder.py
Echo-backend/features/chat/application/generate_reply.py
Echo-backend/features/chat/application/send_message.py
```

### 4.3 将静音端点从 800 ms 调到 600～650 ms

当前 `ECHO_DEVICE_AUTO_SILENCE_MS=800` 会在每轮结束时额外等待约 0.8 秒。

建议按以下顺序实机测试：

```text
650 ms -> 当前默认候选值
600 ms -> 只有在真机长句不截断时再测试
800 ms -> 如果用户自然停顿仍被截断时回退
```

合成中文长句已经证明 500 ms 会在逗号停顿处提前结束，因此不能只追求更短
端点等待。不要降到 300 ms，因为中文短句中停顿可能被误认为结束。

代码位置：

```text
Echo-backend/features/devices/infrastructure/endpoint_detector.py
Echo-backend/features/devices/interface/router.py
```

### 4.4 使用同一 DeepSeek 模型做流式与非流式 A/B

使用同一模型、同一套人格、记忆和历史上下文，分别测试：

```text
A 组：当前完整返回链路
B 组：DeepSeek 流式返回链路
```

目标是验证同一模型开始输出第一个自然短句的时间，并确保流式改造不改变人格质量和工具能力。

### 4.5 第一阶段预期

如果只做：

```text
VAD 500 ms
+ 语音回答限制
+ TTS 语速 1.08
```

在不改流式架构的情况下，预计可以把“开始播放”从约 4 秒降到约 2～2.5 秒。

## 5. 第二阶段：真正的流式语音回复

这是速度优化的核心阶段。

### 5.1 目标链路

```text
用户说完
  -> ASR 最终文字
  -> LLM 开始流式返回
  -> 收到第一个自然短句
  -> 立即启动 TTS
  -> TTS 音频流转 PCM/Opus
  -> 立即发送给 Bread Compact
  -> 后续文字和音频继续追加
  -> 完整回复结束后保存数据库并同步 APP
```

### 5.2 LLM 流式接口

当前 `OpenAICompatibleLLMProvider` 只有完整返回接口：

```text
chat_completion_message(...) -> ProviderAssistantMessage
```

新增接口：

```text
stream_chat_completion(...) -> AsyncIterator[LLMTextDelta]
```

每个增量只包含新文字，不立即触发 TTS。先交给句子分段器。

建议句子分段规则：

```text
遇到 。！？； 时立即提交
超过 18～24 个汉字且有自然停顿时提交
没有标点时最多等待 300 ms
最后一段在 LLM 结束时提交
```

不要一个字一个字地调用 TTS，否则请求数量、音频接缝和费用都会明显增加。

新增文件建议：

```text
Echo-backend/features/devices/application/sentence_chunker.py
Echo-backend/features/devices/application/stream_device_turn.py
```

### 5.3 TTS 流式接口

当前流程：

```text
完整文字 -> 完整 MP3 -> 保存文件 -> 重新读取 -> 全部转 Opus
```

目标流程：

```text
短句文字 -> TTS 音频块 -> 解码 -> Opus 编码 -> WebSocket 发送
```

优先顺序：

1. 先保留 CosyVoice，利用现有流式回调，打通“边收边转”的路径。
2. 如果首包仍然超过目标，再测试 `qwen3-tts-flash-realtime`。
3. 新 TTS 必须重新评测中文自然度、声音一致性和音频稳定性。

不建议第一步就更换 TTS，因为当前主要浪费发生在后端等待完整音频，而不是 API 完全没有流式能力。

### 5.4 Opus 转码策略

设备下行协议是 24 kHz、单声道、60 ms Opus 包。流式转码需要：

```text
TTS 音频块
  -> 有界 PCM 缓冲区
  -> 每 60 ms 取一帧
  -> Opus 编码
  -> WebSocket 二进制发送
```

必须使用有界队列，避免网络或设备播放变慢时无限占用内存。

建议新增配置：

```dotenv
DEVICE_AUDIO_QUEUE_MAX_PACKETS=40
DEVICE_TTS_FIRST_SENTENCE_MAX_CHARS=24
DEVICE_PLAYBACK_START_DELAY_MS=60
```

### 5.5 持久化和 APP 同步

不能因为流式播放而提前把半句话写入正式聊天记录。正确顺序是：

```text
用户 ASR 文字：确认识别后立即或本轮开始时保存
Echo 完整文字：LLM 完成后保存
TTS 播放：与数据库保存解耦
APP：完整消息保存后发送 chat.sync
```

如果播放中途断网：

```text
数据库仍保存完整文字
APP 仍能看到本轮对话
设备端停止当前音频
下一轮可以重新建立连接
```

## 6. 第三阶段：实时 ASR、长连接和自然交互

### 6.1 实时 ASR

一次性 ASR 当前已经足够快，但实时 ASR 可以在用户说话过程中持续上传并获得中间结果：

```text
用户说话同时识别
检测到最终停顿后只等待最后确认
减少“说完后再上传整段音频”的等待
```

这一步需要新的 WebSocket ASR 会话、取消处理和最终结果去重，复杂度高于第一阶段。

### 6.2 WebSocket 长连接

当前设备每次唤醒时重新进行 WebSocket/TLS 握手，约消耗 1 秒。

桌面机器人持续供电，后续可以考虑：

```text
开机后建立设备 WebSocket
空闲时保持连接
唤醒后直接进入 listening
心跳失败才重连
```

这主要优化“唤醒词到我在呢”的速度，不直接减少回答生成时间。

### 6.3 打断和回声

后续增加：

```text
播放时检测用户重新说话
立即停止当前 TTS
丢弃未播放音频
重新进入 ASR
```

这需要硬件回声消除或更可靠的播放参考信号。没有 AEC 前，不建议强行全双工，否则机器人会把自己的声音识别成用户输入。

### 6.4 本地确认音自然度

当前“我在呢，请说。”是本地固定音频，优点是零 API 延迟，缺点是重复播放会显得机械。

后续可以准备 3～5 个本地确认音：

```text
我在呢，请说。
嗯，我听着呢。
好呀，你说。
```

随机选择即可改善重复感，不应在每次唤醒时调用 TTS API。

## 7. 推荐模型策略

| 能力 | 当前方案 | 第一阶段建议 | 第二/三阶段候选 |
| --- | --- | --- | --- |
| APP LLM | DeepSeek | 保持不变 | 保持不变 |
| 机器人 LLM | DeepSeek | 保持同一模型 | 同一模型启用流式 |
| ASR | 腾讯一次性 ASR | 保持不变 | 腾讯实时 ASR |
| TTS | CosyVoice v3.5 Flash | 先流式化现有方案 | 测试 Qwen3-TTS Flash Realtime |
| 记忆/人格 | Echo Backend | 保持不变 | 保持不变 |

最终选择以 Echo 中文人格测试和实机首包时间为准。

## 8. 需要修改的代码边界

### 第一阶段

```text
Echo-backend/shared/config/settings.py
Echo-backend/features/devices/infrastructure/adapters.py
Echo-backend/features/chat/infrastructure/context_builder.py
Echo-backend/features/chat/application/generate_reply.py
Echo-backend/features/devices/interface/router.py
```

主要是配置分流、语音短回复和参数调优。

### 第二阶段

```text
Echo-backend/providers/llm_provider.py
Echo-backend/providers/tts_provider.py
Echo-backend/features/devices/application/stream_device_turn.py
Echo-backend/features/devices/application/sentence_chunker.py
Echo-backend/features/devices/interface/router.py
```

主要是流式 LLM、流式 TTS、Opus 有界队列和取消处理。

### 第三阶段

```text
Echo-backend/features/voice/*
Echo-backend/features/devices/interface/router.py
echo-device-firmware/main/protocols/*
echo-device-firmware/main/audio/*
```

可能涉及设备协议和固件，但不会在第一阶段提前改动。

## 9. 监控指标

每一轮设备对话必须记录以下时间点：

```text
device_wake_at
websocket_connected_at
speech_started_at
speech_ended_at
asr_final_at
llm_first_token_at
llm_first_sentence_at
tts_first_audio_at
device_first_packet_at
turn_persisted_at
```

核心指标：

```text
speech_end_to_asr_final_ms
asr_to_llm_first_token_ms
llm_first_sentence_to_tts_first_audio_ms
tts_first_audio_to_device_first_packet_ms
speech_end_to_device_first_audio_ms
speech_end_to_persisted_ms
```

没有这些指标时，只凭“感觉变快了”无法判断到底是模型、网络、VAD 还是播放器起效。

## 10. 验收标准

### 第一阶段验收

```text
1. APP 文字聊天行为不变
2. 机器人仍使用同一人格和记忆
3. ASR 正确率不能明显下降
4. 设备语音回复首包 P50 <= 2.5 秒（当前云 TTS 实测约 2.5 秒，需真机确认）
5. 连续 20 轮对话无明显截断
6. TTS 失败时文字消息仍保存到 APP
7. 所有参数可通过 .env 回滚
```

### 第二阶段验收

```text
1. 首个自然短句开始播放目标为 P50 <= 1.6 秒；在当前云 TTS 和同一 DeepSeek
   约束下，服务器实测约 2.4～2.6 秒，1.6 秒需要更快或本地 TTS 才能达成
2. 连续音频无明显卡顿
3. 取消、断线、重连不会卡死设备
4. 完整回复只保存一次
5. APP 只收到一组完整 voice_asr / voice_reply 消息
6. 设备端不需要重新烧录即可验证后端流式方案
```

### 第三阶段验收

```text
1. 唤醒词到确认音明显低于当前约 1 秒握手等待
2. 用户可在播放中打断
3. 机器人不会把自己的声音当成用户输入
4. 长连接断开后 5 秒内自动恢复
```

## 11. 回滚方案

任何优化都必须保留以下回滚路径：

```dotenv
DEVICE_LLM_ENABLED=false
DEVICE_STREAMING_ENABLED=false
DEVICE_REALTIME_ASR_ENABLED=false
ECHO_DEVICE_AUTO_SILENCE_MS=800
```

回滚只需要重建 `echo-backend` 容器，不需要重新烧录当前已经验收的 `0.1.3` 固件。

Git 提交建议拆分为：

```text
perf: add device latency instrumentation
perf: route device calls to low-latency model
perf: stream LLM sentence chunks to device TTS
perf: add realtime ASR session for devices
```

每个提交都应单独可回退。

## 12. 最终执行顺序

```text
第 1 步：增加时间指标，不改变行为
第 2 步：同一 DeepSeek 模型的完整返回/流式返回 A/B
第 3 步：VAD 调到 500 ms，限制语音回答长度
第 4 步：实机验证 20～30 轮人格、记忆和速度
第 5 步：LLM 流式文字 + 自然短句分段
第 6 步：CosyVoice 流式音频直接转 Opus
第 7 步：必要时测试 Qwen3-TTS Flash Realtime
第 8 步：实时 ASR、长连接、打断和 AEC
```

最重要的结论是：**第一步不是立即换掉所有 API，而是先把“等待完整结果”的串行结构改成可观测、可分流、可流式的结构。**

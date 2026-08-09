# Echo 每日来信 Agent 与 MiniMax 图片生成重构开发文档

## 0. 文档状态

- 状态：产品与技术方案已确认，待按阶段开发
- 确认日期：2026-08-09
- 适用范围：Echo 后端 Agent、每日来信 Worker、MiniMax 图片 Provider、COS 存储和 Flutter 来信页面
- 架构约束：遵守 `doc/Echo 后端架构与代码规范.md`
- 当前版本基础：Echo v1.0.7
- 本文只定义开发方案，不代表相关代码已经实现

## 1. 产品目标

每日来信不是对昨日聊天的机械摘要，也不是与聊天人格分离的一次普通 LLM 调用。

目标是让同一个 Echo 在第二天回看昨日交流后，写出一封具备以下特征的信：

1. 使用完整 Echo 官方人设、用户个性化配置和当前关系阶段。
2. 基于昨日真实对话、相关长期记忆和未结束话题，不虚构事实。
3. 不只复述事情，还表达 Echo 有依据的观察、判断、担心和更深入的想法。
4. 通过统一 Agent 编排完成内容生成和 MiniMax 图片工具调用。
5. 在用户本地时间 `07:45` 提前生成，在 `08:00` 正式发布。
6. 图片失败不阻塞文字来信，正文失败时不得发布半成品。
7. 来信不发送系统推送，用户在 APP 中自然发现未读来信。

一句话定义：

> 每日来信是 Echo 对昨日共同交流进行有依据的再次思考后，主动留下的一封独立内容。

## 2. 已确认的产品决策

| 项目 | 已确认方案 |
| --- | --- |
| Echo 人设 | 使用与聊天相同的完整官方人设、个性化配置和关系上下文 |
| Agent | 复用统一 Agent 核心，使用独立 `daily_letter` 任务模式 |
| 内容来源 | 昨日完整有效聊天、表情包语义、相关长期记忆、关系状态和 Echo 已表达过的观点 |
| 内容定位 | 不写流水账；包含事实回顾、情绪观察和 Echo 自己更深入的想法 |
| 正文长度 | 建议 `600～1000` 中文字；内容较少时允许自然缩短，不强行凑字 |
| 图片 | 每封信最多一张，默认尝试通过 MiniMax-image 生成 |
| 图片参考 | 使用 Echo 官方人物参考素材，保持人物一致性 |
| 图片存储 | 生成后上传腾讯云 COS，数据库只保存对象元数据和可访问 URL |
| API Key | 仅通过服务器环境变量提供，代码和仓库中保留空配置 |
| 生成时间 | 用户本地时间 `07:45` |
| 发布时间 | 用户本地时间 `08:00` |
| APP 设置 | 本阶段不提供来信开关、时区和发布时间设置页面 |
| 推送 | 不发送个推或系统通知，不写 `notification_outbox` |
| 无互动日期 | 不生成来信，保存 `skipped/no_interaction` 幂等记录 |
| 已发布内容 | 文字发布后不因迟到的图片任务反复变化 |

## 3. 当前实现与主要差距

### 3.1 当前实现

当前来信链路为：

```text
定时循环
  -> 发布时间到期
  -> 读取前一天最多 80 条 chat_messages
  -> 拼接 role/content，截断到 12000 字符
  -> 使用固定提示词直接调用全局 LLM Provider
  -> 第一行解析为标题，其余解析为正文
  -> 立即写入 daily_letters(status=ready)
  -> APP 拉取并展示
```

现有能力包括：

- 按用户时区计算前一个自然日。
- 同一用户、日期和 generation version 的唯一约束。
- 无用户消息时保存 `skipped`。
- 来信列表、详情、未读数量和已读状态。
- PostgreSQL 持久化，重新打开 APP 后仍可读取。

### 3.2 当前差距

1. 来信绕过 Agent，只进行一次固定提示词 LLM 调用。
2. 只写“你是 Echo”，没有完整人设、个性化配置和关系状态。
3. 不使用长期记忆，也不了解跨天延续的话题。
4. 不解析表情包语义，只读取消息文字字段。
5. 固定读取前 80 条消息并从尾部截断，可能遗漏当天较晚的重要交流。
6. `DAILY_LETTER_GENERATION_TIME` 已配置但未参与实际调度。
7. 生成和发布发生在同一时刻，没有 `ready_to_publish` 阶段。
8. LLM 输出依赖首行解析，没有结构化契约。
9. 图片生成开关存在，但没有接入来信实体、Agent、COS 或 APP。
10. APP 支持 `letter_ready` 路由，但后端来信链路不需要也不应创建推送通知。
11. Worker 没有持久化 claim、lease、有限重试和详细失败状态。
12. 缺少针对来信生成质量、幂等性和调度状态机的专门测试。

## 4. 用户体验

### 4.1 每日时间线

默认使用 `Asia/Shanghai`：

```text
前一天 00:00-23:59
  -> 累积真实聊天记录

当天 07:45
  -> 创建或领取来信生成任务
  -> 筛选昨日内容
  -> Agent 写信
  -> MiniMax 生成一张 Echo 插画
  -> 上传 COS
  -> 状态变为 ready_to_publish

当天 08:00
  -> 发布 Worker 将状态改为 ready
  -> APP 可读取并显示未读角标
  -> 不发送系统推送

用户打开信件
  -> 状态由 ready 变为 read
```

### 4.2 APP 发现方式

不使用推送时，APP 必须在以下时机刷新来信：

- 用户登录并进入主界面后。
- APP 从后台恢复到前台后。
- 用户进入来信页面时。
- 用户在来信页面主动下拉刷新时。

聊天页信封按钮继续显示未读数量。APP 长时间停留在前台时，可以在恢复焦点或重新进入页面时刷新，不需要常驻高频轮询。

### 4.3 来信展示

列表保持简洁：

- 日期
- 主题
- 两行摘要
- 未读状态
- 可选的小尺寸图片预览

详情页建议使用：

```text
主题
日期
Echo 插画（存在时）
完整正文
```

图片不存在时不显示空白占位框，正文布局自然上移。

## 5. 目标架构

### 5.1 总体数据流

```text
Generation Scheduler (07:45 local)
        |
        v
DailyLetterApplication
        |
        +--> LetterContextAssembler
        |      +--> Yesterday Chat Repository
        |      +--> Sticker Semantic Repository
        |      +--> Memory Public API
        |      +--> Relationship Public API
        |      +--> Assistant Persona Public API
        |
        v
Unified Agent Core
  conversation_mode=daily_letter
        |
        +--> DailyLetterAgentPolicy
        +--> DailyLetterToolRegistry
        +--> Structured Letter Output
        +--> generate_letter_image tool
                         |
                         v
                 MiniMaxImageProvider
                         |
                         v
                     COS Storage
        |
        v
daily_letters(status=ready_to_publish)
        |
        v
Publish Scheduler (08:00 local)
        |
        v
daily_letters(status=ready)
        |
        v
Letters API -> Flutter APP
```

### 5.2 模块边界

建议保持现有 feature-first 结构：

```text
features/
  agent/
    application/
      orchestrate.py                 # 从聊天专用编排中抽取通用 Agent 核心
    domain/
      policies.py                    # 按 conversation_mode 限制输出和工具

  letters/
    application/
      assemble_context.py
      generate_letter.py
      publish_letters.py
    domain/
      entities.py
      repositories.py
      services.py
      output_schema.py
    infrastructure/
      container.py
      postgres_repository.py
      minimax_image_provider.py
    interface/
      router.py
      schemas.py

shared/
  storage/
    cos_storage.py
```

约束：

- Agent 不直接访问 PostgreSQL。
- Agent 不直接拼 COS URL 或持有 COS 密钥。
- MiniMax Provider 只负责外部 API 协议，不负责来信业务规则。
- Letters Application 负责幂等、状态流转、失败降级和发布时间。
- Flutter 只读取已发布的 `ready/read` 来信。

## 6. 统一 Agent 设计

### 6.1 “统一”的含义

统一 Agent 不等于把 `/chat/messages` 接口伪装成定时任务，也不要求引入 LangGraph。

本期应从现有 `OrchestrateChatWithAgent` 中抽取可复用的编排核心，统一：

- Agent run 生命周期
- 模型多步调用
- Tool Registry 和 Tool Executor
- 工具数量、步骤和总超时限制
- 运行轨迹与失败记录
- 完整 Echo 人设构造方式

聊天和来信分别提供策略：

```text
AgentOrchestrator
  +-- ChatAgentPolicy
  +-- ProactiveChatAgentPolicy
  +-- DailyLetterAgentPolicy
```

不同策略决定：

- 可用工具
- 系统任务说明
- 输出格式
- 是否允许发表情包
- 是否允许联网、定时和时间工具
- 最终内容如何交给对应业务模块

### 6.2 `daily_letter` 模式输入

Agent 输入至少包含：

- `user_id`
- `local_date`
- `timezone`
- Echo 完整官方人设
- 用户个性化 Persona 配置
- 当前关系阶段及关系上下文
- 昨日证据化内容摘要
- 代表性原始消息片段
- 与昨日主题相关的长期记忆
- Echo 近期已经表达过的观点
- 当前来信 generation version

内部触发消息应明确这是来信任务，不把它伪装成用户消息，也不得保存进普通聊天记录。

### 6.3 来信模式工具白名单

允许：

- `retrieve_relevant_memories`：读取与昨日主题相关的长期记忆。
- `generate_letter_image`：根据结构化 image brief 生成一张插画并上传 COS。

默认关闭：

- `send_sticker`
- `create_chat_schedule`
- `list_chat_schedules`
- `cancel_chat_schedule`
- `get_current_time`
- `web_search`

昨日时间范围由应用层可靠计算，不需要模型调用时间工具。来信默认不引用外部实时事实，因此不允许联网搜索。

### 6.4 运行限制

- 单次来信最多一次成功图片工具调用。
- 图片工具失败后最多进行一次由应用层控制的有限重试。
- Agent 最大步骤和超时单独配置，避免挤占聊天 Worker。
- Agent 不允许通过工具创建新的主动聊天、提醒或表情包消息。
- 来信 Agent run 必须记录 `trigger_type=daily_letter` 和对应 `letter_id`。

## 7. 精良内容筛选

### 7.1 原则

信息丰富不等于把所有聊天原样塞进提示词。内容筛选需要同时满足：

1. 尽量覆盖当天真正重要的信息。
2. 保留对话的时间顺序和情绪变化。
3. 优先使用用户明确表达的事实。
4. 允许关联长期记忆，但不能让旧记忆压过当天内容。
5. 保留证据 ID，支持调试和真实性审查。
6. 不删除、不改写原始聊天记录。

### 7.2 数据来源

读取昨日本地自然日内的：

- 用户文字消息
- Echo 文字回复
- 用户和 Echo 的表情包语义标签
- 消息时间和连续会话边界
- Agent 工具最终可见结果，但不读取内部 chain-of-thought
- 与昨日主题语义相关的长期记忆
- 当前关系阶段和最近关系变化

排除：

- 已删除或非 active 消息
- 系统提示词
- 工具内部参数和敏感日志
- ASR 临时文件、TTS 文件地址等实现信息
- 空白表情包消息的原始空文本

### 7.3 两阶段筛选

#### 阶段 A：确定性预处理

应用层完成：

- 按本地日期分页读取全部有效消息，不再固定只取前 80 条。
- 按时间间隔划分连续会话，例如间隔超过 30 分钟视为新的 session。
- 将表情包附件转换成简短语义标签，不加入冗长描述。
- 标记用户目标、情绪词、选择、承诺、疑问和未完成话题的候选消息。
- 为每条候选保留 message ID、时间、角色和内容类型。

#### 阶段 B：证据化 Daily Brief

由上下文分析模型生成结构化 brief：

```json
{
  "sessions": [
    {
      "time_range": "22:20-23:10",
      "topics": ["继续工作", "休息提醒"],
      "user_state": ["有动力", "可能忽视休息"],
      "open_threads": ["明天是否继续当前任务"],
      "evidence_message_ids": [174, 178, 182]
    }
  ],
  "important_facts": [],
  "emotional_shifts": [],
  "echo_already_said": [],
  "candidate_reflections": [],
  "memory_queries": []
}
```

Daily Brief 必须引用 message IDs。无法找到证据的内容不得进入事实字段。

### 7.4 上下文预算

建议顺序：

1. 完整 Echo 人设和真实性规则。
2. Daily Brief。
3. 最重要会话的代表性原文。
4. 与主题最相关的长期记忆。
5. 关系状态。
6. 其他补充片段。

当内容过长时，减少低优先级原文，不截断最重要会话的结尾。不得再次出现“保留最早内容、丢失当天晚间内容”的固定头部截断问题。

## 8. 来信表达规范

### 8.1 内容目标

每封信应至少完成其中三项：

- 记住一个真实而具体的细节。
- 看见用户当时的情绪或行为变化。
- 回应一个仍未结束的话题。
- 把当日事情与用户长期关注的问题连接起来。
- 表达 Echo 有依据的个人看法。
- 留下一句能让用户继续思考的话。

### 8.2 推荐结构

结构不写死为模板，但通常包含：

1. **自然开场**：从一个具体细节进入，不使用“根据昨天的聊天”。
2. **重点回应**：选择一到三个核心话题，不逐条复述。
3. **观察与理解**：说明 Echo 从交流中看到了什么。
4. **Echo 的想法**：给出更深层、有限且诚实的判断。
5. **自然收束**：可以留下问题，也可以只表达陪伴和立场。

### 8.3 Echo 自己的想法

最后一段不能停留在事件总结。允许 Echo 表达：

- “我觉得……”
- “我有一点担心……”
- “也许你真正犹豫的不是……”
- “如果把这两件事放在一起看……”
- “我更愿意相信……”

但必须遵守：

- 判断有昨日对话或长期记忆作为依据。
- 推测必须使用有分寸的语言，不把猜测写成事实。
- 不宣称 Echo 昨晚一直在思考、等待或进行现实活动。
- 可以写“在写这封信时，我又想到”，不能虚构离线生活。
- 不强行给建议，也不每封信都以问题结尾。

### 8.4 避免的表达

- 流水账式“你先说了 A，然后做了 B，后来又说了 C”。
- 空泛的“你已经很棒了，一切都会好的”。
- 重复 Echo 昨天已经说过的相同句子。
- 将长期记忆中的旧事实伪装成昨天发生的事情。
- 无依据分析用户人格、疾病或心理状态。
- 过度亲密、占有或制造依赖的表达。
- 强制要求用户回复或打卡。

## 9. 结构化输出契约

Agent 最终输出必须通过 Schema 校验，不能继续依赖“首行标题”的字符串约定。

建议内部结构：

```json
{
  "subject": "信件主题",
  "content": "完整正文",
  "mood": "quiet_encouragement",
  "core_topics": ["工作节奏", "休息边界"],
  "reflection": "Echo 最核心的个人观察",
  "closing_style": "statement",
  "image_brief": {
    "emotion": "安静、关心但不说教",
    "scene": "清晨窗边的 Echo 整理桌面上的纸张",
    "visual_symbols": ["晨光", "未喝完的水", "合上的笔记本"],
    "avoid": ["文字", "水印", "真实用户形象"]
  },
  "source_message_ids": [174, 178, 182],
  "source_memory_ids": ["memory_xxx"]
}
```

校验规则：

- `subject` 必填，建议不超过 40 个中文字符。
- `content` 必填，最大 4000 字符。
- `reflection` 必填，确保存在 Echo 自己的想法。
- `source_message_ids` 至少包含一个用户消息 ID。
- `image_brief` 不得包含用户真实姓名、电话、地址或聊天原文。
- Schema 失败时允许一次仅修复格式的模型重试，不重新调用工具。

## 10. MiniMax 图片生成

### 10.1 Provider 契约

在 Letters Domain 定义供应商无关接口：

```python
class LetterImageGenerator(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        reference_images: tuple[str, ...],
        aspect_ratio: str,
    ) -> GeneratedImage: ...
```

MiniMax 适配器负责：

- 构造官方 API 请求。
- 处理鉴权、超时和响应格式。
- 下载或解码生成图片。
- 校验 MIME、尺寸和最大字节数。
- 返回原始图片 bytes 和生成元数据。

具体 API URL、模型名称、参考图字段和返回结构在开发时以 MiniMax 当期官方文档为准，不在业务层硬编码。

### 10.2 环境变量

仓库只提供空配置：

```dotenv
LETTER_IMAGE_GENERATION_ENABLED=false

MINIMAX_IMAGE_API_KEY=
MINIMAX_IMAGE_BASE_URL=
MINIMAX_IMAGE_MODEL=
MINIMAX_IMAGE_TIMEOUT_SECONDS=120

LETTER_IMAGE_ASPECT_RATIO=4:3
LETTER_IMAGE_MAX_ATTEMPTS=2
LETTER_IMAGE_MAX_BYTES=10485760
LETTER_IMAGE_REFERENCE_ASSET=
```

约束：

- API Key 只填写在服务器 `/opt/echo/app/Echo-backend/.env`。
- 不提交到 Git，不进入 Flutter，不写入日志。
- 未填写 Key 或开关关闭时，来信正常生成纯文字。

### 10.3 Echo 人物一致性

来信图片使用 Echo 官方人物素材作为参考，不使用用户私人照片。

参考素材应：

- 选择人物外观最稳定、无遮挡的官方图。
- 上传到后端可控位置或 COS 私有对象。
- 由服务端读取并传给 MiniMax。
- 版本化，例如 `echo-character-reference-v1`。

图片提示词由系统人物描述、Agent image brief 和统一风格约束组合，Agent 不直接覆盖人物核心特征。

### 10.4 图片规则

- 每封信最多一张图片。
- 默认请求模型支持的最接近 `4:3` 横向规格。
- 图片表现 Echo 和信件情绪，不复刻具体用户形象。
- 不生成文字、Logo、水印、APP 界面或聊天截图。
- 不把完整聊天记录发送给图片 Provider。
- 敏感话题使用含蓄场景或纯情绪插画，不直接描绘隐私事实。

### 10.5 COS 存储

推荐对象路径：

```text
echo/letters/{user_hash}/{local_date}/{letter_id}.webp
```

上传前执行：

- 图片格式校验
- 最大尺寸限制
- 必要时转为 WebP
- 内容哈希计算
- 对象 key 幂等检查

数据库保存：

- `image_storage_key`
- `image_url` 或受控读取信息
- `image_content_type`
- `image_width`
- `image_height`
- `image_byte_size`
- `image_provider`
- `image_model`
- `image_reference_version`
- `image_generation_status`
- `image_failure_code`

### 10.6 失败降级

```text
正文成功 + 图片成功
  -> ready_to_publish，发布图文来信

正文成功 + 图片失败/超时
  -> 记录 image_failure_code
  -> ready_to_publish，发布纯文字来信

正文失败
  -> 有限重试
  -> 仍失败则 status=failed，不发布
```

图片在 `08:00` 发布截止点之后才完成时，本阶段不再修改已发布来信，避免用户打开前后内容变化。

## 11. 生成与发布状态机

### 11.1 状态定义

沿用现有 APP 对 `ready/read` 的理解，增加内部状态：

```text
pending
  -> generating
  -> ready_to_publish
  -> ready
  -> read

异常分支：
  -> skipped
  -> retry_wait
  -> failed
```

含义：

| 状态 | 含义 | APP 可见 |
| --- | --- | --- |
| `pending` | 已创建待生成 | 否 |
| `generating` | Worker 已领取 | 否 |
| `retry_wait` | 正文生成等待重试 | 否 |
| `ready_to_publish` | 正文已完成，图片成功或已降级 | 否 |
| `ready` | 已发布且未读 | 是 |
| `read` | 已发布且已读 | 是 |
| `skipped` | 当日无有效互动 | 否 |
| `failed` | 有限重试后仍无法生成正文 | 否 |

### 11.2 生成 Worker

每分钟扫描到达用户本地 `07:45` 的目标日期：

1. 以 `user_id + local_date + generation_version` 创建或获取任务行。
2. 使用 `FOR UPDATE SKIP LOCKED` claim。
3. 设置 lease，防止进程中断造成永久 `generating`。
4. 构造 Daily Brief 和完整 Agent 上下文。
5. 执行 `daily_letter` Agent。
6. 校验结构化输出并保存正文。
7. 开关允许时生成图片并上传 COS。
8. 状态改为 `ready_to_publish`。

### 11.3 发布 Worker

每分钟扫描：

```text
status=ready_to_publish
AND publish_at <= NOW()
```

发布操作只负责：

- 状态改为 `ready`。
- 写入 `published_at`。
- 保持幂等。

明确不执行：

- 不重新调用 LLM。
- 不等待图片。
- 不创建聊天消息。
- 不写 `notification_outbox`。
- 不发送个推。

### 11.4 重试建议

正文生成失败：

- 第一次：`07:45`
- 第二次：约 `07:50`
- 第三次：约 `07:57`
- `08:00` 仍失败则标记 `failed`

图片生成：

- 最多两次尝试。
- 单次超时默认 120 秒。
- 图片失败不增加正文尝试次数。

实际退避时间通过配置控制，测试中使用可注入 Clock，不依赖真实等待。

## 12. 数据库调整

在现有 `daily_letters` 上扩展，避免为了 v1 额外拆出复杂任务表：

```text
agent_run_id
context_version
context_snapshot JSONB
source_memory_ids JSONB
reflection TEXT
mood VARCHAR
image_brief JSONB
image_storage_key TEXT
image_url TEXT
image_content_type VARCHAR
image_width INTEGER
image_height INTEGER
image_byte_size BIGINT
image_provider VARCHAR
image_model VARCHAR
image_reference_version VARCHAR
image_generation_status VARCHAR
image_failure_code TEXT
generation_attempt_count INTEGER
next_attempt_at TIMESTAMPTZ
lease_expires_at TIMESTAMPTZ
publish_at TIMESTAMPTZ
```

保留现有字段：

- `source_message_ids`
- `generation_version`
- `scheduled_at`
- `generated_at`
- `published_at`
- `read_at`
- `failure_code`

新增或确认索引：

```text
UNIQUE(user_id, local_date, generation_version)
INDEX(status, next_attempt_at)
INDEX(status, publish_at)
INDEX(user_id, published_at DESC)
```

数据库迁移必须兼容现有 `ready/read/skipped` 数据，不重写或删除已经生成的旧来信。

## 13. API 契约

保留现有接口：

```text
GET  /letters
GET  /letters/latest
GET  /letters/{letter_id}
POST /letters/{letter_id}/read
GET  /letters/preferences
PUT  /letters/preferences
```

本阶段 Flutter 不展示 preferences 设置页，但后端接口可保留，供未来使用和内部验证。

来信响应增加可空图片字段：

```json
{
  "letter_id": "letter_xxx",
  "local_date": "2026-08-08",
  "timezone": "Asia/Shanghai",
  "status": "ready",
  "subject": "慢一点也算往前走",
  "content": "……",
  "image_url": "https://...",
  "image_width": 1280,
  "image_height": 960,
  "published_at": "2026-08-09T00:00:00Z",
  "read_at": null
}
```

安全约束：

- 用户只能访问自己的来信。
- API 不返回 prompt、context snapshot、memory IDs、COS storage key 或 Provider 错误详情。
- `skipped/failed/ready_to_publish` 不出现在用户列表中。

## 14. Flutter 调整

### 14.1 数据模型

`DailyLetter` 增加可空字段：

- `imageUrl`
- `imageWidth`
- `imageHeight`

旧来信没有图片时必须正常解析。

### 14.2 页面行为

- 列表继续请求最近 50 封，后续可再改 cursor 分页。
- 详情页使用缓存网络图片组件。
- 图片加载失败时只隐藏图片，不影响正文。
- 打开详情后继续在服务端标记已读。
- APP 启动、登录恢复和前台 resume 时刷新未读数量。

### 14.3 本阶段不做

- 不增加来信时间设置页。
- 不增加图片重试按钮。
- 不发送本地通知或系统推送。
- 不允许用户编辑或重新生成来信。

## 15. 配置建议

```dotenv
DAILY_LETTER_ENABLED=true
DAILY_LETTER_GENERATION_TIME=07:45
DAILY_LETTER_PUBLISH_TIME=08:00
DAILY_LETTER_WORKER_INTERVAL_SECONDS=60
DAILY_LETTER_GENERATION_VERSION=letter-agent-v2
DAILY_LETTER_MAX_ATTEMPTS=3
DAILY_LETTER_AGENT_TIMEOUT_SECONDS=120
DAILY_LETTER_TARGET_MIN_CHARS=600
DAILY_LETTER_TARGET_MAX_CHARS=1000

LETTER_IMAGE_GENERATION_ENABLED=false
MINIMAX_IMAGE_API_KEY=
MINIMAX_IMAGE_BASE_URL=
MINIMAX_IMAGE_MODEL=
MINIMAX_IMAGE_TIMEOUT_SECONDS=120
LETTER_IMAGE_ASPECT_RATIO=4:3
LETTER_IMAGE_MAX_ATTEMPTS=2
LETTER_IMAGE_MAX_BYTES=10485760
LETTER_IMAGE_REFERENCE_ASSET=
```

配置校验：

- `generation_time` 必须早于 `publish_time`。
- 两者必须是合法 `HH:mm`。
- 图片开关打开时，MiniMax Key、URL、Model 和参考素材必须完整。
- 配置不完整时启动不泄露密钥；可以禁用图片并输出脱敏告警。

## 16. 真实性、隐私与安全

### 16.1 真实性

- 所有昨日事实必须能追溯到 source message。
- 长期记忆只能用于关联和理解，不能伪装成昨日事实。
- Echo 的观点可以是推测，但语言必须表达不确定性。
- 禁止虚构 Echo 的离线活动、身体体验和现实环境。

### 16.2 隐私

- 不把完整聊天记录发送给 MiniMax 图片接口。
- image brief 必须移除姓名、电话、地址、账号和聊天原文。
- Agent 日志只记录消息数量、source ID 数量、耗时和状态，不记录正文全文。
- MiniMax API Key、COS 密钥和签名 URL 不写日志。

### 16.3 内容安全

- 图片生成前执行 prompt 安全检查。
- Provider 返回内容需要进行格式和大小校验。
- 涉及敏感经历时优先生成抽象、安静的 Echo 场景。
- 图片生成失败时不向用户暴露 Provider 错误。

## 17. 可观测性

每轮生成至少记录：

```text
letter_id
user_id_hash
local_date
generation_version
context_message_count
context_memory_count
daily_brief_duration_ms
agent_run_id
agent_duration_ms
agent_model_steps
image_enabled
image_attempt_count
image_duration_ms
image_status
cos_upload_duration_ms
final_status
failure_code
```

禁止记录：

- API Key
- 完整正文
- 完整聊天上下文
- 完整图片 prompt 中可能包含的个人信息

建议指标：

- 到期用户数
- ready_to_publish 数量
- 准时发布率
- 纯文字降级率
- 正文生成失败率
- MiniMax 超时率
- 平均 Agent 耗时
- 平均图片生成耗时
- 每封信平均 LLM 和图片成本

## 18. 测试计划

### 18.1 后端单元测试

- 正确计算 `Asia/Shanghai` 前一自然日。
- `07:45` 前不创建任务，之后创建一次。
- 同一用户、日期、version 不重复生成。
- 无用户消息生成 `skipped/no_interaction`。
- 全日分页读取，不丢失晚间消息。
- 表情包只进入语义标签，不带冗长描述。
- Daily Brief 中事实均带 source IDs。
- 长期记忆不会被标成昨日事实。
- Agent 使用 `daily_letter` 工具白名单。
- 结构化输出失败只进行一次格式修复。
- `reflection` 为空时校验失败。
- 图片成功后上传 COS 并保存元数据。
- 图片失败时正文仍进入 `ready_to_publish`。
- 正文失败后有限重试，耗尽后进入 `failed`。
- `08:00` 只发布 `ready_to_publish`。
- 发布过程不写 `notification_outbox`。
- 多 Worker 并发 claim 不会重复调用 Agent。
- 旧 `ready/read` 来信仍可正常读取。

### 18.2 Provider 合约测试

- MiniMax 鉴权请求不泄露 Key。
- 正确处理成功、超时、限流、无效响应和空图片。
- 参考图请求符合当期 MiniMax 官方协议。
- 返回图片 MIME、字节数和尺寸得到验证。
- COS 上传 key 幂等，失败可降级。

### 18.3 Flutter 测试

- 无图片旧来信正常展示。
- 有图片来信显示图片和正文。
- 图片加载失败不遮挡正文。
- 未读角标在启动、resume、刷新和已读后正确更新。
- 不出现通知权限请求或来信系统通知。
- 详情打开后标记已读失败时可重试。

### 18.4 质量样本评估

建立至少 20 组脱敏对话样本，人工评分：

- 事实准确性
- 重要信息覆盖率
- 是否像 Echo
- 是否只是流水账
- 是否包含有依据的深入想法
- 是否重复昨日回复
- 是否过度亲密或说教
- 图片是否保持 Echo 人物一致性
- 图文情绪是否匹配

任何出现虚构事实、隐私泄露或明显人物错位的样本视为阻断问题。

## 19. 开发阶段

### Phase 1：来信状态机与调度拆分

- 激活 `DAILY_LETTER_GENERATION_TIME`。
- 增加 `pending/generating/retry_wait/ready_to_publish` 状态。
- 实现 claim、lease、有限重试和独立发布 Worker。
- 保持现有纯文字生成可运行。

完成标准：生成与发布时间真正分离，旧来信兼容。

### Phase 2：统一 Agent 与完整 Echo 上下文

- 抽取通用 Agent orchestration core。
- 增加 `DailyLetterAgentPolicy`。
- 实现 LetterContextAssembler 和证据化 Daily Brief。
- 注入完整人设、个性化、关系和相关记忆。
- 改为结构化来信输出。

完成标准：来信不再直接调用固定提示词 LLM，Agent run 可追踪。

### Phase 3：MiniMax 图片与 COS

- 增加 MiniMax Provider 适配器。
- 配置 Echo 官方参考素材。
- 注册 `generate_letter_image` 工具。
- 生成图片、校验并上传 COS。
- 实现图片失败的纯文字降级。

完成标准：填写 Key 并开启配置后可以稳定生成一张 Echo 插画。

### Phase 4：Flutter 图文来信

- 扩展 API DTO 和 Flutter 模型。
- 详情页展示图片。
- 增加启动、resume 和进入页面刷新。
- 验证无推送时未读角标仍能及时更新。

完成标准：新旧来信均可查看，不依赖系统推送。

### Phase 5：质量与生产验收

- 补齐单元、集成和架构测试。
- 使用脱敏样本评估内容质量。
- 填写 MiniMax 配置并进行受控 smoke test。
- 在生产环境观察一轮 `07:45 -> 08:00` 完整时间线。

## 20. 验收标准

功能验收：

- 每个有有效互动的用户每天最多生成一封来信。
- `07:45` 开始生成，`08:00` 前不对 APP 可见。
- `08:00` 后准时变为未读来信。
- 没有互动时不生成空泛来信。
- 来信正文使用完整 Echo 人设和相关长期记忆。
- 正文包含清晰的 Echo 个人观察或想法，而非只复述事件。
- 每封信最多一张 MiniMax 图片。
- 图片失败时仍按时发布文字。
- 不产生任何来信系统推送或 notification outbox 记录。
- APP 重启、恢复前台和进入来信页后能看到最新未读状态。

工程验收：

- `python -B scripts/check_architecture.py` 通过。
- Python lint 通过。
- 后端全部测试通过。
- `flutter analyze` 为 0 issues。
- Flutter 全部测试通过。
- 密钥扫描确认 MiniMax 和 COS 密钥未进入 Git。
- 生产日志能区分生成、图片、COS 和发布四个阶段。

质量验收：

- 不虚构用户未表达的事实。
- 不虚构 Echo 的离线现实活动。
- 不把信写成昨日聊天流水账。
- 不总是使用相同开头、相同结尾或固定安慰模板。
- 最后一部分能表达有依据、有分寸且可继续交流的 Echo 想法。
- 图片人物外观和 Echo 官方素材保持可接受的一致性。

## 21. 明确非目标

本阶段不实现：

- 来信系统推送。
- APP 来信时间设置页面。
- 用户手动要求重新生成同一封信。
- 一封信生成多张图片。
- 将来信插入普通聊天消息流。
- 在来信中发送表情包。
- 让 Agent 联网搜索并写入外部新闻。
- 删除或用摘要替换原始聊天历史。
- 为了统一 Agent 而引入新的编排框架或独立微服务。

## 22. 最终开发原则

1. 同一个 Echo：聊天、主动消息和来信共享人格与关系，不产生多个互相矛盾的 Echo。
2. 证据优先：先确认昨天真实发生了什么，再表达看法。
3. 思考而非复述：来信必须比聊天记录本身多一层有依据的理解。
4. 文字优先：图片增强体验，但不控制来信是否准时发布。
5. 生成与发布分离：耗时任务提前完成，用户只看到稳定成品。
6. 无推送也可发现：依靠 APP 生命周期刷新和未读角标完成体验闭环。
7. 原始记录不丢失：摘要、Daily Brief 和来信都只是派生数据。

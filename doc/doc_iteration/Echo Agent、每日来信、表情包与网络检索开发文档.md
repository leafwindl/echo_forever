# Echo Agent、每日来信、表情包与网络检索开发文档

## 0. 文档状态

- 状态：开发设计稿
- 适用范围：Echo 后端、微信小程序、后台任务与外部 Provider
- 架构约束：遵守 `doc/Echo 后端架构与代码规范.md`
- 本期目标：引入可控 Agent 编排能力，落地时间工具、网络检索、每日来信和表情包系统
- 非目标：本期不把 Agent 拆成独立微服务，不实现无限自主运行，不允许 Agent 绕过业务模块直接访问数据库

## 1. 产品目标

Echo 不再只是“拼装上下文后调用一次 LLM”，而是可以在安全、可追踪的边界内：

1. 判断当前任务是否需要工具。
2. 获取可靠的当前时间和相对时间信息。
3. 在需要实时或外部事实时执行网络检索。
4. 从表情包库选择合适的表情包，或异步生成新表情包。
5. 保存用户主动上传并授权保存的表情包。
6. 按用户本地时区，在固定时间生成并发布一封回顾前一日的 Echo 来信。

这些能力必须继续服从 Echo Persona、关系阶段、用户边界、内容安全和真实性边界。Agent 不是新的角色，也不拥有独立人格。

## 2. 已对齐的产品定义

### 2.1 Agent 定位

Echo Agent 是决策与编排层，负责：

- 理解本轮目标。
- 判断是否调用工具。
- 选择工具和参数。
- 读取工具结果并形成下一步动作。
- 在有限步骤内生成最终回复或业务命令。
- 记录运行轨迹、耗时和失败原因。

Agent 不负责：

- 直接写聊天、信件、表情包或记忆数据库。
- 决定各业务实体的数据规则。
- 绕过用户权限、内容审核或任务幂等约束。
- 在没有事件触发时无限循环或自主运行。

### 2.2 每日来信

每日来信是独立内容，不属于聊天消息流。

- 按用户时区划分自然日。
- v1 默认在用户本地时间次日 `08:00` 发布，回顾前一个自然日。
- 发布时间必须通过配置和用户设置控制，禁止硬编码。
- 前一日没有有效互动时默认不生成。
- 同一用户、同一回顾日期最多一封，必须幂等。
- 信件显示在人物区域的独立信件入口，不插入聊天气泡。
- 未读信件通过人物区域图标角标提示。

信件表达 Echo 对共同经历的整理、观察与有限想法，但不得虚构 Echo 离线期间真实做过某事、持续等待用户或拥有现实生活。

### 2.3 表情包

表情包系统同时支持：

- Echo 从已有表情包库检索并发送。
- Echo 根据明确语境创建异步生成任务，生成成功后加入库并发送或留存。
- 用户上传表情包，并明确选择是否允许 Echo 保存。
- 用户管理自己上传的表情包。
- 表情包带结构化语义标签，Agent 只通过公开工具检索和选择。

Echo 不应每轮都发表情包。表情包是表达增强，不是回复的固定组成部分。

### 2.4 网络检索

网络检索允许 Agent 自动调用，但仅限以下场景：

- 用户明确要求搜索、查找、验证或获取最新信息。
- 当前问题包含明显时效性事实，模型内部知识不足以可靠回答。
- 用户已授权的业务任务需要外部公开信息。

普通闲聊、情绪回应、关系交流和已由当前上下文充分回答的问题不得为了“显得聪明”而搜索。

## 3. 当前架构与目标架构

### 3.1 当前链路

```text
用户消息
  -> Context Builder
  -> 单次 LLM 调用
  -> 对话规则检查/重写
  -> 保存 Chat Turn
  -> 异步摘要、记忆、关系、语音
```

当前已经具备 Persona、关系、记忆、语音和后台任务，但没有标准 Tool、Agent Run、Tool Call 和多步执行契约。

### 3.2 目标链路

```text
用户消息 / 定时事件 / 生成任务完成事件
                    |
                    v
             Agent Application
                    |
       +------------+-------------+
       |            |             |
       v            v             v
   LLM 决策      Tool Registry   Agent Policy
       |            |             |
       +------ 有限步骤循环 -------+
                    |
          Final Reply / Domain Command
                    |
       +------------+-------------+
       |            |             |
       v            v             v
      Chat        Letters       Stickers
```

## 4. 模块组织

第一阶段在现有后端内部新增独立 Feature，不拆微服务：

```text
features/
  agent/
    domain/
      entities.py
      policies.py
      services.py
      repositories.py
    application/
      run_agent_turn.py
      execute_agent_task.py
    infrastructure/
      llm_tool_runner.py
      tool_registry.py
      adapters.py
      postgres_repository.py
      container.py
    public.py

  letters/
    domain/
    application/
    interface/
    infrastructure/
    public.py

  stickers/
    domain/
    application/
    interface/
    infrastructure/
    public.py

providers/
  web_search_provider.py
  image_generation_provider.py
  object_storage_provider.py
```

### 4.1 依赖方向

```text
Interface -> Application -> Domain
Infrastructure -> Domain Protocol
Bootstrap/Container 负责装配
```

跨 Feature 规则：

- Agent Application 只依赖 Agent Domain Protocol。
- Agent Infrastructure Adapter 可以调用 `chat.public`、`memory.public`、`letters.public`、`stickers.public` 的稳定入口。
- Agent 禁止 import 其它 Feature 的 Infrastructure、Repository 或 Interface。
- Letters、Stickers、Chat 不反向依赖 Agent 内部实现。
- 外部搜索、图片生成、对象存储必须通过 Provider Protocol 和注册表接入。

### 4.2 为什么暂时不拆微服务

- 当前用户量和工具数量尚不足以抵消分布式部署成本。
- Agent 与 Chat、Memory、Relationship 之间存在低延迟协作需求。
- 先通过 Feature 和 Protocol 建立清晰边界，未来可把 Agent Worker 独立部署而不改变业务契约。
- 图片生成和定时任务可以先作为同一代码库中的独立 Worker 进程运行，不要求独立服务仓库。

满足以下任一条件后再评估拆服务：

- Agent 任务吞吐与 HTTP 服务资源明显冲突。
- 图片生成、网络检索需要独立扩缩容。
- Agent Run 需要独立队列、长时间运行或多租户隔离。
- 单体部署已无法满足故障隔离和发布节奏。

## 5. Agent Domain 设计

### 5.1 核心实体

#### AgentRun

```text
AgentRun
- run_id
- user_id
- trigger_type: chat | scheduled_letter | sticker_generation | system_event
- trigger_id
- status: pending | running | waiting_tool | completed | failed | cancelled
- objective
- step_count
- max_steps
- started_at
- finished_at
- error_code
```

#### ToolCall

```text
ToolCall
- tool_call_id
- run_id
- tool_name
- status: pending | running | completed | failed
- input_summary
- output_summary
- started_at
- finished_at
- duration_ms
- error_code
```

日志和数据库均不得保存完整敏感输入；调试所需详细载荷应加密、限期保存或只保存哈希与摘要。

### 5.2 Tool 契约

Domain 定义统一协议：

```python
class AgentTool(Protocol):
    @property
    def specification(self) -> ToolSpecification: ...

    async def execute(
        self,
        context: ToolExecutionContext,
        arguments: ToolArguments,
    ) -> ToolResult: ...
```

`ToolSpecification` 至少包含：

- `name`
- `description`
- `input_schema`
- `result_schema`
- `risk_level`
- `timeout_seconds`
- `requires_user_confirmation`
- `is_idempotent`

禁止把任意 Python 函数自动暴露给模型。只有注册表白名单中的工具可用。

### 5.3 工具风险分级

| 等级 | 示例 | 策略 |
|---|---|---|
| read | 获取时间、搜索公开网页、检索记忆、查询表情包 | 可按策略自动执行 |
| create_internal | 创建信件草稿、创建表情包生成任务 | 需幂等键和内容审核 |
| send | 发送表情包、发布信件 | 必须经过渠道和频率策略 |
| destructive | 删除表情包、删除信件、清空数据 | 必须由用户明确操作，不允许 Agent 自主调用 |

### 5.4 Agent 执行循环

v1 采用有限 Tool Loop：

```text
1. 创建 AgentRun
2. 加载当前目标、Persona、关系、必要上下文和允许工具
3. LLM 返回 final_response 或一个 tool_call
4. Policy 校验工具、参数、风险、调用次数和超时
5. 执行工具并把结构化结果加入 working context
6. 回到步骤 3
7. 达到完成条件或最大步骤后结束
```

默认限制建议：

- 每个聊天 Run 最多 4 次工具调用。
- 每个 Run 最多 6 个决策步骤。
- 网络检索最多 2 次。
- 同一 Run 不允许重复执行相同参数的非幂等工具。
- 达到上限后返回基于已有结果的克制回复，不继续循环。
- 单工具超时和总 Run 超时均配置化。

### 5.5 Agent Policy

Policy 是纯 Domain 规则，至少包含：

- 当前 Trigger 允许哪些工具。
- 工具风险等级是否允许自动执行。
- 是否超过步骤、费用、频率或时间预算。
- 当前关系阶段是否允许某种主动表达。
- 当前用户是否关闭网络检索、表情包或每日来信。
- 结果是否需要内容安全审核。

LLM 可以建议动作，但不能覆盖 Policy。

## 6. 时间工具

### 6.1 工具列表

```text
get_current_time
- input: timezone
- output: local_datetime, local_date, weekday, utc_offset

calculate_time_difference
- input: start_datetime, end_datetime, timezone
- output: duration_seconds, human_readable_duration

resolve_relative_date
- input: expression, reference_datetime, timezone
- output: start_datetime, end_datetime, confidence
```

### 6.2 规则

- 用户时区来自受信任的用户设置；没有设置时使用产品默认时区并明确标记来源。
- Domain 不读取系统时间；通过 `Clock` Protocol 注入。
- 时间工具输出 ISO 8601 和 IANA timezone。
- “今天、昨天、明天”必须相对用户时区解释。
- LLM 不得自行猜测星期、日期或时差。
- 测试使用 Fake Clock，覆盖跨日、夏令时和 UTC 偏移边界。

## 7. 网络检索

### 7.1 Provider 契约

```python
class WebSearchProvider(Protocol):
    async def search(self, request: WebSearchRequest) -> WebSearchResult: ...
```

输入：

- query
- locale
- recency_days
- allowed_domains
- blocked_domains
- maximum_results
- safe_search

输出：

- results
- title
- canonical_url
- snippet
- published_at
- retrieved_at
- source_domain

### 7.2 Agent 工具

```text
search_web
- risk_level: read
- requires_user_confirmation: false
- timeout_seconds: configurable
- maximum_calls_per_run: 2
```

### 7.3 触发策略

应该检索：

- 用户明确要求搜索或验证。
- 新闻、价格、天气、政策、人物职位、产品版本等时效性信息。
- 当前答案需要外部来源才能可靠完成。

不应检索：

- 普通问候、闲聊和情绪陪伴。
- 仅依赖当前对话即可回答的关系问题。
- 为了延长对话而主动搜索用户没有询问的话题。

### 7.4 来源与安全

- 最终回复要区分工具事实和 Echo 的观点。
- 对事实性结果保留来源 URL 和检索时间。
- 前端文字聊天支持可点击来源；电话模式只口语化概括，来源保存在结构化响应中。
- 禁止访问内网 IP、localhost、云元数据地址和不受信任重定向，防止 SSRF。
- Provider 负责网络请求错误转换，Application 不依赖具体 SDK。
- 搜索结果属于不可信数据，不得覆盖系统规则或作为提示词指令执行。
- 根据 query hash、locale 和时间窗口做短期缓存，缓存不得跨用户泄露私人查询。

## 8. 每日来信 Feature

### 8.1 领域实体

```text
DailyLetter
- letter_id
- user_id
- local_date
- timezone
- status: pending | generating | ready | read | skipped | failed
- subject
- content
- source_message_ids
- generation_version
- scheduled_at
- generated_at
- published_at
- read_at
- failure_code
```

唯一约束：

```text
UNIQUE(user_id, local_date, generation_version)
```

`local_date` 表示被回顾的用户本地自然日，不是服务器 UTC 日期。

### 8.2 生成条件

必须同时满足：

- 用户开启每日来信。
- 用户配置了有效时区，或明确接受产品默认时区。
- 前一自然日至少存在一轮有效用户互动。
- 当天没有 ready/generating 的同版本信件。
- 用户没有处于删除、封禁或数据清理状态。

无互动时记录 `skipped` 及原因，避免调度器反复尝试。

### 8.3 内容输入

只允许使用：

- 前一自然日内当前用户的聊天消息。
- 对应会话摘要中的有来源用户事实。
- 当天产生或更新的长期记忆。
- Echo Persona。
- 当前关系阶段和用户表达偏好。
- 已完成且与当天直接相关的共同目标事件。

禁止使用：

- 其他用户数据。
- 没有来源的模型推测。
- Echo 虚构的离线经历、身体活动和现实环境。
- 为增加戏剧性而编造的情绪、冲突或承诺。

### 8.4 内容结构

v1 建议长度 150 至 500 中文字：

```text
主题

对当天一至两个具体片段的自然回顾
Echo 对这些片段的有限观察或想法
克制的结尾，不要求用户回复，不制造愧疚或依赖
```

信件不是聊天摘要。摘要解决事实连续性；信件表达人物化的整理和观察。

### 8.5 调度与发布

默认策略：

- 用户本地次日 `07:45` 创建生成任务。
- 用户本地次日 `08:00` 发布 ready 信件。
- 生成时间和发布时间分别配置，便于预留失败重试窗口。
- 任务以 `(user_id, local_date, generation_version)` 为幂等键。
- 失败按持久化后台任务规则重试，超过次数标记 failed。
- 服务重启后恢复 pending/running 任务。

不得为每个用户创建常驻内存定时器。调度器应周期扫描“下一个本地发布时间已到”的用户，并通过数据库 claim 任务。

### 8.6 API

```text
GET /letters/latest
GET /letters?limit=&cursor=&status=
GET /letters/{letter_id}
POST /letters/{letter_id}/read
GET /letters/preferences
PUT /letters/preferences
```

响应必须包含稳定 schema；用户身份只来自 Bearer Token。

### 8.7 小程序 UI

- 人物区域新增信件图标，不放入聊天输入区。
- 有未读 ready 信件时显示角标或轻量动画。
- 点击进入信件列表或最新信件页。
- 阅读后调用 read API，角标消失。
- 生成失败不向用户展示技术错误；没有新信时保持普通空状态。
- 设置页允许开关每日来信、设置时区和本地发布时间。

## 9. 表情包 Feature

### 9.1 领域实体

```text
Sticker
- sticker_id
- owner_type: echo | user
- owner_user_id
- source: builtin | generated | uploaded
- storage_key
- content_type
- width
- height
- byte_size
- perceptual_hash
- description
- semantic_tags
- status: processing | active | rejected | deleted
- moderation_status
- created_at
- updated_at
```

```text
StickerGenerationJob
- job_id
- user_id
- prompt
- normalized_intent
- status: pending | running | completed | failed
- generated_sticker_id
- attempts
- error_code
- created_at
- finished_at
```

### 9.2 表情包工具

```text
search_stickers
- input: intent, emotion, maximum_results
- output: sticker candidates with score

send_sticker
- input: sticker_id
- output: chat attachment command

request_sticker_generation
- input: intent, visual_description, emotion
- output: generation_job_id

save_user_sticker
- 只由明确的用户上传/保存操作触发，不允许 Agent 静默保存
```

### 9.3 检索策略

第一阶段使用：

- 标准化语义标签。
- 关键词、情绪和 intent 加权匹配。
- 最近使用惩罚，避免重复发送同一张。
- 用户私人库优先级可配置，但不得跨用户召回。

后续可以增加图片 embedding 和文本 embedding，但必须隐藏在 `StickerSearchIndex` Protocol 后。

### 9.4 发送策略

- 用户明确要表情包时可以直接检索发送。
- 轻松、庆祝、玩笑等语境可以由 Agent 建议发送。
- 严肃、安全、医疗、冲突和明显悲伤场景默认不主动发表情包。
- 默认最多连续 5 轮发送 1 次主动表情包；用户明确请求不受此限制。
- 同一表情包设置最近使用冷却。
- 发送动作必须保存为结构化聊天附件，不能把图片 URL 拼进普通文本。

### 9.5 用户上传与保存

流程：

```text
上传文件
-> 校验 MIME、文件头、尺寸和大小
-> 内容审核
-> 计算感知哈希去重
-> 用户确认保存
-> 提取/编辑标签
-> 写入私人 Sticker Library
```

要求：

- 上传接口限流。
- 文件存储 key 不使用原始文件名。
- 用户只能读取、发送和删除自己的私人表情包。
- 删除数据库记录时同步安排对象存储清理任务。
- 不默认把用户表情包加入全局 Echo 库。
- 若未来允许共享，必须有独立授权、版权和审核流程。

### 9.6 图片生成

- 图片生成通过 `ImageGenerationProvider`。
- Agent 只创建生成请求，不能直接调用具体 SDK。
- 生成请求进入持久化后台任务。
- 生成结果先审核，再入库和发送。
- 当前聊天不能无限等待图片生成；超过同步等待阈值后返回自然文字，生成完成后由事件决定是否展示。
- 同一 Run 的生成请求必须有幂等键，避免重试重复计费。

### 9.7 API

```text
GET /stickers?owner=&tags=&cursor=&limit=
POST /stickers/upload
POST /stickers/{sticker_id}/confirm-save
DELETE /stickers/{sticker_id}
POST /stickers/generations
GET /stickers/generations/{job_id}
```

聊天发送接口需要向后兼容扩展：

```json
{
  "reply": "这次确实值得庆祝。",
  "content_parts": [
    {"type": "text", "text": "这次确实值得庆祝。"},
    {"type": "sticker", "sticker_id": "stk_xxx", "url": "..."}
  ],
  "audio_urls": []
}
```

`reply` 暂时保留，避免破坏现有客户端；新客户端优先渲染 `content_parts`。

## 10. 数据库设计

新增表建议：

- `agent_runs`
- `agent_tool_calls`
- `daily_letters`
- `letter_preferences`
- `stickers`
- `sticker_generation_jobs`
- `chat_message_attachments`

### 10.1 关键索引

```text
agent_runs(user_id, created_at DESC)
agent_runs(status, created_at)
agent_tool_calls(run_id, created_at)
daily_letters(user_id, published_at DESC)
daily_letters(user_id, local_date, generation_version) UNIQUE
daily_letters(status, scheduled_at)
stickers(owner_user_id, status, created_at DESC)
stickers(perceptual_hash)
sticker_generation_jobs(status, created_at)
chat_message_attachments(message_id, position)
```

迁移必须：

- 使用独立、可重复执行的 migration。
- 不在应用启动时执行 destructive migration。
- 保持现有 `POST /chat/send` 响应兼容。
- 为新增约束和索引补 Repository 测试。

## 11. 后台任务与事件

### 11.1 任务类型

```text
daily_letter_generation
daily_letter_publish
sticker_generation
sticker_asset_cleanup
agent_deferred_action
```

任务状态遵循：

```text
pending -> running -> completed
pending -> running -> retry -> failed
```

每个任务必须包含：

- job_id
- job_type
- status
- payload
- idempotency_key
- attempts
- max_attempts
- error_code
- started_at
- finished_at

### 11.2 领域事件

建议事件：

```text
ChatTurnCompleted
DailyLetterGenerated
DailyLetterPublished
StickerUploaded
StickerGenerated
StickerSent
MemoryExtracted
```

第一阶段可以使用数据库 Outbox + Worker 轮询。禁止仅依赖进程内 `asyncio.create_task` 承载信件生成、图片生成和发布等关键任务。

## 12. 配置

建议新增：

```text
AGENT_ENABLED=true
AGENT_MODEL=
AGENT_MAX_STEPS=6
AGENT_MAX_TOOL_CALLS=4
AGENT_RUN_TIMEOUT_SECONDS=45

WEB_SEARCH_PROVIDER=
WEB_SEARCH_API_KEY=
WEB_SEARCH_TIMEOUT_SECONDS=10
WEB_SEARCH_MAX_CALLS_PER_RUN=2
WEB_SEARCH_CACHE_TTL_SECONDS=900

DAILY_LETTER_ENABLED=true
DAILY_LETTER_GENERATION_LOCAL_TIME=07:45
DAILY_LETTER_PUBLISH_LOCAL_TIME=08:00
DAILY_LETTER_MODEL=
DAILY_LETTER_MAX_TOKENS=900
DAILY_LETTER_MAX_ATTEMPTS=3

STICKER_ENABLED=true
STICKER_IMAGE_PROVIDER=
STICKER_MAX_UPLOAD_BYTES=
STICKER_MAX_WIDTH=
STICKER_MAX_HEIGHT=
STICKER_GENERATION_TIMEOUT_SECONDS=
STICKER_PROACTIVE_COOLDOWN_TURNS=5
```

所有 secret 只通过环境变量或密钥服务注入；`.env.example` 只提供空值或安全示例。

## 13. 安全、隐私与产品边界

### 13.1 用户数据

- 所有信件、私人表情包、Agent Run 和附件按 `user_id` 隔离。
- 任何公开 URL 都不能泄露可枚举的存储路径。
- 私人图片优先使用带过期时间的签名 URL。
- 用户删除账号时，信件、表情包、附件、Agent 轨迹和对象存储文件进入可验证清理流程。

### 13.2 内容安全

- 网络结果、用户上传图片和生成图片都视为不可信输入。
- 图片上传和生成结果必须审核后才能 active。
- 信件生成服从现有安全规则、关系边界和真实性边界。
- Agent 不得通过工具调用规避模型安全策略。

### 13.3 主动行为边界

- 每日来信是用户可关闭的固定产品能力，不代表 Echo 在后台持续生活。
- Echo 不得声称自己一整天都在观察、等待或想念用户。
- 主动表情包必须受频率策略控制。
- 网络检索不得主动追踪用户、搜索私人身份或扩大用户未授权的调查范围。

## 14. 可观测性

结构化日志至少包含：

- request_id
- user_id（脱敏）
- conversation_id
- run_id
- tool_call_id
- job_id
- provider
- tool_name
- trigger_type
- duration_ms
- error_code

核心指标：

- Agent Run 成功率、平均步骤数、超限比例。
- 各工具调用量、失败率、P50/P95 延迟和费用。
- 网络检索触发率、缓存命中率和无结果率。
- 每日来信 scheduled/generated/published/read/skipped/failed 数量。
- 信件生成耗时、重试率和阅读率。
- 表情包检索命中率、主动发送率、用户删除率。
- 图片生成成功率、审核拒绝率和平均费用。

日志禁止包含完整搜索 query、完整信件、聊天隐私、图片内容、API key 和签名 URL。

## 15. 测试策略

### 15.1 Agent Domain

- 工具白名单。
- 风险分级。
- 最大步骤和最大调用次数。
- 重复非幂等调用拦截。
- 用户关闭能力后的工具拒绝。
- Fake Tool、Fake Clock 和 Fake LLM 下的确定性执行。

### 15.2 时间

- 用户时区转换。
- UTC 跨日。
- 夏令时切换。
- “今天/昨天/明天”解析。
- 缺失时区时的显式降级。

### 15.3 网络检索

- 明确搜索请求触发。
- 普通闲聊不触发。
- 时效性问题触发。
- 超时、无结果、Provider 错误降级。
- SSRF 和不安全 URL 拦截。
- 搜索结果中的提示词注入不能改变系统规则。

### 15.4 每日来信

- 用户本地自然日边界。
- 无互动跳过。
- 同日幂等。
- 任务失败重试和服务重启恢复。
- 信件只能引用给定 source_message_ids。
- 不虚构离线经历。
- 未读/已读状态和前端角标。
- 跨用户隔离。

### 15.5 表情包

- MIME 和文件头双重校验。
- 大小、尺寸、感知哈希去重。
- 私人库隔离。
- 内容审核状态流转。
- 主动发送冷却。
- 严肃语境禁止主动发送。
- 图片生成幂等与失败恢复。
- 删除记录后对象清理任务。

### 15.6 关键集成测试

```text
聊天 -> Agent -> 时间工具 -> 正确时间回复
聊天 -> Agent -> 网络检索 -> 带来源回复
聊天 -> Agent -> 表情包检索 -> content_parts 返回
用户上传 -> 审核 -> 确认保存 -> 私人库可检索
定时扫描 -> 信件生成 -> 发布 -> 人物区域未读角标 -> 阅读
服务重启 -> pending 任务恢复
```

## 16. 分阶段开发计划

### Phase 0：契约与迁移

- 定义 Agent、Tool、Letter、Sticker Domain。
- 定义 Provider Protocol。
- 建立数据库 migration、索引和配置。
- 建立 Fake 实现和架构依赖测试。

验收：没有真实工具时，Fake Agent Run 可以完整执行并持久化轨迹。

### Phase 1：时间工具与 Agent 基础循环

- 实现 Tool Registry、Agent Policy 和有限执行循环。
- 实现 Clock 和时间工具。
- Chat 通过 Agent Application 生成回复。
- 保留不需要工具时的单次 LLM 快速路径。

验收：时间问题不再由模型猜；普通聊天不会额外调用工具。

### Phase 2：网络检索

- 接入 WebSearchProvider。
- 实现触发策略、缓存、来源结构和 SSRF 防护。
- 文字聊天展示来源；电话模式保留结构化来源。

验收：实时问题可检索并带来源，普通闲聊检索率接近零。

### Phase 3：表情包库

- 实现上传、审核、保存、删除和标签检索。
- 扩展 Chat `content_parts` 和附件表。
- 实现 Agent 检索/发送工具与主动发送冷却。

验收：用户私人表情包严格隔离，Echo 能在合适语境选择已有表情包。

### Phase 4：表情包生成

- 接入 ImageGenerationProvider。
- 实现生成任务、审核、对象存储和幂等。
- 处理异步完成后的展示策略。

验收：生成失败不阻塞聊天，重试不重复计费或产生重复资源。

### Phase 5：每日来信

- 实现 Letter Domain、设置 API、调度器、生成 Worker 和 UI。
- 使用前一自然日有来源消息生成。
- 接入未读角标和阅读状态。

验收：按用户本地时间稳定发布；无互动跳过；内容不虚构且不进入聊天框。

### Phase 6：灰度与评测

- Feature Flag 分用户灰度。
- 建立工具触发准确率、信件质量和表情包自然度评测集。
- 分析费用、延迟、失败率和用户关闭率。
- 达到门槛后逐步扩大。

## 17. 发布门禁

上线前必须满足：

- Domain、Application、Infrastructure、Interface 测试通过。
- Black、Ruff、类型检查、架构依赖检查通过。
- migration 可重复执行，并提供修复方案。
- 所有关键任务可持久化、可恢复、可观测。
- Agent 有步骤、调用次数、超时和费用上限。
- 网络检索完成 SSRF、注入和来源测试。
- 图片上传/生成完成审核和用户隔离测试。
- 每日来信完成时区、幂等、真实性和关闭开关测试。
- 旧客户端在没有 `content_parts` 支持时仍可正常显示 `reply`。

## 18. 最终架构结论

本期将 Agent 从 Chat 中逻辑独立为后端内部 Feature，但不拆成独立微服务。

Agent 是工具与主动任务的决策编排层；Chat、Memory、Letters、Stickers 继续拥有各自的领域规则和数据。时间、网络检索、图片生成和对象存储通过可替换 Provider 接入。每日来信与表情包生成使用持久化任务和 Worker，不依赖进程内临时任务。

这一结构既能支持当前需求，也为未来增加日程、学习、自律、通知和更智能的信息检索保留稳定扩展点。

# Echo 统一 Agent 对话运行时重构方案

> 状态：核心重构已实现，待真机验收
>
> 日期：2026-08-05
>
> 适用范围：聊天与语音通话的对话生成、工具调用、结构化内容交付和消息持久化
>
> 与旧方案的关系：本文取代 `agent-tool-orchestration-plan.md` 中“独立 Planner + 工具成功后固定模板 + 主 Chat LLM 兜底”的回复设计。旧文档保留为 Phase 1 实施记录，不再作为后续架构依据。

## 1. 背景与现状

当前链路已经能发送表情包，但仍然是混合架构：

```text
POST /chat/send
  -> 构建完整聊天上下文
  -> Agent Planner 单独判断是否调用工具
  -> 执行 search_stickers / send_sticker
  -> 工具成功：ResponsePolicy 使用固定文案，跳过主 Chat LLM
  -> Planner finish 或异常：回退到主 Chat LLM 自由回复
  -> 组合 reply 与 content_parts
```

这造成了三个直接问题：

1. Agent 工具路径与普通 LLM 回复路径互相独立，Echo 的人格、语气和工具行为没有在同一次模型推理中完成。
2. 表情包发送成功时只能返回固定文案，无法结合当前对话自然表达。
3. Agent 失败后静默回退到主 LLM，主 LLM 看不到完整工具事实，可能一边实际返回表情包，一边声称自己不能发送。

此外，当前 `content_parts` 只随 HTTP 响应返回，没有随 assistant 消息写入 `chat_message_attachments`。下一轮上下文只读取文字，模型不知道上一轮真实发送过的附件，这会继续制造能力认知和会话事实的不一致。

## 2. 核心决策

### 2.1 Agent 是运行时，LLM 是它的决策与表达引擎

重构后，每一条用户消息都进入统一 Agent Runtime。LLM 不再位于 Agent 之外，也不再有“Agent 回复”和“Chat LLM 回复”两套结果。

```text
用户消息 + 人格 + 记忆 + 会话历史 + 可用工具
  -> Agent Runtime 调用对话模型
  -> 模型直接回复，或者提出工具调用
  -> Runtime 执行工具并把结果追加到同一回合
  -> 同一个对话模型继续判断或生成自然回复
  -> Runtime 汇总工具产生的附件和来源
  -> 原子化保存文字、附件与运行记录
  -> 返回 APP
```

这里的“同一个模型”指同一套模型配置、人格、上下文和 Agent 状态。一次带工具的回合通常需要多次模型 API 请求，因为服务器必须在两次请求之间真正执行工具；这些请求仍属于同一个 `run_id`，不是 Planner 和 Chat LLM 两条独立链路。

### 2.2 模型负责选择与表达，工具负责客观事实

模型负责：

- 判断是否需要工具。
- 选择工具并生成语义参数。
- 看到工具结果后继续推理。
- 结合 Echo 人格生成最终自然文字。
- 在轻松且合适的语境中主动决定是否附带表情包。

工具与 Runtime 负责：

- 权限、资源可见性和参数校验。
- 查询、发送、保存、删除等动作是否真实成功。
- 附件、来源、错误码和幂等结果。
- 调用次数、超时、冷却和风险限制。
- 最终响应中的结构化内容只能来自已成功执行的工具。

模型不能直接编造 `sticker_id`、URL、时间、搜索来源或工具成功状态。

### 2.3 最终回复只有一个

最终 `reply_text` 必须由 Agent 回路中的对话模型生成。工具结果作为同一回路里的事实提供给模型，`content_parts` 和 `sources` 则由 Runtime 根据工具结果确定性汇总。

固定文案仅保留为以下情况的最后兜底，不参与正常成功路径：

- 模型服务最终生成失败或超时。
- 模型连续返回不合法协议结果。
- 工具已经成功产生必须交付的附件，但最终自然文字无法生成。

不再用关键词或正则扫描 LLM 回复并二次纠错，也不再在 Agent 异常时静默调用旧 Chat LLM。

## 3. 目标与非目标

### 3.1 本次目标

1. 所有聊天和通话文本回合统一进入 Agent Runtime。
2. 普通聊天、工具选择和最终自然回复使用同一逻辑模型回路。
3. 表情包明确请求和 Echo 主动发送都通过正式工具完成。
4. 最终文字与已执行工具事实保持同一上下文。
5. 用户和 Echo 的消息附件均持久化，并能进入后续会话上下文。
6. 时间、网络检索和表情包工具进入同一个 Tool Registry。
7. 保持 APP 当前 `/chat/send` 请求与响应协议兼容。
8. 为长期记忆、来信等后续工具保留稳定扩展点。

### 3.2 本次非目标

- 不引入无限自主循环或无人值守后台 Agent。
- 不允许 Agent 绕过现有 feature public API 直接访问其他模块数据库。
- 不让模型直接控制附件 URL、用户身份或权限结论。
- 不在第一阶段支持一条 Echo 回复发送多张表情包。
- 不在本次重构中实现表情包生成、视觉理解或长期任务恢复。
- 不为使用框架而强制引入 LangGraph。

## 4. 目标数据流

### 4.1 普通聊天

```text
APP POST /chat/send
  -> Chat 校验请求并取得 conversation_id
  -> Context Builder 构建人格、记忆、摘要、历史和当前消息
  -> Agent Runtime 暴露本回合允许使用的工具
  -> Conversation Model 返回 final
  -> Runtime 生成 AgentTurnResult
  -> Chat 原子化保存 user message + assistant message
  -> APP 收到 reply + content_parts + sources
```

普通聊天通常只需要一次模型调用。它仍然经过 Agent Runtime，只是模型判断无需工具并直接完成回复。

### 4.2 用户明确要求发送表情包

```text
用户：“给我发一个开心的表情包”
  -> 模型调用 search_stickers(query="开心")
  -> Runtime 返回候选的 id、描述和语义标签
  -> 模型从候选中调用 send_sticker(sticker_id=...)
  -> Runtime 校验候选范围并返回 succeeded + ContentPart
  -> 同一模型看到发送成功事实，生成符合当前聊天语境的自然回复
  -> Runtime 交付 reply_text + 一张 sticker attachment
```

最终文字不再是固定的“给你”模板。附件是否出现只由 `send_sticker` 的真实结果决定。

### 4.3 Echo 主动发送表情包

```text
自然聊天
  -> 模型结合人格、当前情绪和对话语境判断适合附带表情包
  -> Runtime 先检查主动发送策略和冷却状态
  -> search_stickers(语义意图)
  -> send_sticker(候选 id)
  -> 同一模型结合工具结果完成自然文字
  -> 文字气泡与表情包图片作为同一 assistant 消息的独立内容部分交付
```

第一阶段主动发送约束：

- 每个 assistant 回合最多一张表情包。
- 不允许连续两个 Echo 回合主动发送。
- 默认设置回合冷却，可配置，初始建议为 4 个 assistant 回合。
- 严肃、安全、医疗、冲突、明显悲伤和工具报错场景默认禁止主动发送。
- 用户明确要求发送时不受主动发送冷却限制，但仍受每回合数量和权限限制。
- 模型只能表达语义意图，最终候选必须来自用户可见的表情包集合。

### 4.4 时间工具示例

```text
用户：“现在几点？”
  -> 模型调用 get_current_time(timezone="Asia/Shanghai")
  -> Runtime 返回可靠时间
  -> 同一模型自然回复当前时间
```

不再由关键词函数在 Agent 回路之外预先调用时间工具。

### 4.5 语音通话

```text
ASR 最终文本
  -> 与聊天相同的 Agent Runtime
  -> 通话模式不注册表情包工具
  -> AgentTurnResult.reply_text
  -> TTS 只合成 reply_text
  -> 只返回文字与音频，不交付表情包 content_parts
```

通话模式完全关闭表情包发送，包括 Echo 主动发送和用户明确要求两种情况。Runtime 不向模型暴露 `search_stickers`、`send_sticker`，Executor 同时拒绝通话模式下的表情包工具调用；即使模型产生越界调用，也不得生成或持久化表情包附件。

## 5. Agent 回路协议

### 5.1 运行状态

```text
created
  -> model_deciding
  -> executing_tools
  -> model_deciding
  -> finalizing
  -> completed | failed
```

回路必须有明确上限：

- 默认最多 6 个模型步骤。
- 默认最多 4 次工具调用。
- 每回合最多一次 `send_sticker` 成功结果。
- 单工具和整个 Agent 回合分别设置超时。
- 达到限制后不再调用工具，进入受控结束流程。

### 5.2 模型返回类型

模型适配层不再只返回字符串，而是返回完整 assistant 消息：

```python
@dataclass(frozen=True)
class AgentModelResponse:
    text: str
    tool_calls: tuple[AgentToolCall, ...]
    finish_reason: str
    provider_request_id: str = ""
```

合法结果只有两类：

1. `tool_calls` 非空：Runtime 校验并执行工具，把 assistant tool call 和 tool result 追加到本回合消息序列。
2. `tool_calls` 为空：`text` 是本回合唯一候选最终回复，Runtime 完成一致性检查后结束。

第一阶段按顺序执行工具调用。只有确认互不依赖、只读且无副作用的工具，后续才允许并行执行。

### 5.3 原生 Function Calling 与兼容方案

优先通过 OpenAI-compatible `tools` / `tool_choice=auto` 协议接入当前模型 Provider，并保留完整的 `assistant.tool_calls` 与 `tool` 消息。

实施前先做 Provider 能力验证：

- 当前模型是否稳定返回 `tool_calls`。
- 是否支持连续的 search -> send -> final 多步回路。
- 空文本但存在 `tool_calls` 是否能正确解析。
- tool result 回灌后是否能稳定生成中文自然回复。
- 超时、限流和非法参数时的响应结构。

如果当前 Provider 不支持原生 Function Calling，则使用结构化 action 兼容适配器，但仍必须满足：

- action 生成和最终自然回复使用同一个模型接口与完整 Agent 上下文。
- 工具结果追加回同一个消息序列。
- 不恢复独立 Planner 与主 Chat LLM 双路径。
- 兼容适配器仅改变协议编码，不改变 Agent Runtime 的领域接口。

## 6. 上下文设计

每次 Agent 模型调用都使用同一份基础上下文，并在工具执行后追加新消息：

```text
1. Echo 人格与对话边界
2. 工具使用规则与可靠事实规则
3. 会话摘要
4. 长期记忆检索结果
5. 关系状态
6. 最近会话历史（含附件语义）
7. 当前用户消息（含附件语义）
8. 本回合 assistant tool_calls
9. 本回合 tool results
```

### 6.1 用户表情包进入上下文

用户发送表情包时，服务器根据已校验的 `sticker_id` 读取上传时保存的描述和语义标签，构造成可信的结构化内容。例如：

```text
用户发送了一张表情包。
描述：开心地挥手
语义标签：开心、打招呼
```

语义数据来自表情包存储记录，不信任 APP 任意提交的描述。模型据此理解用户消息并必须回复。

### 6.2 Echo 历史附件进入上下文

历史 assistant 消息不能只返回文字。Context Builder 需要同时读取 `chat_message_attachments`，把已发送表情包的描述、标签和发送事实作为该 assistant 消息的一部分提供给模型。

这样下一轮模型能知道“Echo 上一轮已经发过一张开心表情包”，不依赖旧文本猜测工具能力，也不需要清除记忆。

旧聊天中“Echo 不能发送图片/表情包”之类的 assistant 文本保留为历史对话，不做数据清洗；当前 Runtime 提供的工具清单、工具执行结果和系统能力声明具有更高优先级。长期记忆若误存了这类系统能力判断，则在记忆上下文组装时过滤，因为系统能力不属于用户长期记忆事实。

### 6.3 工具结果安全边界

- 工具结果进入模型前转换为 `safe_for_model` 结构。
- 网络检索内容按不可信外部资料处理，不能成为新的系统指令。
- 内部路径、鉴权信息和无关用户数据不得进入模型。
- 对模型暴露稳定资源 ID、语义描述和结果状态，不暴露可被伪造的客户端 URL 作为执行依据。

## 7. 工具系统

### 7.1 统一 Tool Registry

每个工具声明：

```python
ToolDefinition(
    name="send_sticker",
    description="将已检索且当前用户可见的表情包附加到本次 Echo 回复",
    input_schema=SendStickerInput,
    risk_level=ToolRisk.SEND,
    timeout_seconds=5,
    max_calls_per_turn=1,
    allow_proactive=True,
)
```

定义还应包含：

- 参数与输出 Schema。
- handler。
- 权限与可见性策略。
- 是否有副作用、是否幂等。
- 允许的会话模式。
- 是否允许主动调用。
- 返回给模型的安全投影方式。

### 7.2 第一批迁移工具

| 工具 | 类型 | 用途 | 第一阶段约束 |
| --- | --- | --- | --- |
| `get_current_time` | read | 获取可靠服务端时间 | 替换关键词预处理 |
| `search_web` | read | 获取外部事实和来源 | 返回内容视为不可信资料 |
| `search_stickers` | read | 按描述和标签检索候选 | 最多返回 3 个候选 |
| `send_sticker` | send | 为本次回复附加候选表情包 | 必须来自本回合检索结果，最多成功一次 |

### 7.3 `send_sticker` 的准确语义

`send_sticker` 在当前 HTTP 聊天架构中不是绕过 Chat 直接推送文件，而是确认“将这个表情包作为本次 assistant 消息附件交付”。

成功结果必须包含：

```json
{
  "status": "completed",
  "delivery": "attached_to_current_reply",
  "sticker_id": "stk_xxx",
  "description": "开心地挥手",
  "semantic_tags": ["开心", "打招呼"]
}
```

Runtime 根据该结果创建 `ContentPart`。模型只看到已成功附加的事实，不能自行添加、替换或删除附件。

## 8. 最终结果与一致性

### 8.1 `AgentTurnResult`

```python
@dataclass(frozen=True)
class AgentTurnResult:
    run_id: str
    status: AgentRunStatus
    reply_text: str
    content_parts: tuple[ContentPart, ...]
    sources: tuple[SourceReference, ...]
    tool_results: tuple[AgentToolResult, ...]
    model_steps: int
    error_code: str | None = None
```

删除 `AgentReplyMode.LLM` 与 `AgentReplyMode.CONTROLLED`。`GenerateChatReply` 不再根据模式选择另一个 LLM，只消费一个完整的 `AgentTurnResult`。

### 8.2 确定性规则

- `content_parts` 只能从 `completed` 工具结果汇总。
- `send_sticker` 未成功时不得返回 sticker `ContentPart`。
- `send_sticker` 成功时必须返回且只返回对应 sticker `ContentPart`。
- `sources` 只能来自成功的检索工具。
- 模型文本不能改变工具状态或附件集合。
- 任何客户端重试都不得重复产生同一附件或工具副作用。

### 8.3 自然回复一致性

最终模型调用会收到清晰的工具结果，例如“表情包已经附加到当前回复”，并要求基于事实自然回答。正常路径不使用固定模板。

Runtime 只接受基于当前 `AgentState` 最新版本生成的 final：所有已完成工具结果必须已经作为 `tool` 消息进入该次模型调用，附件清单必须与成功工具结果完全一致。若最终调用返回空文本、非法协议、再次请求越界工具，或其状态版本已经过期，Runtime 最多进行一次同回路重试，并附加结构化一致性错误。这里校验的是运行时状态、call id、结果状态和附件引用，不通过中文关键词判断意图。

文本语义一致性通过高优先级能力声明、真实工具结果回灌和端到端回归用例约束。旧历史中的能力否认不得覆盖当前工具事实；正常成功链路不再额外启动一套 Chat LLM，也不使用关键词替换生成文本。

若重试仍失败：

- 已成功生成附件：保留权威附件，使用最小兜底文字完成交付并记录错误。
- 工具未成功：不返回附件，使用明确失败兜底或整体请求错误。
- 不调用旧 Chat LLM，也不伪造工具成功。

## 9. 持久化设计

### 9.1 原子保存一次聊天回合

一次成功交付应在同一数据库事务中保存：

1. user `chat_messages` 记录。
2. 用户消息附件及其语义快照。
3. assistant `chat_messages` 记录。
4. assistant 消息附件及其语义快照。
5. `agent_runs` 与 assistant 消息的关联结果。

`chat_message_attachments` 已存在，第一阶段复用该表：

- `message_id` 使用 `chat_messages.message_id`，不使用数据库自增 `id`。
- `attachment_type=sticker`。
- `resource_id=sticker_id`。
- `position` 保留内容顺序。
- `metadata` 保存交付时的描述、语义标签、公开 URL 快照和来源信息。

实现时需让仓储层返回内部 `id` 与稳定 `message_id`，避免当前只返回数字 id 而无法可靠写附件的问题。

### 9.2 Agent 运行记录

继续复用：

- `agent_runs`：一次统一 Agent 回合。
- `agent_tool_calls`：每个模型提出并实际执行的工具调用。

建议补充或在现有字段中记录：

- `conversation_id`
- `user_message_id`
- `assistant_message_id`
- `model_step_count`
- `provider_request_id`
- `final_outcome`
- `runtime_version`

是否新增数据库列在实现阶段根据现有迁移方式确定，但日志中必须先具备这些关联标识。

### 9.3 摘要与长期记忆

- 摘要更新在文字与附件持久化成功后执行。
- 摘要输入包含附件的语义描述，不包含二进制内容。
- 长期记忆抽取仍由现有后台调度负责，不把每个工具调用自动写成长期记忆。
- “Echo 已经具备发送表情包能力”属于系统能力，不应依赖用户记忆保存。

## 10. 失败、降级与幂等

### 10.1 禁止双路径回退

Agent Runtime 启用后，一次请求只能由它完成。以下行为全部删除：

- Planner 失败后调用独立 Chat LLM。
- `finish` 后再交给主 Chat LLM 生成另一份回复。
- 工具成功后由固定 ResponsePolicy 抢占回复。
- 根据关键词修正模型是否承认发送能力。

### 10.2 失败策略

| 场景 | 行为 |
| --- | --- |
| 首次模型调用失败 | 不执行工具，返回可观察的受控错误或最小兜底 |
| 只读工具失败 | 将失败状态回灌同一模型，让其自然说明暂时无法查询 |
| `search_stickers` 无结果 | 回灌 `no_result`，由同一模型自然回复，不发送附件 |
| `send_sticker` 失败 | 回灌失败事实，由同一模型自然回复，不发送附件 |
| 工具成功后最终模型失败 | 保留权威附件，最小文字兜底，记录 `finalization_failed` |
| 达到步骤上限 | 禁止新工具，尝试一次无工具 final；失败则最小兜底 |

### 10.3 幂等

- APP 请求增加或复用请求幂等键，服务端按用户、会话和请求键保存最终结果。
- 工具调用使用 `run_id + tool_call_id` 作为幂等键。
- 同一调用重试返回原结果，不重复附加表情包。
- assistant 消息及附件必须在一个事务中落库，避免文字存在但附件丢失。

## 11. 模块调整

### 11.1 Agent

```text
features/agent/domain/entities.py
  删除 AgentReplyMode
  增加 AgentModelResponse、AgentState、AgentRunStatus
  收敛 AgentTurnResult

features/agent/domain/services.py
  AgentConversationModel 协议
  AgentOrchestrator 协议

features/agent/domain/tools.py
  统一 ToolDefinition、ToolRegistry 和调用策略

features/agent/application/orchestrate_chat.py
  实现单一有界 model/tool loop

features/agent/application/execute_tool.py
  统一校验、超时、幂等、审计和安全结果投影

features/agent/infrastructure/model.py
  OpenAI-compatible Function Calling 适配器
  必要时提供 structured-action 兼容适配器

features/agent/infrastructure/tools/
  sticker_tools.py
  time_tools.py
  web_search_tools.py
```

现有 `planner.py` 和正常路径 `response_policy.py` 在迁移完成后删除。最小灾难兜底移入 Runtime finalizer，不再承担常规回复职责。

### 11.2 Chat

```text
features/chat/application/generate_reply.py
  构建上下文后只调用 Agent Runtime
  不再持有独立 ChatLLM

features/chat/infrastructure/context_builder.py
  读取并表达历史附件语义

features/chat/domain/repositories.py
  增加原子保存消息与附件的仓储契约

features/chat/infrastructure/postgres_repositories.py
  写入 chat_messages 与 chat_message_attachments
  历史查询关联附件
```

### 11.3 Provider

```text
providers/llm_provider.py
  从 chat_completion(...) -> str
  扩展为 chat_completion(...) -> ProviderAssistantMessage
  支持 tools、tool_choice、tool_calls、finish_reason 和 request_id
```

普通文本调用方可通过薄适配器继续只读取 `text`，避免一次性影响摘要、记忆抽取等非 Agent 场景。

### 11.4 APP

第一阶段保持接口不变：

```json
{
  "reply": "自然文字",
  "audio_urls": [],
  "content_parts": [],
  "sources": []
}
```

APP 继续将文字显示在气泡中，将表情包作为独立图片显示。若后端历史接口后续返回完整内容部分，APP 再补充历史附件恢复；本次后端必须先保证新消息落库完整。

## 12. 实施阶段

### Phase 0：Provider 能力验证

- 用当前生产同款模型验证原生 Function Calling。
- 保存 search -> send -> final 的原始响应形态。
- 确认工具调用参数、空 content、错误和超时处理。
- 据证据选择原生适配器或 structured-action 兼容适配器。

交付门槛：明确 Provider 协议，不凭模型名称猜测能力。

### Phase 1：统一 Agent 核心回路

- 新建 `AgentConversationModel` 和统一响应领域对象。
- 实现有界 model/tool loop。
- 普通聊天直接在 Runtime 内 final。
- 保留现有工具但先不开放主动表情包。
- 增加新旧运行时开关用于联调。

开关只允许“整次请求选 v1 或 v2”，v2 内部不得回退 v1 Chat LLM。

### Phase 2：迁移全部现有工具

- 迁移 `get_current_time`，删除关键词时间预处理。
- 迁移 `search_web`，删除关键词网络检索预处理。
- 迁移 `search_stickers` 与 `send_sticker`。
- 删除固定成功模板和 Planner JSON 纠错链路。

### Phase 3：消息附件持久化与上下文回灌

- 原子保存 user/assistant 消息及附件。
- 历史查询恢复附件。
- Context Builder 注入用户和 Echo 的表情包语义。
- 摘要输入包含附件语义。

该阶段完成前，不开放 Echo 主动发送表情包。

### Phase 4：开放主动表情包

- 接入显式请求与主动发送的区分策略。
- 实施冷却、场景限制和单张上限。
- 观察主动发送率、用户继续对话率和手动关闭率。
- 根据真实数据调整提示和冷却，不添加关键词触发器。

### Phase 5：清理与正式切换

- 删除旧 Planner、ResponsePolicy 正常路径和独立 ChatLLM 分支。
- 删除旧关键词工具触发与否认纠错代码。
- 全量启用统一 Runtime。
- 保留短期回滚开关，稳定后移除旧实现。

## 13. 测试方案

### 13.1 单元测试

- 模型直接 final 时不执行工具。
- 模型提出合法 tool call 时执行并回灌结果。
- 非法工具、非法参数、越权资源均被拒绝。
- `search_stickers` 候选之外的 `sticker_id` 不可发送。
- 每回合最多成功发送一张表情包。
- 工具结果正确汇总为附件和来源。
- 模型、工具和总回合超时均停止循环。
- 达到步骤或调用上限后不再执行新工具。
- v2 失败时不会调用旧 Chat LLM。

### 13.2 集成测试

- 普通聊天：Echo 保持自然人格，无工具调用。
- 明确发送：search -> send -> natural final，文字与图片分开。
- 主动发送：合适场景可发送，冷却期内不连续发送。
- 无匹配表情包：自然说明，无附件。
- 发送失败：自然说明，无附件。
- 时间查询：调用真实时间工具后回答。
- 网络查询：答案与 `sources` 一致。
- 用户表情包：描述和标签进入上下文，Echo 必须回复。
- 下一轮历史：模型能看到 Echo 上一轮发送的表情包语义。
- 请求重试：不会生成重复 assistant 消息或重复附件。

### 13.3 端到端验收用例

1. 用户：“给我发一个开心的表情包。” Echo 返回自然文字和一张语义匹配的图片，不说“无法发送”。
2. 用户只发一张标签为“无语”的表情包。Echo 能理解语义并自然回复。
3. 连续普通聊天中，Echo 可在合适时主动附带一张表情包，但不会连续刷图。
4. 用户问当前时间，日志显示模型调用 `get_current_time`，最终答案来自工具结果。
5. 用户问无需工具的问题，日志无工具调用，只有统一 Agent 的 final。
6. 重启服务后继续聊天，历史上下文仍包含之前发送的表情包事实。
7. 聊天与语音的最终文字均来自同一 Agent Runtime，语音再基于该文字合成。

## 14. 日志与可观测性

每个回合至少记录：

```text
run_id
runtime_version
user_id_hash
conversation_id
conversation_mode
model_step
model_action=tool_call|final
tool_call_id
tool_name
tool_status
attachment_count
source_count
final_outcome
error_code
duration_ms
```

禁止记录 access token、表情包二进制、完整私密记忆或未经脱敏的 Provider 请求体。

建议增加指标：

- Agent 成功率和 P50/P95 延迟。
- 平均模型步骤数与工具调用数。
- 工具成功、无结果、失败和超时率。
- 表情包明确请求成功率。
- Echo 主动表情包发送率与冷却拦截率。
- 最终生成兜底率。
- 附件落库与 HTTP 交付不一致次数，该值必须为 0。

## 15. LangGraph 决策

本次不引入 LangGraph。当前目标是单请求内、步骤有上限、同步执行的 model/tool loop，显式状态机足够清晰，也更容易与现有分层和测试方式结合。

LangGraph 不会让“Agent 与 LLM 统一”自动发生；统一的关键是消息协议、工具结果回灌、单一最终回复和可靠持久化。

出现以下需求时再评估 LangGraph：

- Agent 需要跨请求暂停并等待用户确认。
- 长任务需要 checkpoint、恢复和人工介入。
- 出现大量条件分支、并行工具和子 Agent。
- 来信、计划任务与聊天共享复杂的持久化工作流。

领域接口保持框架无关，未来可替换编排实现而不改变 Tool Registry、Chat 协议和 APP。

## 16. 完成标准

以下条件全部满足后，统一 Agent 重构才算完成：

- 每个聊天和通话文本回合只产生一个 Agent `run_id` 和一个最终自然回复。
- 普通回复与工具后回复均由同一 Agent 对话模型回路生成。
- `send_sticker` 成功时文字自然、附件独立展示，且不再出现能力否认。
- 用户与 Echo 的表情包附件均持久化并进入下一轮上下文。
- 时间、网络检索和表情包不再由关键词预处理触发。
- Agent 失败不再静默进入独立 Chat LLM 路径。
- 旧 Planner、常规模板 ResponsePolicy 和关键词纠错代码完成删除。
- 后端完整测试通过，新增统一 Agent、持久化和幂等测试。
- APP `flutter analyze` 0 issue，`flutter test` 全部通过。
- 真机完成普通聊天、用户发表情包、Echo 明确发送、Echo 主动发送和语音通话回归。

## 17. 审核确认项

本方案默认采用以下产品决策，审核时重点确认：

1. 每条消息都经过统一 Agent Runtime；不再保留独立 Chat LLM 回复路径。
2. 工具后的最终文字由同一模型自然生成；固定文案只用于灾难兜底。
3. 第一阶段 Echo 主动表情包冷却为 4 个 assistant 回合，明确请求不受该冷却限制。
4. 通话模式完全不发送表情包，明确请求和主动发送均禁用。
5. 先实现项目内显式有界回路，不引入 LangGraph。
6. 附件持久化与历史回灌是开放主动表情包前的必要条件，不作为后续可选优化。

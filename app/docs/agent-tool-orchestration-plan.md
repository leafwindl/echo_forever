# Echo Agent 工具编排开发方案

> 说明：本文记录已经实现的 Phase 1 混合编排方案。后续统一 Agent 重构以
> `unified-agent-runtime-refactor-plan.md` 为准；其中“固定 ResponsePolicy + 独立 Chat LLM”
> 的设计不再作为目标架构。

> 状态：Phase 1 已实现
>
> 日期：2026-08-05
>
> 本文用于记录 Echo 的 Agent 工具编排边界、状态模型、迁移步骤和已确认决策。

## 1. 背景

Echo 已经具备时间查询、网络检索、表情包检索和表情包发送等工具能力，也已经通过 `agent_runs`、`agent_tool_calls` 记录 Agent 运行过程。

当前聊天链路仍然是“工具预处理 + 自由文本生成”模式：

```text
用户消息
  -> EnrichChatWithAgent 根据固定条件调用工具
  -> 工具结果转成 system message 和 content_parts
  -> ChatLLM 独立生成字符串回复
  -> Chat 模块组合文字与附件
```

这套模式可以完成基础功能，但工具执行结果与 LLM 回复之间没有统一的状态约束。例如：

- `send_sticker` 已经执行成功，`content_parts` 中也有表情包。
- LLM 受到旧会话内容影响，仍然回复“我没有发送图片的能力”。
- 当前只能通过关键词或正则识别矛盾文本，再要求 LLM 改写。

关键词纠错只能覆盖已知表达，无法从架构上保证工具状态与回复一致。随着长期记忆、来信、主动行为和更多工具接入，这类冲突会越来越难维护。

## 2. 目标

本次重构的核心目标是让 Agent 编排层成为一次聊天回合的状态拥有者：

1. 工具执行结果是发送、查询、保存等客观状态的唯一事实来源。
2. LLM 可以判断意图和选择工具，但不能自行宣称工具是否执行成功。
3. 最终文字、附件、来源和工具状态由同一个 `AgentTurnResult` 返回。
4. 成功、无结果、失败和超时均通过结构化状态进入确定分支。
5. 删除表情包发送链路中的关键词纠错和语义猜测兜底。
6. 保持 `/chat/send` 和 APP 现有协议兼容。
7. 为长期记忆、来信和其他 Agent 工具提供可复用的编排基础。

## 3. 非目标

本次不包含以下内容：

- 不修改用户发送表情包的 APP 交互。
- 不改变 `content_parts` 的客户端渲染协议。
- 不让 LLM 直接生成表情包 URL、文件路径或未经校验的 `sticker_id`。
- 不在第一阶段实现无限循环、自主后台任务或跨会话长时间运行的 Agent。
- 不因为引入 Agent 而清除聊天记录或长期记忆。
- 不在第一阶段强制引入 LangGraph 依赖。

## 4. 设计原则

### 4.1 LLM 负责决策，工具负责事实

LLM 可以输出：

- 是否需要调用工具。
- 调用哪个工具。
- 工具需要的语义参数。
- 普通聊天回复的语气或内容目标。

LLM 不能决定：

- 工具是否真的执行成功。
- 用户是否有权访问某个资源。
- 表情包是否已经作为附件返回。
- 长期记忆是否已经写入或删除。
- 来信是否已经创建、发送或标记已读。

这些状态只能来自工具执行结果。

### 4.2 副作用动作必须由状态驱动回复

对发送、保存、删除等有副作用的工具，最终确认语句由响应策略根据工具状态产生，不让 LLM 自由描述执行结果。

例如：

```text
send_sticker.status = succeeded
  -> content_parts 必须包含对应 sticker
  -> 回复使用“已发送”状态下的受控文案

send_sticker.status = failed
  -> content_parts 不得包含 sticker
  -> 回复使用“发送失败”状态下的受控文案
```

受控文案可以根据 `tone` 从有限模板中选择，但成功或失败语义不能由 LLM 改写。

### 4.3 工具输入必须再次校验

即使工具参数来自 LLM，也必须执行服务端校验：

- 校验 `user_id` 与资源可见范围。
- 只允许发送检索结果中返回的候选 `sticker_id`。
- 限制每轮工具调用次数、超时时间和返回数量。
- 不信任 LLM 生成的 URL、路径、用户身份或权限结论。

### 4.4 Agent 状态与聊天展示分离

Agent 负责产生结构化结果，Chat 负责持久化和交付，APP 负责展示：

```text
Agent: 决策、工具调用、工具结果、最终状态
Chat: 会话上下文、消息落库、HTTP 响应
APP: 文字气泡、表情包图片、来源列表、错误状态
```

## 5. 目标架构

```text
POST /chat/send
  -> Chat Context Builder
  -> Agent Orchestrator
       -> Agent Planner
       -> Tool Registry
       -> Tool Executor
       -> Agent State
       -> Response Policy
  -> AgentTurnResult
  -> Chat Persistence
  -> ChatResponse
  -> APP
```

各组件职责如下：

| 组件 | 职责 |
| --- | --- |
| `AgentOrchestrator` | 驱动规划、工具执行和最终状态转换 |
| `AgentPlanner` | 将用户意图和工具结果转换为结构化下一步 |
| `ToolRegistry` | 注册工具名称、参数模型、风险级别和处理器 |
| `ToolExecutor` | 校验参数、执行超时、记录调用并返回统一结果 |
| `AgentState` | 保存当前回合的计划、步骤、工具结果和交付事实 |
| `ResponsePolicy` | 根据最终状态生成受控确认文案和附件 |
| `Chat` | 保存用户消息和 Agent 最终回复，不参与工具语义判断 |

## 6. Agent 状态模型

### 6.1 回合状态

建议定义以下状态：

```text
planning
executing
finalizing
completed
failed
```

状态转换：

```text
planning
  -> executing     存在合法工具调用
  -> finalizing    不需要工具，直接回复

executing
  -> planning      工具结果需要下一步决策
  -> finalizing    已满足目标或达到步骤上限
  -> failed        不可恢复错误

finalizing
  -> completed     已生成一致的 AgentTurnResult
  -> failed        无法构造合法响应
```

### 6.2 核心领域对象

建议将现有 `AgentEnrichment` 逐步替换为以下结构：

```python
@dataclass(frozen=True)
class AgentToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentToolResult:
    call_id: str
    tool_name: str
    status: str  # succeeded | no_result | failed | timed_out
    data: dict[str, Any]
    safe_for_model: str
    error_code: str | None = None


@dataclass(frozen=True)
class AgentTurnResult:
    run_id: str
    status: str
    reply_text: str
    content_parts: tuple[ContentPart, ...]
    sources: tuple[SourceReference, ...]
    tool_results: tuple[AgentToolResult, ...]
```

`reply_text` 和 `content_parts` 必须由最终 `AgentState` 一次性生成，不能由两个互不知情的流程分别提供。

## 7. Planner 协议

### 7.1 统一规划结果

Planner 每一步只允许返回以下两类动作：

```json
{
  "action": "tool_call",
  "tool_name": "search_stickers",
  "arguments": {
    "query": "开心"
  }
}
```

或：

```json
{
  "action": "finish",
  "reply_mode": "normal",
  "reply_text": "今天听起来心情不错。"
}
```

对于发送、保存和删除等动作，`finish.reply_text` 不能承载工具成功状态。最终确认语句由 `ResponsePolicy` 根据工具结果生成。

### 7.2 模型适配方式

Planner 对上层暴露统一接口，底层可以有两种实现：

1. 原生 Function Calling：模型直接返回工具调用，优先采用。
2. 结构化 JSON：用于当前仅返回文本的 Provider，按固定 JSON Schema 解析。

结构化 JSON 解析失败时：

- 最多进行一次格式修复请求。
- 修复仍失败则结束 Agent 回合，不执行任何有副作用的工具。
- 返回可观察错误码，不能根据关键词猜测用户意图后继续执行。

## 8. Tool Registry

### 8.1 工具定义

每个工具统一声明：

```python
ToolSpecification(
    name="send_sticker",
    description="发送当前用户可见的表情包",
    risk_level=ToolRisk.SEND,
    timeout_seconds=5,
    is_idempotent=True,
)
```

注册项还应包含：

- 输入参数模型。
- 输出结果模型。
- 执行处理器。
- 用户权限策略。
- 是否允许主动调用。
- 是否需要前置工具结果。

### 8.2 第一阶段工具

| 工具 | 风险 | 输入 | 输出 | 约束 |
| --- | --- | --- | --- | --- |
| `search_stickers` | `read` | `query`, `limit` | 可见候选列表 | 最多返回 3 个候选 |
| `send_sticker` | `send` | `sticker_id` | 发送状态和 `ContentPart` | 只能使用本轮检索候选，第一阶段最多 1 张 |
| `get_current_time` | `read` | `timezone` | 可靠时间 | 只允许服务端支持的时区 |
| `search_web` | `read` | `query`, `limit` | 来源列表 | 外部内容按不可信资料处理 |

第一阶段重构优先完成表情包工具，再将时间和网络检索迁移到同一注册表。

## 9. 表情包执行流程

### 9.1 用户明确请求表情包

```text
用户：“给我发一个开心的表情包”
  -> Planner: search_stickers(query="开心")
  -> Executor: 返回候选 sticker_id
  -> Planner: send_sticker(sticker_id=候选之一)
  -> Executor: 返回 succeeded + ContentPart
  -> ResponsePolicy: 选择 sticker_sent 文案
  -> AgentTurnResult: reply_text + sticker content_part
```

成功响应示例：

```json
{
  "reply": "给你，这张很适合现在。",
  "content_parts": [
    {
      "type": "sticker",
      "sticker_id": "stk_xxx",
      "url": "/static/stickers/xxx.png"
    }
  ]
}
```

### 9.2 没有匹配结果

```text
search_stickers.status = no_result
  -> 不调用 send_sticker
  -> content_parts 为空
  -> ResponsePolicy 使用 sticker_not_found 文案
```

示例文案：`我这里暂时没有找到合适的表情包。`

### 9.3 发送失败

```text
send_sticker.status = failed
  -> content_parts 为空
  -> ResponsePolicy 使用 sticker_send_failed 文案
  -> 记录 error_code
```

示例文案：`这张刚才没有发出去，你可以再试一次。`

### 9.4 普通聊天中附带表情包

当 Agent 判断普通回复适合附带表情包时：

- LLM 可以生成普通聊天内容。
- 附件仍只来自 `send_sticker` 成功结果。
- 发送状态提示由 `ResponsePolicy` 管理。
- 严肃、安全、医疗、冲突和明显悲伤场景默认禁止主动发送。
- 第一阶段每轮最多附带一张表情包。

## 10. 响应策略

### 10.1 状态文案枚举

建议使用有限的响应类型：

```text
normal_reply
sticker_sent
sticker_not_found
sticker_send_failed
tool_timeout
agent_failed
```

副作用工具的结果文案由服务端模板生成。为了保持 Echo 的性格，可以让 Planner 返回 `tone` 枚举：

```text
concise
gentle
playful
```

`tone` 只能影响措辞，不能改变成功或失败事实。

### 10.2 不再使用关键词纠错

完成迁移后删除：

- `_STICKER_DENIAL_PATTERNS`
- `_denies_sticker_delivery`
- `_correct_sticker_delivery_reply`
- 表情包发送成功后的二次 LLM 纠错请求

对应测试从“是否命中否认关键词”改为“工具状态是否唯一决定回复和附件”。

## 11. 安全与可靠性

### 11.1 调用限制

- 每轮默认最多 6 个 Agent 步骤。
- 每轮默认最多 4 次工具调用。
- 第一阶段最多调用一次 `send_sticker`。
- 达到上限后立即进入 `finalizing`，不得继续循环。

### 11.2 幂等与重复发送

`send_sticker` 使用 `run_id + call_id` 作为幂等键：

- 同一个调用重试时不得产生两个附件。
- HTTP 客户端超时重试时，服务端应能返回同一回合结果或拒绝重复执行。
- 工具调用记录必须包含输入摘要、结果状态和错误码。

### 11.3 超时与降级

- 工具按各自 `timeout_seconds` 单独超时。
- Planner 整体受 `AGENT_RUN_TIMEOUT_SECONDS` 限制。
- 只读工具失败时可以降级为普通聊天。
- 发送类工具失败时必须明确返回失败状态，不能假装成功。
- Agent 异常不能影响聊天接口释放请求锁和记录失败信息。

## 12. 数据与日志

现有表可以继续复用：

- `agent_runs` 保存回合状态、目标、步骤数和最终错误。
- `agent_tool_calls` 保存每次工具调用及结果。

第一阶段建议补充以下可观察字段，是否新增数据库列在实现时再评估：

- `planner_version`
- `final_outcome`
- `sequence_number`
- `risk_level`
- `idempotency_key`

日志至少包含：

```text
run_id
conversation_id
planner_action
tool_name
tool_status
step_count
final_outcome
duration_ms
```

日志不得记录完整 access token、用户隐私原文或表情包二进制内容。

## 13. Chat 与 APP 协议影响

### 13.1 后端

`POST /chat/send` 请求和响应保持兼容：

- `reply` 继续承载文字。
- `content_parts` 继续承载表情包等结构化内容。
- `sources` 继续承载网络检索来源。
- Agent 内部状态不直接暴露给 APP。

`GenerateChatReply` 不再分别调用 `AgentEnrichment` 和 `ChatLLM`，而是接收完整的 `AgentTurnResult`。

### 13.2 APP

第一阶段不需要修改 APP 协议：

- 文字继续显示在气泡中。
- 表情包继续作为独立图片显示。
- Echo 第一阶段最多回复一张表情包。
- 工具失败通过正常文字回复或现有请求错误状态呈现。

## 14. 代码拆分建议

建议新增或调整以下模块：

```text
features/agent/domain/entities.py
  AgentState
  AgentPlan
  AgentToolCall
  AgentToolResult
  AgentTurnResult

features/agent/domain/tools.py
  ToolRegistry
  ToolDefinition

features/agent/application/orchestrate_chat.py
  AgentOrchestrator

features/agent/application/execute_tool.py
  ToolExecutor

features/agent/application/response_policy.py
  AgentResponsePolicy

features/agent/infrastructure/planner.py
  FunctionCallingPlanner
  StructuredJsonPlanner

features/agent/infrastructure/tools/
  sticker_tools.py
  time_tools.py
  web_search_tools.py
```

跨 feature 访问继续通过稳定 public API：

- Agent 不直接访问 stickers repository。
- Sticker 工具通过 `features.stickers.public` 查询和发送。
- Chat 不直接理解任何具体工具参数。

## 15. 实施阶段

### Phase 1：Agent 核心与表情包迁移

- 建立 `AgentState`、Planner、Tool Registry、Executor 和 Response Policy。
- 将 `search_stickers`、`send_sticker` 注册为正式工具。
- 将表情包发送改为完整 Agent 循环。
- 使用结构化工具结果组装 `reply` 和 `content_parts`。
- 删除表情包关键词触发和否认文本正则纠错。
- 保持 `/chat/send` 与 APP 协议不变。

### Phase 2：现有只读能力迁移

- 将 `get_current_time` 迁移到 Tool Registry。
- 将 `search_web` 迁移到 Tool Registry。
- 统一来源、安全提示、超时和调用记录。
- 移除旧 `EnrichChatWithAgent` 中的固定分支。

### Phase 3：长期能力接入

- 接入长期记忆检索和经过确认的记忆写入工具。
- 接入来信查询、创建和状态更新工具。
- 增加主动行为频率限制和风险策略。
- 根据实际复杂度评估 LangGraph 持久化和恢复能力。

## 16. LangGraph 采用策略

第一阶段建议不直接引入 LangGraph，先实现项目内的显式状态机，原因如下：

- 当前核心流程只有少量同步步骤。
- 现有 `agent_runs` 和 `agent_tool_calls` 已满足基础审计需求。
- 显式状态机依赖更少，便于测试工具状态与响应的一致性。
- Planner、Tool Registry 和 `AgentTurnResult` 均设计为可迁移接口。

出现以下需求时再引入 LangGraph：

- 多条条件分支和循环难以通过简单状态机维护。
- 需要暂停后等待用户确认，再恢复同一 Agent 回合。
- 需要跨进程恢复长时间运行任务。
- 需要并行工具、子 Agent 或复杂补偿流程。
- 需要对图节点进行独立持久化、回放和人工介入。

LangGraph 只能负责流程编排，不能替代工具结果作为事实来源，也不能自动消除 LLM 与工具状态冲突。

## 17. 测试方案

### 17.1 Domain 测试

- Planner 合法结果可以转换为 `AgentPlan`。
- 非法工具名、非法参数和越界步骤会被拒绝。
- 工具成功、无结果、失败和超时进入正确状态。
- 发送成功一定包含附件，发送失败一定不包含附件。
- `ResponsePolicy` 的文案语义与工具状态固定一致。

### 17.2 Application 测试

- 用户明确要求表情包时依次执行搜索和发送。
- 旧会话中存在“不能发送图片”的历史内容时，成功结果仍返回正确文案和附件。
- 没有匹配候选时不调用发送工具。
- 无权限 `sticker_id` 无法发送。
- Planner 输出损坏时不执行副作用工具。
- 同一 `call_id` 重试不会产生重复附件。
- 达到步骤或工具调用上限后正确结束。

### 17.3 API 与回归测试

- `/chat/send` 现有文字聊天协议不变。
- 用户发送表情包后 Echo 必须回复。
- Echo 工具发送成功后文字和图片保持一致。
- APP 继续将文字和图片分开显示。
- 语音聊天、长期记忆提取和关系记录不回归。
- 后端全量测试通过。
- `flutter analyze` 为 0，`flutter test` 全部通过。

## 18. 验收标准

- 表情包是否发送只由 `send_sticker` 的结构化结果决定。
- 表情包发送链路不再依赖“表情包”等关键词触发工具。
- 表情包发送链路不存在否认语句关键词或正则纠错。
- 工具成功时，回复必定包含一张合法附件和成功状态文案。
- 工具失败时，回复不得包含附件，也不得宣称发送成功。
- 每次 Agent 回合和工具调用均可通过 `run_id` 追踪。
- 工具权限、超时、步骤限制和幂等策略有自动化测试。
- `/chat/send` 及 APP 现有展示行为保持兼容。
- 所有后端和 Flutter 检查通过。

## 19. 已确认事项

1. 第一阶段采用项目内显式状态机，不立即引入 LangGraph。
2. 当前 Provider 优先接入结构化 JSON Planner；具备原生 Function Calling 后切换对应适配器。
3. 发送、保存、删除等副作用工具使用服务端受控文案，LLM 只选择 `tone`，不能自由描述执行结果。
4. Phase 1 只迁移表情包工具，时间和网络检索放在 Phase 2。
5. 第一阶段每轮最多发送一张表情包，保持现有 APP 协议不变。
6. 完成迁移后删除现有表情包关键词触发和正则纠错逻辑。

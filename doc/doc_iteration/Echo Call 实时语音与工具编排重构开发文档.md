# Echo Call 实时语音与工具编排重构开发文档

> 状态：已完成本地实现与自动化验证，待真机验收和部署  
> 日期：2026-08-16  
> 适用范围：Echo 后端、APP 语音通话、Echo 硬件语音  
> 依赖基线：统一 Chat/Agent、流式 LLM、流式 TTS、腾讯 ASR、Tavily 兼容搜索  
> 架构约束：遵守 `doc/Echo 后端架构与代码规范.md`

## 1. 结论

Call 不应完整复制文字聊天的重型流程，也不应永久关闭所有工具。目标是把实时语音拆成两条明确路径：

```text
普通通话
  -> 不携带工具定义
  -> 精简上下文
  -> LLM 流式短回复
  -> TTS 尽快播放

需要外部能力的通话
  -> Call 路由只开放本轮需要的工具白名单
  -> Agent 通过原生 function calling 决定是否调用
  -> 工具调用确定后先播放一条自然进度语
  -> 工具执行与进度语 TTS 并行
  -> 根据真实工具结果流式生成最终回答
```

第一版 Call 工具范围：

| 能力 | Call 是否支持 | 实现方式 |
| --- | --- | --- |
| 普通聊天 | 支持 | 无工具快速路径 |
| 当前日期、时间、星期、时段 | 支持 | 服务端确定性上下文，不调用工具 |
| 网络搜索 | 支持 | `search_web` |
| 创建定时任务 | 支持 | `create_chat_schedule` |
| 查询定时任务 | 支持 | `list_chat_schedules` |
| 取消定时任务 | 支持 | `list_chat_schedules` + `cancel_chat_schedule` |
| 表情包 | 不支持 | Call 永久禁止 |
| 主动聊天 | 不在本轮通话内触发 | 继续由后台任务处理 |
| 每日来信、图片生成 | 不支持 | 继续走各自异步业务链路 |

不引入 LangGraph。现有有限步骤 Agent、Tool Registry、参数校验、执行器和运行轨迹足以承担第一版工具编排。

## 2. 当前实现事实

### 2.1 已完成的 Call 瘦身

当前本地工作区已经完成并通过测试的 Call 基础调整包括：

- 通话历史只保留最近 `8` 条用户/助手纯正文。
- 清除历史中的 `[消息时间 ...]`、会话边界和附件协议。
- 普通通话不读取摘要；只有明确提到“还记得、上次聊过”等内容时才补充扩展上下文。
- 每轮保留服务端确定的本地日期、时间、星期、时段和时区，但不把技术格式暴露给用户。
- Call 使用独立的 `CALL_MAX_TOKENS=256` 和 `CALL_HISTORY_MESSAGES=8`。
- Call 使用 `CALL_REPLY_MAX_CHARS=80` 的确定性交付上限；超过时优先在完整句子边界结束。
- 提示词改为一至两句、普通回复尽量不超过约五十个汉字的口语表达。
- 流式短句进入 TTS 前执行交付门禁，拦截 JSON、内部字段和时间标记。
- 实际播放的流式文字用于最终落库，避免“用户听到的内容”和“聊天记录”不一致。

这部分解决的是上下文污染和普通通话延迟，不等于工具能力已经开放。

### 2.2 Call 工具当前实际不可用

当前代码存在两层关闭：

1. `features/agent/infrastructure/container.py` 中 `get_call_agent()` 使用空 `ToolRegistry`。
2. `features/agent/public.py` 对 `conversation_mode == "call"` 强制传入 `tools_enabled=False`。

硬件侧虽然传入 `ECHO_DEVICE_TOOLS_ENABLED`，但随后仍被 Agent public 层覆盖。因此当前无论 APP 通话还是硬件通话，都不会收到任何 function tool 描述，也不可能调用搜索或定时任务。

### 2.3 搜索当前实际状态

后端已经存在：

- `providers/web_search_provider.py`：Tavily 兼容 Provider。
- `features/agent/infrastructure/tools/web_search_tools.py`：`search_web` 工具。
- 搜索结果来源结构、超时、最大结果数和 Agent Tool Result。
- 文字聊天 Agent 中的搜索工具注册。

但默认配置为：

```dotenv
WEB_SEARCH_ENABLED=false
WEB_SEARCH_API_KEY=
```

因此当前搜索 Provider 会返回空结果。即使先配置搜索，当前也只会对文字聊天生效；Call 必须完成本文重构后才能使用。

## 3. 重构目标

### 3.1 产品目标

1. 普通通话保持低延迟，不因为少量工具能力而每轮携带全部工具。
2. 用户明确询问新闻、最新信息或要求联网核实时，Echo 可以搜索后回答。
3. 用户通过语音设置、查询和取消提醒时，复用现有持久化定时任务。
4. 工具需要等待时先给出一句自然、真实的进度语，避免长时间无声。
5. APP 通话和硬件通话共享完全相同的 Call 业务规则。
6. 最终回答、聊天记录、来源和任务执行结果保持一致。
7. 工具失败时准确说明，不编造已经搜索、已经创建或已经取消。

### 3.2 非目标

1. 不在 Call 中发送表情包或图片。
2. 不展示模型思维链、隐藏推理、工具参数或内部执行日志。
3. 不做无限步骤自主 Agent；每轮仍有严格步骤、调用次数和总超时。
4. 不把新闻、天气、股价等事实写死在提示词中。
5. 不为第一版增加第二个 LLM 或独立 Agent 微服务。
6. 不修改固件协议；进度语和最终回答继续复用现有文字/TTS/音频队列。

## 4. 目标数据流

### 4.1 统一入口

APP 通话和硬件语音最终都应进入同一个用例：

```text
PCM 音频
  -> ASR final 文本
  -> send_chat_message(conversation_mode="call")
  -> Call Context Builder
  -> CallToolIntentRouter
  -> Call Agent
  -> 流式文字门禁
  -> 流式 TTS
  -> 保存用户消息与 Echo 最终回复
  -> APP 聊天记录/SSE 同步
```

设备适配层不再各自决定“是否允许工具”，工具能力由 Call 应用层按本轮意图统一决定。

### 4.2 普通通话快速路径

示例：

```text
用户：我今天有点累。
Echo：听起来今天消耗不小。是事情太多，还是心里一直没松下来？
```

流程：

```text
路由结果 fast_chat
  -> allowed_tool_names=()
  -> 模型从第一个 delta 开始流式输出
  -> SentenceChunker 形成自然短句
  -> TTS 与后续 LLM 输出并行
```

该路径不能因为工具重构增加额外 LLM 分类调用。

### 4.3 当前时间直接回答

示例：

```text
用户：现在几点了？
Echo：现在是晚上十点四十。
```

当前本地日期、时间、星期、时段和时区由服务端每轮确定性注入。Call 不需要为了回答当前时间再执行 `get_current_time`，从而省去一次 Agent 工具循环。

这里不是“取消时间能力”，而是把稳定、低成本的信息作为可信上下文直接提供。

### 4.4 网络搜索路径

示例：

```text
用户：我想知道今天有什么新闻。
Echo：好，我看看今天发生了什么。
Echo：今天比较受关注的有三件事……
```

流程：

```text
CallToolIntentRouter -> web_search
  -> 本轮只向模型提供 search_web
  -> 模型返回合法 function call
  -> 后端确认调用真实存在且参数校验通过
  -> on_progress_text("好，我查一下今天的新消息。")
  -> 进度语 TTS 与 Tavily 请求并行
  -> 搜索结果作为不可信外部资料回传 Agent
  -> 移除工具定义，流式生成最终回答
  -> 最终正文和 sources 落库
```

只有合法工具调用形成后才能播报“我查一下”。模型仅仅在文字中声称要搜索，不算工具调用。

### 4.5 定时任务路径

示例：

```text
用户：明天早上八点提醒我带伞。
Echo：好，我先把时间确认一下。
Echo：设置好了，明天早上八点提醒你带伞。
```

流程：

```text
CallToolIntentRouter -> schedule_create
  -> 服务端解析“明天早上八点”的绝对本地时间
  -> 本轮只开放 create_chat_schedule
  -> 工具按当前 user_id 创建持久化任务
  -> 成功后生成自然确认
```

时间不完整时不得猜测：

```text
用户：晚上提醒我。
Echo：可以，今晚几点提醒你？
```

查询和取消任务允许最多两次工具调用：先列出当前用户任务，再按稳定 `schedule_id` 取消。所有工具继续服从用户隔离，用户 A 不得读取或取消用户 B 的任务。

## 5. Call 工具路由

### 5.1 路由契约

建议新增纯应用层结构：

```python
class CallToolMode(str, Enum):
    FAST_CHAT = "fast_chat"
    WEB_SEARCH = "web_search"
    SCHEDULE_CREATE = "schedule_create"
    SCHEDULE_MANAGE = "schedule_manage"


@dataclass(frozen=True)
class CallToolRoute:
    mode: CallToolMode
    allowed_tool_names: tuple[str, ...]
    maximum_tool_calls: int
    progress_kind: str | None = None
```

推荐映射：

| 路由 | 可见工具 | 最大工具调用 |
| --- | --- | ---: |
| `fast_chat` | 无 | 0 |
| `web_search` | `search_web` | 1 |
| `schedule_create` | `create_chat_schedule` | 1 |
| `schedule_manage` | 首轮仅 `list_chat_schedules`；有候选后仅 `cancel_chat_schedule` | 2 |

### 5.2 路由职责

路由器只负责缩小能力边界，不负责生成最终答案，也不直接执行工具。

第一版采用确定性高置信规则处理明确意图：

- “查一下、搜一下、最新、今天的新闻、网上有没有、帮我核实”进入搜索候选。
- “提醒我、叫我、设置提醒”进入创建任务候选。
- “有哪些提醒、取消提醒、删掉任务”进入任务管理候选。
- 当前时间、日期、星期直接使用可信时间上下文。
- 其余输入进入 `fast_chat`。

这层关键词不是替代 Agent 的语义理解，而是控制“本轮允许模型看到哪些高权限能力”。进入某一候选后，是否调用以及参数如何填写，仍由原生 function calling 决定。

第一版不增加单独的 LLM 路由调用。若后续真实语料证明确定性路由漏判明显，再用独立的小型分类器补充，不在普通通话主链路无条件增加一次模型请求。

### 5.3 Registry 改造

`get_call_agent()` 不再使用空 Registry，改为注册 Call 允许的候选工具：

```text
search_web
create_chat_schedule
list_chat_schedules
cancel_chat_schedule
```

同时：

- `send_sticker` 不注册到 Call Registry。
- 每轮通过 `allowed_tool_names` 过滤 model descriptions。
- Tool Executor 仍再次检查 `allowed_modes`，防止模型伪造工具名绕过路由。
- 定时任务工具的 `allowed_modes` 增加 `call`。
- `search_web` 显式声明允许 `chat`、`call`，不依赖默认值表达安全边界。

## 6. 进度语设计

### 6.1 用户可见内容

进度语是可以验证的执行状态，不是思维链。

允许：

- “好，我查一下今天的新消息。”
- “好，我先确认一下这个提醒。”
- “我看看你现在有哪些提醒。”

禁止：

- 输出“我正在分析你的意图”或模型内部判断过程。
- 在工具成功前说“已经查到了”或“已经设置好了”。
- 输出工具名、参数、JSON、call id、Provider 名称或异常堆栈。
- 搜索尚未执行时声称某项外部事实是真的。

### 6.2 生成方式

第一版优先使用后端确定性模板，不额外调用一次 LLM：

```text
search_web            -> 好，我查一下。
create_chat_schedule  -> 好，我先确认一下这个提醒。
list_chat_schedules   -> 我看看你现在的提醒。
cancel_chat_schedule  -> 好，我确认一下要取消的提醒。
```

可以根据已校验的搜索主题做有限填充，但总长度不超过 40 个中文字符、最多一句。禁止把未经清洗的完整用户输入直接拼进系统话术。

### 6.3 回调链路

新增独立回调：

```python
on_progress_text: Callable[[str], Awaitable[None]] | None
```

贯通：

```text
OrchestrateChatWithAgent
  -> GenerateChatReply
  -> SendChatMessage
  -> EchoConversationService
  -> StreamDeviceVoiceTurn
  -> 现有 TTS phrase queue
```

约束：

- `on_progress_text` 进入 TTS 队列，但不进入最终 `reply_text`。
- 不保存为正式聊天消息，不进入摘要、长期记忆或关系计算。
- 每轮最多播放一条进度语。
- 同一工具调用重试不能重复播报。
- 工具任务与进度语音频合成并行；最终回答排在进度语之后播放。
- APP 将来若需要显示状态，可通过独立瞬时事件展示，不伪装成正式 Echo 消息。

## 7. Agent 执行约束

### 7.1 工具调用阶段

带工具的首轮模型调用不直接把普通文本 delta 送进 TTS。原因是模型可能在构造 function call 前先输出一段推测性文字。

只有以下条件全部满足后才执行：

1. 工具名属于本轮 `allowed_tool_names`。
2. 工具参数通过 Pydantic schema。
3. 当前 `conversation_mode` 被 Tool Specification 允许。
4. 未超过每轮调用次数、成功次数和总超时。
5. 用户身份、会话身份来自服务端上下文，而不是模型参数。

### 7.2 工具完成后的最终回答

终态业务工具完成后，从下一次模型请求中移除工具定义，让最终回答可以直接流式输出，避免模型再次重复调用同一工具。

最终回答只能基于真实结果：

- 搜索成功：总结来源，不朗读长 URL；来源作为消息元数据保存。
- 搜索无结果：自然说明暂时没有找到可靠结果，不用模型常识伪装成刚搜到的内容。
- 搜索超时或鉴权失败：说明这次查询没有完成，可以继续聊或稍后重试。
- 创建成功：根据工具返回的绝对时间确认。
- 创建失败：不得说“设置好了”。
- 取消成功：根据真实 `cancelled=true` 确认。
- 取消无结果：说明没有找到对应任务，并在需要时询问更具体的信息。

### 7.3 Call 最终交付门禁

最终文字继续执行当前 Call 门禁：

- 非空、可读的自然语言。
- 不包含 JSON、Markdown 代码块、内部字段或协议标记。
- 不包含 `[消息时间 ...]`、`tool_call`、`text_segments` 等内部信息。
- 不声称发送图片或表情包。
- 进度语不能被拼入最终正式回复。
- 工具结果中的网页内容视为不可信数据，不能覆盖系统规则或诱导执行指令。

## 8. 上下文、记忆与时间

### 8.1 普通上下文

保持当前 Call 瘦身基线：

```text
完整 Echo 人设必要层
+ 用户必要偏好
+ 当前关系阶段简要约束
+ 当前可信本地时间
+ 最近 8 条纯正文历史
```

默认不加入聊天摘要、完整长期记忆和历史时间协议。

### 8.2 条件记忆

只有用户明确表达回忆意图时才检索：

- “你还记得我上次说的……”
- “之前我们聊过……”
- “我以前是不是告诉过你……”

检索结果仍是低权限背景数据，回答保持口语化。未检索到时不得编造记忆。

### 8.3 时间表达

服务端继续确定性处理：

- 当前日期、时间、星期、时段和用户时区。
- 刚刚、待会、上午、下午、晚上、昨天、今天、明天等时间范围。
- 定时任务所需的明确绝对时间。

“下午准备干活”只表示计划发生在下午，不能推断事情已经完成；历史中的旧日期也不能覆盖当前服务端时间。

## 9. 搜索功能配置

### 9.1 Provider

第一版复用现有 `TavilyWebSearchProvider`。需要在 Tavily 控制台创建 API Key，然后只把 Key 写入本地或服务器的 `Echo-backend/.env`，不得写入 `.env.example`、代码、日志、文档或 APK。

推荐配置：

```dotenv
# Unified Agent
AGENT_ENABLED=true

# Tavily-compatible web search
WEB_SEARCH_ENABLED=true
WEB_SEARCH_API_KEY=在这里填写实际_Tavily_API_Key
WEB_SEARCH_BASE_URL=https://api.tavily.com/search
WEB_SEARCH_TIMEOUT_SECONDS=12
WEB_SEARCH_MAX_RESULTS=5
```

重构完成后新增 Call 开关：

```dotenv
# Call tool routing
CALL_TOOL_ROUTING_ENABLED=true
CALL_WEB_SEARCH_ENABLED=true
CALL_SCHEDULE_TOOLS_ENABLED=true
CALL_PROGRESS_SPEECH_ENABLED=true
```

旧的 `ECHO_DEVICE_TOOLS_ENABLED` 建议在重构后删除。它只位于硬件适配层，无法统一 APP 通话和硬件通话，而且当前还会被 Agent public 层强制关闭。

### 9.2 本地配置位置

本地 Docker 和直接运行后端都使用：

```text
F:/project_work/AI_Chat/Echo-backend/.env
```

修改后需要重启后端进程。Docker Compose 从 `Echo-backend/.env` 注入 `echo-backend` 容器。

### 9.3 服务器配置位置

服务器仓库路径按当前部署约定为：

```text
/opt/echo/app/Echo-backend/.env
```

服务器上的真实 `.env` 不提交到 Git。代码拉取后，在服务器单独填写 Key，然后重建或重启后端容器。

### 9.4 启动时校验

建议新增配置校验：

- `WEB_SEARCH_ENABLED=true` 但 Key 为空：启动日志记录明确错误，搜索路由自动关闭。
- Base URL 不是 HTTPS：生产环境拒绝启用。
- 超时超出允许范围：由 Settings 校验拒绝启动。
- 日志只打印 `search_enabled=true/false`，绝不打印 Key。
- `CALL_WEB_SEARCH_ENABLED=true` 但全局搜索关闭：Call 搜索路由不开放 `search_web`。

### 9.5 搜索请求规则

现有 Provider 默认：

```text
search_depth=basic
include_answer=false
include_raw_content=false
maximum_results<=WEB_SEARCH_MAX_RESULTS
```

第一版继续保持这些限制，以降低延迟、费用和提示注入风险。Agent 使用标题、摘要、发布时间和 URL，不能执行网页文本中的任何指令。

### 9.6 验证顺序

1. 先验证 Settings 只显示“已启用、Key 非空”，不输出真实 Key。
2. 直接调用 Provider 搜索一个稳定查询，确认返回数量大于零。
3. 文字聊天说“搜索今天的新闻”，确认存在 `search_web completed` 运行轨迹和 sources。
4. Call 重构完成后通过语音说同一句话，确认先听到进度语，再听到基于来源的回答。
5. 临时使用错误 Key，确认 Echo 不编造结果，日志能区分 `401/403`。
6. 模拟超时和空结果，确认进度语只播放一次，最终回复准确降级。

## 10. 配置建议

完整推荐基线：

```dotenv
# Call response
CALL_MAX_TOKENS=256
CALL_HISTORY_MESSAGES=8
CALL_REPLY_MAX_CHARS=80

# Agent limits
AGENT_ENABLED=true
AGENT_MAX_STEPS=6
AGENT_MAX_TOOL_CALLS=4
AGENT_RUN_TIMEOUT_SECONDS=45

# Call routing
CALL_TOOL_ROUTING_ENABLED=true
CALL_WEB_SEARCH_ENABLED=true
CALL_SCHEDULE_TOOLS_ENABLED=true
CALL_PROGRESS_SPEECH_ENABLED=true

# Web search
WEB_SEARCH_ENABLED=true
WEB_SEARCH_API_KEY=
WEB_SEARCH_BASE_URL=https://api.tavily.com/search
WEB_SEARCH_TIMEOUT_SECONDS=12
WEB_SEARCH_MAX_RESULTS=5
```

Call 本身使用更严格的运行时上限，不直接沿用文字聊天的四次工具额度：

- 搜索：最多 1 次。
- 创建任务：最多 1 次。
- 查询并取消任务：最多 2 次。
- 进度语：最多 1 条。
- 表情包：0 次。

## 11. 代码改造范围

已新增：

```text
Echo-backend/features/agent/domain/call_routing.py
Echo-backend/features/agent/application/call_progress.py
Echo-backend/features/chat/application/call_reply_limiter.py
Echo-backend/features/devices/application/transcript_guard.py
```

已修改：

```text
Echo-backend/features/agent/domain/tools.py
  - 支持按 allowed_tool_names 输出工具描述

Echo-backend/features/agent/application/orchestrate_chat.py
  - 接收 CallToolRoute
  - 增加 on_progress_text
  - 工具成功后收口到无工具流式最终回答

Echo-backend/features/agent/infrastructure/container.py
  - 为 get_call_agent 注册搜索和定时任务工具

Echo-backend/features/agent/infrastructure/tools/web_search_tools.py
  - 显式 allowed_modes=("chat", "call")

Echo-backend/features/agent/infrastructure/tools/schedule_tools.py
  - 定时任务工具允许 call

Echo-backend/features/agent/public.py
  - 删除 call 强制 tools_enabled=False
  - 根据配置和路由传递白名单

Echo-backend/features/chat/application/generate_reply.py
Echo-backend/features/chat/application/send_message.py
Echo-backend/features/chat/public.py
Echo-backend/features/devices/infrastructure/adapters.py
Echo-backend/features/devices/application/stream_voice_turn.py
  - 贯通 on_progress_text

Echo-backend/shared/config/settings.py
Echo-backend/.env.example
  - 增加 Call 工具路由配置并删除旧硬件专用开关
```

APP 通话入口不需要新增一套 Agent。它继续调用 `conversation_mode="call"`，后端即可获得相同行为。

## 12. 测试计划

### 12.1 单元测试

- 普通闲聊路由为 `fast_chat`，模型调用不含 tools。
- 当前时间问题直接使用可信时间上下文，不调用工具。
- 明确新闻查询只暴露 `search_web`。
- 搜索模型没有返回 function call 时不得伪造搜索进度和搜索结果。
- 合法搜索调用只播放一次进度语。
- 搜索成功后 sources 来自 Tool Result。
- 搜索空结果、超时、401、429 均有准确降级。
- 创建提醒只暴露创建工具，模糊时间不创建。
- 查询取消最多两次工具调用并保持用户隔离。
- Call 永远不暴露 `send_sticker`。
- 进度语不进入正式回复、数据库、摘要和记忆。
- 最终回复门禁能拦截 JSON、`[消息时间]` 和内部字段。
- Call 超长正文只交付到自然句边界，并保证 TTS 正文与数据库正文一致。
- 实时 ASR 返回与音频时长明显不相称的文本时回退整段识别；整段仍异常则拒绝入库。
- CosyVoice 首次无音频或限流失败只重试一次，流结束和异常路径都只发送一次 `tts stop`。
- 搜索空结果或执行失败时使用确定性降级，模型不能声称已经查到结果。

### 12.2 集成测试

- APP Call 和硬件 Call 对同一输入得到相同工具路由。
- 进度 TTS 与工具请求并行，最终音频严格排在进度语之后。
- 工具执行期间断开设备不会产生重复任务。
- 使用相同 `request_id` 重试时保持幂等，不重复创建提醒。
- 最终落库文本与用户实际听到的最终正文一致。

### 12.3 全量门禁

```text
pytest 全量通过
Ruff 通过
Python compile 通过
架构检查通过
git diff --check 通过
```

### 12.4 性能验收

- 普通 Call 不增加额外 LLM 路由调用，首 delta 不应出现明显回退。
- 搜索 Call 在工具完成前必须先开始播放进度语。
- 进度语不等待搜索完成才合成。
- 记录 ASR final、路由完成、tool call 确认、进度 TTS 首包、工具完成、最终 LLM first delta、最终 TTS 首包。
- 真实延迟以服务器日志和真机时间线为准，不用单次主观感受代替数据。

## 13. 实施顺序

### 阶段一：路由和白名单

1. 新增 `CallToolRoute` 和确定性路由器。
2. Tool Registry 支持按名称过滤描述。
3. Call Agent 注册搜索和定时任务候选工具。
4. 删除 call 强制关闭工具的逻辑。
5. 保持表情包在 Call 中不可见、不可执行。

### 阶段二：进度语

1. 新增后端确定性进度语生成器。
2. 贯通 `on_progress_text` 回调。
3. 让进度 TTS 与工具执行并行。
4. 保证进度语不落库、不进入记忆。

### 阶段三：搜索配置与降级

1. 配置 Tavily API Key。
2. 增加启动配置校验和安全日志。
3. 完成搜索成功、无结果、超时、鉴权和限流测试。
4. 验证 sources 落库和 APP 历史兼容。

### 阶段四：定时任务

1. 扩展定时工具的 Call mode。
2. 接入确定性时间解析。
3. 验证创建、查询、取消和幂等。
4. 验证 Call 中创建的任务仍由现有后台 Worker 执行。

### 阶段五：真机验收

1. APP 通话验证普通聊天、时间、搜索和提醒。
2. Echo 硬件验证同一组用例。
3. 对齐完整延迟时间线。
4. 确认无内部标记、无 JSON、无表情包、无重复任务。

## 14. 发布与回滚

### 14.1 发布策略

先在服务器启用搜索 Provider，但保持 Call 路由关闭：

```dotenv
WEB_SEARCH_ENABLED=true
CALL_TOOL_ROUTING_ENABLED=false
```

确认文字聊天搜索稳定后，再开启 Call：

```dotenv
CALL_TOOL_ROUTING_ENABLED=true
CALL_WEB_SEARCH_ENABLED=true
CALL_SCHEDULE_TOOLS_ENABLED=false
```

搜索真机通过后，最后开启定时任务工具。

### 14.2 回滚

出现工具延迟或稳定性问题时：

```dotenv
CALL_TOOL_ROUTING_ENABLED=false
```

Call 立即退回普通无工具流式路径，不影响文字聊天、主动聊天、每日来信和已有定时任务 Worker。

搜索 Provider 本身异常时：

```dotenv
WEB_SEARCH_ENABLED=false
```

关闭后不得继续向 Call Agent 暴露 `search_web`。

## 15. 最终验收场景

| 用户语音 | 预期行为 |
| --- | --- |
| “你今天怎么样？” | 无工具，直接流式口语回复 |
| “现在几点？” | 使用服务端时间直接回答，无工具 |
| “今天星期几？” | 使用服务端时间直接回答，无工具 |
| “查一下今天有什么新闻” | 一条进度语、一次搜索、基于来源回答 |
| “网上核实一下这件事” | 仅开放搜索，由 function calling 决定查询参数 |
| “明天八点提醒我带伞” | 创建一次性任务并确认绝对时间 |
| “晚上提醒我” | 不猜时间，先询问具体几点 |
| “我有哪些提醒？” | 查询当前用户任务 |
| “取消明天的提醒” | 查询后取消准确任务；有歧义时先澄清 |
| “给我发个表情包” | Call 不调用图片工具，自然说明通话里先继续说 |
| 搜索超时 | 不编造结果，准确说明本次查询未完成 |
| 工具调用期间设备断开 | 不重复创建任务，运行轨迹可审计 |

## 16. 审核结论

本重构的核心不是让 Call 携带更多能力，而是让每一轮只携带真正需要的能力：

```text
低延迟普通通话
+ 确定性时间上下文
+ 按意图开放的最小工具白名单
+ 可验证的进度语
+ 基于真实工具结果的最终回答
```

这样既保留实时语音的响应速度，也为新闻搜索、定时任务以及后续更多工具建立统一、可控的扩展方式。

## 17. 2026-08-16 实施结果

### 17.1 生产日志定位

本次卡顿不是 WebSocket 建连失败，而是上一轮长期占用半双工播放状态：

- 最近普通轮次从 ASR final 到 LLM first delta 约 `1.58s`，到首包音频约 `2.36s`。
- 旧的 `18` 字 TTS 分片会把一次回答拆成约 `6～10` 个 CosyVoice 请求。
- 当前片段加两个预取形成最多三路并发，生产日志出现 `Throttling.RateQuota`。
- 一轮回复因此可能占用 `10～20s`，设备在收到可靠 `tts stop` 前不能进入下一轮。
- 另有一次约 `3.7s` 音频得到约 `760` 字 ASR 文本，明显是背景音污染，不应进入聊天和记忆。

### 17.2 已落地稳定性参数

```dotenv
CALL_REPLY_MAX_CHARS=80
ECHO_DEVICE_TTS_CHUNK_MAX_CHARS=32
ECHO_DEVICE_TTS_CHUNK_MIN_CHARS=12
ECHO_DEVICE_TTS_PREFETCH_PHRASES=1
COSYVOICE_MAX_CONCURRENT_STREAMS=2
```

这些参数共同减少单轮 TTS 请求数和半双工占用时间。回复长度门禁约束的是用户实际听到并最终落库的正文，不会出现播放短文、数据库保存长文的分叉。

### 17.3 当前启用策略

Call 工具路由默认仍关闭，部署时按能力逐步开启：

```dotenv
CALL_TOOL_ROUTING_ENABLED=false
CALL_WEB_SEARCH_ENABLED=false
CALL_SCHEDULE_TOOLS_ENABLED=false
CALL_PROGRESS_SPEECH_ENABLED=true
```

没有真实 Tavily Key 时不得开启 Call 搜索。普通 Call、可信本地时间和 ASR/TTS 稳定性修复不依赖搜索配置。

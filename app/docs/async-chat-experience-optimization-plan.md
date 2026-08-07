# Echo 异步聊天与多段回复优化开发方案

> 状态：待审核，尚未开始功能重构
>
> 日期：2026-08-06
>
> 适用范围：Android APP 文字聊天、用户表情包消息、统一 Agent 回复、聊天历史与实时消息交付
>
> 不适用范围：语音通话。通话继续使用现有同步 ASR -> Agent -> TTS 链路，继续禁用表情包工具。
>
> 关联文档：`unified-agent-runtime-refactor-plan.md`、`sticker-sending-plan.md`、`../../doc/Echo v1.0 业务流程与数据流.md`

## 1. 背景

Echo 当前聊天已经具备以下能力：

- 文字消息发送与统一 Agent 回复。
- 用户和 Echo 独立发送表情包。
- Agent 在同一个模型回路中调用时间、网络搜索和表情包工具。
- 聊天消息、附件、摘要和长期记忆持久化。
- 最近 10 条历史加载和向前分页。

改造前的交互采用传统同步请求模型：

```text
用户发送一条消息
  -> APP 加入用户消息和 typing 占位
  -> POST /chat/send
  -> 后端构建上下文
  -> Agent 完整运行
  -> 工具执行
  -> 生成最终单段文字
  -> 用户消息和 Echo 回复一起写入数据库
  -> HTTP 返回
  -> APP 替换 typing 占位
```

这一模型能保证一问一答的顺序，但无法提供接近微信的连续聊天体验。

## 2. 当前问题与代码证据

### 2.1 APP 使用全局忙碌状态锁住聊天

当前 `ChatState.isBusy` 包含 `isSending`，并被以下流程共同使用：

- `ChatController.sendMessage` 在忙碌时直接拒绝发送文字。
- `ChatController.sendSticker` 在忙碌时直接拒绝发送表情包。
- 聊天页 `_send` 在忙碌时不读取输入。
- 表情包面板在忙碌时不能打开。
- 输入区发送按钮在 `isSending` 时显示“等待”并禁用。

因此用户必须等待 Echo 完整回复后才能继续发送。

### 2.2 后端主动拒绝同一用户的第二个请求

`SendChatMessage` 使用 `ChatRequestGuard` 保证同一用户只有一个请求正在处理。上一条消息尚未完成时，下一条请求返回 `409 ChatRequestInProgressError`。

这个门禁保护了消息顺序、Agent 工具额度和数据库写入，但它的语义是“拒绝并发”，不是“接受并排队”。仅解除 APP 按钮限制会把问题从 UI 转移成大量 `409`，不能形成连续聊天。

### 2.3 用户消息保存得太晚

当前 `GenerateChatReply` 先完成 Agent，再通过 `add_chat_turn` 原子写入用户消息和单条 assistant 消息。

这意味着：

- Agent 处理期间，服务器聊天历史中还没有这条用户消息。
- 请求超时、APP 退出或服务器重启时，用户已经看到的本地消息可能没有被服务端保存。
- 后端无法先确认“消息已收到”，再异步生成 Echo 回复。

### 2.4 返回协议只能自然表达一条 Echo 消息

当前 `ChatResponse` 主要包含：

```text
reply: 单段文字
content_parts: 可选表情包和其他结构化内容
sources: 可选来源
```

APP 将 `reply` 和第一张表情包映射为同一个 `ChatMessage`。虽然 UI 可以把图片画在气泡外，但数据上仍然是一条 assistant 消息，无法稳定表达：

```text
Echo：我在呀。
Echo：今天发生什么了？
Echo：[表情包]
```

### 2.5 HTTP 生命周期同时承担接收、推理和交付

`POST /chat/send` 只有在 Agent、工具、持久化和可选后处理全部结束后才返回。接收用户消息和生成 Echo 回复没有解耦，因此 APP 只能把一次 HTTP 请求当成一个完整聊天回合。

## 3. 核心结论

本次优化不能只修改发送按钮，也不需要再次更换 Agent 架构。

现有统一 Agent 继续负责：

- 理解一个输入批次中的所有用户消息。
- 决定是否调用时间、搜索、表情包等工具。
- 根据工具事实生成符合 Echo 人格的自然回复。
- 决定回复是一段还是多段。

本次新增的是 Agent 外部的聊天调度与交付能力：

```text
Chat Intake       立即接收和保存用户消息
Chat Scheduler    合并连续消息并串行调度 Agent turn
Agent Runtime     理解、决策、调用工具和生成结构化回复
Chat Delivery     保存多条 Echo 消息并实时推送给 APP
```

LangGraph 不是本次重构的必要条件。只有未来出现跨分钟暂停恢复、人工确认节点、复杂补偿或多个子 Agent 时，才重新评估图状态机框架。

## 4. 目标

### 4.1 用户体验目标

1. 用户点击发送后，消息立即出现在聊天记录中。
2. Echo 处理期间，用户仍可继续发送文字或表情包。
3. 用户连续发送的多条消息保持独立气泡，但可以被 Agent 作为同一输入批次理解。
4. Echo 可以回复一至三条独立文字消息。
5. Echo 表情包作为独立图片消息展示，不进入文字气泡。
6. Echo 回复期间输入框、发送按钮和表情包入口保持可用。
7. APP 进入后台后，服务器继续处理；重新进入时能够补齐回复。
8. 网络重连不能制造重复消息、重复 Agent turn 或重复表情包。
9. Echo 的“正在输入”和多段消息出现节奏随回复字数自然变化，短回复更快，长回复适当延长，但不重复叠加模型本身已经产生的等待时间。

### 4.2 技术目标

1. 用户消息先持久化，Agent 后运行。
2. 同一会话始终最多运行一个 Agent turn，但允许存在多个待处理消息。
3. 同一设备重复请求使用客户端消息 ID 幂等去重。
4. 消息顺序以服务端消息 ID 为最终事实。
5. Echo 多段回复和表情包由同一个 `AgentTurnResult` 统一交付。
6. APP 通过实时事件接收回复，断线后通过历史接口恢复。
7. 后端重启后能够继续处理数据库中未完成的聊天任务。
8. 聊天摘要、长期记忆、关系进度和每日来信继续基于真实消息工作。
9. 回复节奏由独立 Delivery Timing Policy 计算，不能让 LLM 自由决定任意等待时间，也不能通过 worker `sleep` 阻塞数据库事务。

## 5. 非目标

第一阶段不实现：

- 多人群聊、多个 Echo 角色或会话分支。
- 用户修改、撤回或引用回复。
- Echo 同时运行多个 Agent turn。
- 每条用户碎片都单独调用一次模型。
- 无限制的 Echo 多段回复或一次发送多张表情包。
- 在 APP 本地建立完整聊天数据库。
- 离线状态下长期保存并自动发送聊天正文。
- 语音通话插入聊天异步队列。
- Agent 运行中任意时刻强制中断已经执行的有副作用工具。
- 为聊天并发单独引入 LangGraph、Redis、Kafka 或新的微服务集群。

## 6. 术语与边界

| 术语 | 含义 |
|---|---|
| User Message | 用户实际发送的一条独立文字或表情包消息 |
| Client Message ID | APP 在发送前生成的 UUID，用于重试幂等 |
| Input Batch | 一个短时间窗口内、交给同一次 Agent turn 理解的若干用户消息 |
| Agent Turn | 对一个 Input Batch 执行的一次统一 Agent 运行 |
| Reply Group | 同一次 Agent turn 产生的一组 Echo 消息 |
| Delivery Message | Reply Group 中的一条独立文字、表情包或后续可扩展内容 |
| Context Cutoff | 本次 Agent turn 能看到的最后一条用户消息 ID |
| Typing State | Echo 正在处理的临时 UI 状态，不是一条聊天消息 |

以下关系必须保持：

```text
多个 User Message
  -> 一个 Input Batch
  -> 一个 Agent Turn
  -> 一个 Reply Group
  -> 一至多条 Delivery Message
```

## 7. 总体架构

```text
┌──────────────── Flutter APP ────────────────┐
│ Chat UI                                     │
│  ├─ 本地乐观消息                            │
│  ├─ 单条发送状态                            │
│  ├─ Echo typing 状态                        │
│  └─ SSE 消息接收与历史补齐                  │
└───────────────┬─────────────────────────────┘
                │ POST /chat/messages
                │ GET  /chat/events
                │ GET  /chat/messages
┌───────────────▼─────────────────────────────┐
│ FastAPI                                     │
│  ├─ Chat Intake：校验、权限、幂等、持久化   │
│  ├─ Chat Event Stream：实时交付             │
│  └─ Chat Worker：认领到期批次               │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│ PostgreSQL                                  │
│  ├─ conversations                           │
│  ├─ chat_messages                           │
│  ├─ chat_message_attachments                │
│  └─ chat_turn_jobs                          │
└───────────────┬─────────────────────────────┘
                │ one active turn/conversation
┌───────────────▼─────────────────────────────┐
│ Unified Agent Runtime                       │
│  ├─ Persona / memory / relationship         │
│  ├─ LLM                                     │
│  ├─ time / web / sticker tools              │
│  └─ structured delivery plan                │
└─────────────────────────────────────────────┘
```

## 8. 目标业务流程

### 8.1 用户发送文字

```text
1. APP 生成 client_message_id。
2. APP 立即插入本地用户气泡，状态为 sending。
3. APP 清空输入框，发送按钮继续可用。
4. APP 调用 POST /chat/messages。
5. 后端在一个事务中：
   - 校验用户和消息长度。
   - 按 client_message_id 幂等查重。
   - 将用户消息写入 chat_messages。
   - 创建或追加 collecting 状态的 chat_turn_job。
6. 后端立即返回 202 Accepted 和服务端 message_id。
7. APP 用服务端消息替换本地临时消息，状态变为 sent。
8. Chat Worker 在收集窗口结束后运行 Agent。
9. Reply Group 写入数据库并通过 SSE 推送。
10. APP 按服务端 message_id 插入多条 Echo 消息。
```

正常情况下，步骤 1 至 7 不等待 LLM，目标响应时间应明显短于当前 `/chat/send`。

### 8.2 用户发送表情包

用户点击表情包后：

1. 面板立即关闭。
2. APP 插入独立用户图片消息。
3. 请求只携带 `sticker_id`，不上传二进制。
4. 后端校验表情包属于 Echo 公共库或当前用户私人库。
5. 后端保存 `message_type=sticker` 和对应附件。
6. 描述和语义标签在构建 Agent 输入时转换为可信语义。
7. 该消息可以与收集窗口内相邻的用户文字组成同一个 Input Batch。

Echo 仍然必须对用户表情包产生一次有效回应。回应可以是文字、文字加一张表情包，或在轻量语境中仅回复一张表情包；最终规则见待确认事项。

### 8.3 连续用户消息合并

建议默认参数：

| 参数 | 建议值 | 作用 |
|---|---:|---|
| 静默收集窗口 | 800 ms | 用户停止输入后再启动 Agent |
| 最长收集时间 | 2500 ms | 防止用户持续输入导致 Agent 永不开始 |
| 单批最大消息数 | 8 | 防止队列滥用 |
| 单批最大文字量 | 6000 字符 | 控制模型输入和费用 |

示例：

```text
10:00:00.000 用户：我今天
10:00:00.420 用户：有点累
10:00:01.020 用户：工作出了点问题
10:00:01.820 收集窗口结束
```

数据库保存三条独立消息，Agent 输入保持消息顺序，但三条消息属于同一个 Input Batch。关系进度按一次 Agent turn 计数，不能因为用户拆成三个气泡而增长三次。

若达到最长收集时间、最大消息数或最大文字量，应立即关闭当前批次并开始处理；后续消息进入下一批。

### 8.4 Agent 处理中收到新消息

第一阶段采用确定性最强的规则：

```text
当前 Agent Turn 已经 running
  -> 新用户消息仍立即保存并返回 accepted
  -> 新消息进入下一个 collecting batch
  -> 当前 Agent Turn 不被强制取消
  -> 当前 Reply Group 完成交付
  -> Worker 继续处理下一批
```

这样可以保证：

- 不出现 `409`。
- 不并行竞争历史、工具额度和表情包发送额度。
- 不会在工具已经执行后取消回合，造成“动作发生但回复消失”。
- 数据库顺序和 APP 展示可以稳定恢复。

后续 Phase 2 可以增加“草稿重算”：若新消息在最终回复提交前到达，并且本轮没有成功执行发送类工具，则允许放弃未交付草稿，把新消息合并后重新生成一次。第一阶段不做该优化。

### 8.5 Echo 多段回复

Echo 的多段回复必须来自模型的结构化最终结果，不能在 APP 或后端按句号、换行符机械切割。

建议模型最终协议：

```json
{
  "text_segments": [
    "听起来今天确实挺累的。",
    "工作上发生什么了？"
  ],
  "sticker_placement": "after_text"
}
```

Runtime 校验规则：

- `text_segments` 第一阶段最多 3 条。
- 去除空段、纯空白段和相邻重复段。
- 多段文字总长度继续受聊天回复上限约束。
- `sticker_placement` 只控制已经成功执行的 `send_sticker` 结果放在文字前还是文字后。
- `sticker_id`、URL 和发送成功状态只能来自工具结果，模型不能在最终 JSON 中自行填写。
- 第一阶段每个 Reply Group 最多一张成功表情包。
- 结构化结果非法时允许一次修复请求；仍失败则使用单段文本兜底。
- 严肃、医疗、安全、冲突和知识解释场景不要求拆成多条。
- 普通闲聊也不强制拆分；一条自然回复优于刻意分段。

Runtime 将结果转换为：

```text
ReplyGroup
  delivery[0] = text
  delivery[1] = text
  delivery[2] = sticker
```

每个 delivery 都保存为独立 assistant `chat_messages` 记录，共享同一个 `reply_group_id` 和 `agent_turn_id`。

### 8.6 Echo 消息交付顺序

一个 Reply Group 应在同一个数据库事务中完成以下操作：

1. 写入所有独立 assistant 消息。
2. 写入表情包和来源附件。
3. 为消息分配连续的服务端 ID。
4. 标记 chat turn 为 completed。
5. 提交事务后发送一个包含完整消息数组的 SSE delivery group 事件。

APP 一次收到整个 Reply Group，并按数组顺序插入。可以使用很短的逐条显示动画，但必须先为整个 group 保留确定顺序，避免用户在动画期间发送消息后，历史重新加载发生位置跳动。

消息已经在服务端事务中完整持久化，展示延迟只影响当前前台 APP 的呈现，不修改 `message_id`、`created_at`、数据库顺序或历史恢复结果。

### 8.7 按回复字长模拟打字节奏

Echo 不采用气泡内部逐字打印，而采用更接近微信的表现：

```text
Echo 正在输入
  -> 等待与回复长度匹配的有限时间
  -> 第一条完整气泡出现
  -> 继续保持短暂 typing
  -> 下一条完整气泡出现
```

逐字打印容易造成长内容阅读抖动、Markdown 半成品、URL 和来源闪烁，也不像普通即时通讯的消息发送方式，因此不作为默认方案。

建议由后端 `DeliveryTimingPolicy` 根据 Unicode 字素数量计算展示提示，由 APP 执行动画。推荐初始参数：

| 参数 | 建议值 | 说明 |
|---|---:|---|
| 基础打字时间 | 600 ms | 极短回复也保留轻微自然感 |
| 每有效字素时间 | 32 ms | 中文、英文、数字和 emoji 按 Unicode 字素计数 |
| 目标总打字时间 | 800～4800 ms | 防止过快或因长回复等待过久 |
| 模型实际耗时抵扣 | 100% | Agent 已经花费的可见等待时间计入打字时间 |
| 生成后额外等待上限 | 2500 ms | 即使模型极快也不额外拖延太久 |
| 相邻文字气泡最小间隔 | 300 ms | 避免多段同时闪现 |
| 相邻文字气泡最大间隔 | 1600 ms | 防止多段回复过慢 |
| 表情包额外间隔 | 300 ms | 与相邻文字稍作分离 |

推荐计算原则：

```text
effective_chars = 所有文字段落的 Unicode 字素数
target_typing_ms = clamp(600 + effective_chars * 32, 800, 4800)
remaining_typing_ms = clamp(target_typing_ms - agent_elapsed_ms, 0, 2500)
```

多段回复再根据每一段的字素占比分配 `remaining_typing_ms`，并应用相邻气泡最小、最大间隔。实际参数必须放入配置或纯策略类，后续可以通过真机体验调整，不能散落在 Widget 中。

关键规则：

- 从收到 `chat.typing.started` 开始计算用户已经感知到的等待时间。
- Agent 实际运行 3 秒、目标打字时间 2 秒时，不再追加等待。
- Agent 只运行 300 ms、生成较长回复时，可以补充有限等待。
- typing 在服务端处理结束后，如果 APP 仍有待展示段落，应持续到最后一段出现，不能中间闪退。
- 所有消息在事件到达时已经按服务端顺序保留位置，后续用户消息不会让动画中的旧消息重新排序。
- APP 在后台、SSE 重连、历史补齐或 delivery 事件已经超过 10 秒时，立即展示全部消息，不补演过期打字动画。
- Android 系统关闭动画或 APP 处于无障碍减弱动态效果模式时，可以跳过额外展示延迟。
- 安全提醒、错误提示和需要用户立即处理的系统信息不使用人工延迟。
- 打字节奏只属于 UI 呈现，不影响 Agent 配额、摘要、记忆、推送和消息持久化。

### 8.8 APP 进入后台和重新连接

- 用户消息一旦收到 202，即使 APP 进入后台，服务器仍继续处理。
- SSE 在后台断开不影响 Agent 和持久化。
- APP 回到前台后先恢复历史缺口，再恢复实时流。
- 新 Echo 回复可复用现有推送模块发送不含正文的通知。
- 通知点击进入聊天页后，以历史接口为事实来源，不能只依赖推送 payload。

## 9. API 设计

### 9.1 接收异步聊天消息

新增：

```http
POST /chat/messages
Authorization: Bearer <token>
Content-Type: application/json
```

文字请求：

```json
{
  "client_message_id": "fbd2b3d2-ff52-4ca3-bcd2-a9fb9d86c201",
  "message_type": "text",
  "text": "我今天有点累"
}
```

表情包请求：

```json
{
  "client_message_id": "54a3cbe4-a0c4-48a7-8d8f-c7fb5c0a5bb2",
  "message_type": "sticker",
  "sticker_id": "sticker_xxx"
}
```

成功响应：

```http
202 Accepted
```

```json
{
  "conversation_id": "conv_xxx",
  "message": {
    "message_id": 1024,
    "client_message_id": "fbd2b3d2-ff52-4ca3-bcd2-a9fb9d86c201",
    "role": "user",
    "message_type": "text",
    "content": "我今天有点累",
    "content_parts": [],
    "created_at": "2026-08-06T10:00:00Z"
  },
  "turn": {
    "turn_id": "turn_xxx",
    "status": "collecting"
  }
}
```

幂等规则：

- 同一用户重复提交相同 `client_message_id` 和相同内容，返回已有消息，不重复写入。
- 同一 `client_message_id` 携带不同内容，返回 `409`。
- `client_message_id` 只解决同一条用户消息重试，不再代表整个 Agent 结果缓存。

### 9.2 实时聊天事件

新增：

```http
GET /chat/events?conversation_id=<id>&after_message_id=<id>
Accept: text/event-stream
Authorization: Bearer <token>
```

事件类型：

| 事件 | 说明 |
|---|---|
| `chat.ready` | SSE 已连接，返回当前 conversation 和 cursor |
| `chat.typing.started` | 某个 Agent turn 开始处理 |
| `chat.delivery.created` | 一个完整 Reply Group 已持久化 |
| `chat.turn.failed` | Agent turn 最终失败，没有生成 assistant 消息 |
| `chat.typing.stopped` | 当前 turn 结束、失败或取消 |
| `chat.conversation.reset` | 用户清空聊天，旧流需要刷新 |
| `chat.heartbeat` | 保活事件，不进入 UI |

`chat.delivery.created` 示例：

```json
{
  "turn_id": "turn_xxx",
  "reply_group_id": "reply_xxx",
  "presentation": {
    "agent_elapsed_ms": 1870,
    "initial_delay_ms": 0,
    "message_delays_ms": [0, 620, 300]
  },
  "messages": [
    {
      "message_id": 1025,
      "role": "assistant",
      "message_type": "text",
      "content": "听起来今天确实挺累的。",
      "content_parts": []
    },
    {
      "message_id": 1026,
      "role": "assistant",
      "message_type": "text",
      "content": "工作上发生什么了？",
      "content_parts": []
    },
    {
      "message_id": 1027,
      "role": "assistant",
      "message_type": "sticker",
      "content": "",
      "content_parts": [
        {
          "type": "sticker",
          "sticker_id": "sticker_xxx",
          "url": "https://..."
        }
      ]
    }
  ]
}
```

SSE 只负责低延迟通知，PostgreSQL 消息记录才是最终事实。APP 不能把“收到某个 SSE 事件”当作唯一持久化依据。

`presentation` 是可丢弃的展示提示，不是消息事实。APP 应对数值再次执行上下限校验；字段缺失、非法、重连或历史补齐时直接展示消息。

### 9.3 历史向前分页与向后补齐

现有接口继续支持：

```http
GET /chat/messages?before_id=<id>&limit=10
```

新增向后同步参数：

```http
GET /chat/messages?after_id=<last_message_id>&limit=50
```

规则：

- `before_id` 用于加载更早历史。
- `after_id` 用于 SSE 重连后补齐新消息。
- 两者不能同时出现。
- APP 按服务端 `message_id` 去重。
- SSE 重连后先补齐 `after_id`，再继续实时接收。

### 9.4 协议边界

当前 APK 尚未发布，不保留旧文字聊天协议兼容层：

- 新文字和表情包消息只通过 `POST /chat/messages` 接收。
- Echo 回复只通过 `GET /chat/events` 和 `after_id` 补齐交付。
- `POST /chat/send` 只服务语音通话，schema 只接受 `mode=call`。
- 后端不实现 `/chat/send mode=chat` 适配器，也不维护第二条文字 Agent 链路。

同步通话必须与 Chat Worker 共享同一个用户执行门禁。通话正在运行时，新文字消息仍可被 Intake 保存并排队；Chat Worker 等通话释放门禁后再处理。文字 Agent 和通话 Agent 不能并行写入同一 active conversation。

## 10. 后端领域设计

### 10.1 Chat Intake

新增应用用例建议命名为 `AcceptChatMessage`，职责仅包括：

- 验证用户、会话、文字长度和消息类型。
- 验证表情包所有权和可见性。
- 处理 `client_message_id` 幂等。
- 保存用户消息和附件。
- 创建或追加 collecting chat turn。
- 返回已保存的用户消息。

它不得：

- 调用 LLM。
- 等待 Agent 完成。
- 生成 Echo 回复。
- 直接操作 APP 推送。

### 10.2 Chat Scheduler

新增 `ChatTurnScheduler`，负责：

- 将相邻用户消息分配到同一个 Input Batch。
- 维护 `collect_until` 和最长收集时间。
- 保证每个 conversation 最多一个 running turn。
- 在当前 turn 运行时创建下一批 collecting turn。
- 达到限制时提前关闭批次。
- 后端重启后重新认领超时的 running job。

数据库认领使用事务和 `FOR UPDATE SKIP LOCKED`，即使未来增加多个后端或独立 worker，也不能让同一 turn 被运行两次。

Scheduler 还应提供共享的 `ConversationExecutionLease`：

- Chat Worker 在运行统一 Agent 前获取租约。
- 同步通话在运行统一 Agent 前获取同一租约。
- `/chat/send mode=call` 和 Chat Worker 使用同一用户执行门禁。
- 租约按 conversation 隔离，异常和超时后必须可靠释放或过期。
- Intake 不需要租约，因此 Echo 正在聊天或通话时仍能快速保存新文字消息。

### 10.3 Chat Worker

第一阶段可在 FastAPI lifespan 中启动数据库驱动的异步 worker，复用当前单实例部署，避免立即增加新服务。

实现必须通过独立 Protocol 和应用用例封装，不能把轮询、Agent 调用和 SQL 写进 `main.py`。达到以下任一条件后，再拆出 `echo-chat-worker` Compose 服务：

- 后端需要多个 API 实例。
- Chat Agent 明显占用 API 事件循环或连接池。
- 队列等待时间和 HTTP 延迟互相影响。
- 需要独立扩缩容或故障隔离。

worker 流程：

```text
claim due turn
  -> 加载 input_first_id 到 input_last_id 的用户消息
  -> 固定 context_cutoff
  -> 构建 Persona、摘要、长期记忆和最近消息
  -> 运行 Unified Agent
  -> 校验 structured delivery plan
  -> 原子保存 Reply Group
  -> 更新摘要、记忆和关系任务
  -> 发布 SSE event
```

### 10.4 Unified Agent 输出升级

当前 `AgentTurnResult.reply_text` 应逐步升级为：

```text
AgentTurnResult
  run_id
  text_segments
  content_parts
  sticker_placement
  sources
  tool_results
  error_code
```

建议新增领域模型：

```text
AgentDeliveryPlan
  text_segments: tuple[str, ...]
  sticker_placement: before_text | after_text

ChatDeliveryMessage
  message_type: text | sticker
  content
  content_parts
  sources
  sequence
```

Agent 负责表达，Chat 负责把计划转换为真实消息并持久化。Agent 不能直接写 `chat_messages`。

### 10.5 Delivery Timing Policy

回复时间不由 LLM 输出。新增纯策略组件 `DeliveryTimingPolicy`，输入只包括：

- 各文字段落的 Unicode 字素长度。
- 段落数量和表情包位置。
- 从 `chat.typing.started` 到 Reply Group 生成完成的实际耗时。
- 服务端配置的最小、最大和总等待上限。

输出为 Reply Group 的展示提示：

```text
DeliveryPresentation
  agent_elapsed_ms
  initial_delay_ms
  message_delays_ms
```

它不修改 Agent 回复内容，不执行 `sleep`，不占用 worker，不延迟数据库提交。APP 收到 delivery 后，根据提示维护本地 reveal queue；服务端和历史接口始终认为消息已经完成。

### 10.6 表情包工具边界

现有 `send_sticker` 成功结果继续是唯一的表情包发送事实：

- 模型决定是否调用和语义目标。
- 工具校验候选、权限、冷却和每轮成功额度。
- Runtime 收集成功 `ContentPart`。
- Delivery Builder 把该 `ContentPart` 转换为独立 sticker 消息。
- 最终文字不得否认已成功的工具事实。
- 失败的工具调用不产生 sticker 消息，也不消耗成功额度。

## 11. 数据模型调整

### 11.1 `chat_messages`

建议新增：

| 字段 | 用途 |
|---|---|
| `client_message_id` | 用户消息幂等 ID；assistant 为空 |
| `agent_turn_id` | 关联处理该消息的 turn |
| `reply_group_id` | 同一组 Echo 多段回复 |
| `sequence_in_group` | Reply Group 内顺序 |
| `in_reply_to_message_id` | 当前回复批次对应的最后一条用户消息 |

约束：

- `(user_id, client_message_id)` 对非空值唯一。
- 同一 `reply_group_id` 的 `sequence_in_group` 唯一。
- 用户和 assistant 仍然使用同一张消息表，历史按服务端 ID 排序。
- 文字和表情包继续通过 `message_type` 和附件区分。

### 11.2 `chat_turn_jobs`

新增持久化队列表：

| 字段 | 用途 |
|---|---|
| `turn_id` | 稳定业务 ID |
| `user_id` / `conversation_id` | 数据隔离和会话调度 |
| `status` | collecting / queued / running / completed / failed / cancelled |
| `input_first_message_id` | 批次第一条用户消息 |
| `input_last_message_id` | 批次最后一条用户消息 |
| `context_cutoff_message_id` | Agent 实际看到的最后一条消息 |
| `collect_until` | 静默窗口截止时间 |
| `collect_deadline` | 最长收集截止时间 |
| `attempt_count` / `max_attempts` | 崩溃恢复和有限重试 |
| `agent_run_id` | 关联 `agent_runs` |
| `error_code` | 最终失败分类 |
| `started_at` / `completed_at` | 延迟和运维分析 |

数据库必须保证同一 conversation 最多一个 `running` turn。

### 11.3 `chat_request_results`

该表只继续服务同步通话请求幂等。异步聊天改用 `client_message_id` 和 `chat_turn_jobs`，不把一整份 Agent 回复缓存绑定在某条用户 HTTP 请求上。

### 11.4 来源持久化

网络搜索来源需要绑定到 Reply Group 的最后一条文字消息，或者新增稳定的 message source 记录。历史重新加载后仍必须能打开来源，不能只依赖 SSE payload。

## 12. APP 状态模型调整

### 12.1 删除全局发送锁语义

`ChatState.isSending` 不再控制整个输入区。建议拆分为：

```text
isClearing
isLoadingInitialHistory
isLoadingMoreHistory
eventConnectionState
echoTyping
pendingMessagesByClientId
```

输入区仅在以下情况禁用：

- 未登录或 token 已失效。
- 正在清空会话。
- 输入为空或超过长度限制。
- 当前页面正在销毁。

Echo typing、历史加载和某一条消息发送中都不应锁住正常输入。

### 12.2 单条用户消息状态

建议 APP 领域模型增加：

```text
ChatSendState.localSending
ChatSendState.sent
ChatSendState.failed
```

交互：

- `localSending`：气泡旁显示轻量进度状态。
- `sent`：服务端已持久化，不需要额外“已读”文案。
- `failed`：显示红色失败图标，点击使用同一 `client_message_id` 重试。
- 重试成功后替换原消息，不新增重复气泡。

第一阶段不声称 Echo 已读，因为模型真正开始处理的时间与服务器接收时间不同。

### 12.3 Typing 状态

- typing 是聊天列表底部的临时状态，不再创建 `ChatMessage.typing` 假消息。
- 收到 `chat.typing.started` 后展示“Echo 正在输入”。
- 收到 delivery、failed 或 stopped 后移除。
- 多个批次排队时，只要存在 running turn，typing 保持可见。
- SSE 断开时不长期保留 typing，重新连接后由服务端状态恢复。

### 12.4 多段消息展示

- Reply Group 中的每条文字是独立气泡。
- 连续 Echo 气泡可以减少重复头像和时间，保持视觉分组。
- 表情包直接显示图片，不显示外围文字气泡。
- 来源入口显示在 Reply Group 最后一条文字消息下方。
- 每个气泡拥有稳定尺寸约束，图片加载不能推动前后消息错位。

### 12.5 动态打字展示状态

APP 将 typing 拆成两个来源：

```text
serverProcessing = Agent turn 仍在运行
localRevealActive = Reply Group 仍有段落等待展示
echoTyping = serverProcessing || localRevealActive
```

- 收到完整 Reply Group 后立即在状态中保留所有消息及顺序，但按 reveal queue 逐条设为可见。
- `chat.typing.stopped` 只结束 `serverProcessing`，不能清除仍在运行的 `localRevealActive`。
- 用户发送新消息不取消 reveal queue，也不禁用输入区。
- 页面离开、APP 后台或事件过期时立即完成 reveal queue，避免回来后继续播放旧动画。
- 新 Reply Group 到达时按服务端消息顺序排队，不能同时运行两套互相交错的展示计时器。
- 定时器必须在 Controller/Notifier 层管理并在 dispose 时释放，不能直接散落在单个气泡 Widget 中。

### 12.6 滚动行为

- 用户当前位于列表底部时，新消息自动滚动到底部。
- 用户正在查看历史时，不强制跳转，显示“新消息”浮动按钮。
- 用户自己发送消息时滚动到自己的最新消息。
- 加载更早历史继续补偿滚动偏移。
- Reply Group 一次插入，避免多次自动滚动造成画面抖动。

### 12.7 SSE 生命周期

- 登录成功并进入聊天页后连接。
- APP 后台允许断开，回到前台重连。
- token 刷新后重新建立连接。
- 重连退避建议为 1、2、5、10、30 秒封顶。
- 每次重连使用最后服务端 `message_id` 补齐。
- 同一消息可能同时来自 HTTP ACK、历史补齐和 SSE，必须统一按 message ID 去重。

## 13. 摘要、记忆、关系和来信兼容

### 13.1 聊天摘要

- 摘要在 Reply Group 持久化后更新。
- 多段 Echo 文字按顺序合并后提供给摘要器。
- 摘要继续只压缩 LLM 上下文，不删除原始消息。
- collecting 和 running 状态的用户消息不能提前进入已完成摘要边界。

### 13.2 长期记忆

- 一个 Input Batch 触发一次记忆 gate。
- gate 可以看到批次内每一条用户消息和完整 Echo 多段文字。
- 后台任务 payload 应记录该批次的全部用户 source message IDs，不能只记录最后一个气泡。
- 表情包语义标签可以参与理解，但不能把图片 URL 当成长期事实。

### 13.3 关系进度

- 关系互动次数按成功完成的 Agent turn 计算，不按用户气泡数量计算。
- 用户连续拆句不能快速刷高关系阶段。
- Agent 最终失败时是否计入互动沿用当前业务规则，但必须保持确定且可测试。

### 13.4 每日来信

- 来信继续读取真实 `chat_messages`。
- Echo 多段回复应按 Reply Group 顺序还原。
- 未完成 turn 不作为已回复互动写入来信来源。

## 14. 清空聊天与并发处理

用户在仍有 collecting、queued 或 running turn 时清空聊天，需要明确一致性规则：

1. APP 弹窗说明未完成回复会被取消。
2. 后端在事务中关闭当前 conversation 或递增 conversation generation。
3. collecting 和 queued job 标记为 cancelled。
4. running job不能继续向已清空会话提交 Reply Group。
5. running Agent 即使最终返回，提交前发现 generation 不一致也必须丢弃交付结果。
6. 当前聊天消息、附件和摘要按现有清空语义处理。
7. 长期记忆仍不随聊天清空。
8. SSE 发送 `chat.conversation.reset`，APP 清理本地列表并加载新 active conversation。

这一步不能仅依靠 APP 取消 HTTP，因为 Agent 已经脱离原始请求生命周期。

## 15. 错误与恢复策略

### 15.1 消息接收失败

- 请求未获得 202：本地消息标记 failed。
- 用户点击失败图标后使用相同 `client_message_id` 重试。
- 超时但服务器实际已保存时，幂等响应返回原消息。
- 认证失败进入登录恢复，不盲目重试。
- 表情包不存在或无权访问时，本地图片消息标记失败并提示原因。

### 15.2 Agent 失败

- 用户消息继续保留，不能回滚。
- 现有 LLM 超时仍进行一次有限重试。
- turn 最终失败后写入 `error_code`，发送 `chat.turn.failed`。
- APP 显示非气泡式状态“Echo 刚才没有回复”，不能伪造 assistant 文案。
- 失败不会阻止下一批用户消息继续处理。
- 第一阶段不自动无限重新运行失败 turn。

### 15.3 Worker 重启

- collecting 和 queued job 在启动后继续认领。
- running job 超过租约时间后允许有限重试。
- 若 Reply Group 已经提交而 job 状态更新失败，通过 `reply_group_id` 唯一约束避免重复消息。
- 成功的 `send_sticker` 额度按 Agent run 和 tool call 记录恢复，不能因 worker 重试重复交付图片。

### 15.4 SSE 断开

- 不影响数据库任务。
- APP 重新连接后调用 `after_id` 补齐。
- typing 等临时状态允许丢失并重新同步。
- 消息内容不得只存在内存事件总线。

## 16. 限流与成本控制

异步接收后需要把“消息发送限流”和“模型运行限流”分开：

| 层级 | 控制对象 | 建议 |
|---|---|---|
| Intake 限流 | 用户发送的每条消息 | 防刷接口，但允许正常连续拆句 |
| Queue 限制 | 单会话未处理消息数 | 建议最多 20 条，超限返回 429 |
| Batch 限制 | 单批消息数和总字符 | 8 条、6000 字符 |
| Agent 配额 | 实际 Agent turn | 一个 Input Batch 计一次模型回合配额 |
| Tool 配额 | 时间、搜索、表情包工具 | 沿用现有每轮调用次数和成功额度 |

不能按每个用户气泡都消耗一次完整 Agent 日配额，否则鼓励用户写成长段文字，反而不符合自然聊天体验。

## 17. 安全与隐私

- SSE、历史补齐、message ACK 均必须使用当前认证用户。
- `conversation_id`、`message_id` 和 `turn_id` 访问必须校验 `user_id`。
- 私人表情包只能由所有者和后端工具访问。
- 日志只记录 ID、消息类型、字符数、状态和耗时，不记录完整聊天正文。
- 不在日志中记录私人表情包 URL、签名参数、token 或完整工具 query。
- SSE 响应禁止代理缓存。
- APP 通知继续不显示敏感聊天正文。
- `client_message_id` 不能作为越权查询其他用户消息的凭据。

## 18. Nginx 与部署

新增 SSE location 时需要：

```text
proxy_buffering off
proxy_cache off
gzip off
proxy_read_timeout 3600s
X-Accel-Buffering: no
```

部署顺序：

1. 执行 additive 数据库迁移。
2. 部署只支持新文字协议和同步通话入口的后端。
3. 验证文字、表情包和通话链路。
4. 构建并发布使用异步聊天的新 APK。
5. 观察队列、SSE 和 Agent 指标。

数据库迁移必须是 additive，不允许要求 APP 和后端在同一秒完成切换。

## 19. 可观测性

每条链路应能通过以下 ID 对齐：

```text
request_id
client_message_id
message_id
conversation_id
turn_id
agent_run_id
reply_group_id
tool_call_id
```

建议指标：

- Chat Intake p50 / p95 响应时间。
- collecting 等待时间。
- queued 和 running turn 数量。
- Agent turn p50 / p95 完成时间。
- 每批平均用户消息数。
- 每个 Reply Group 平均文字段数。
- 主动和明确请求表情包的成功率。
- turn 失败率、超时率和重试率。
- SSE 当前连接数、断开率和重连率。
- `after_id` 补齐的消息数量。
- 幂等命中和冲突数量。

日志示例应只包含结构化元数据：

```text
chat_message_accepted user_id_hash=... message_id=... turn_id=... type=text
chat_turn_started turn_id=... input_count=3 context_cutoff=...
chat_turn_completed turn_id=... reply_group_id=... deliveries=3 duration_ms=...
```

## 20. 测试方案

### 20.1 后端单元测试

- 同一 `client_message_id` 相同内容幂等返回。
- 同一 `client_message_id` 不同内容返回冲突。
- 连续消息在 800 ms 窗口内合并。
- 超过最长收集时间后关闭批次。
- running turn 存在时创建下一批，不返回 409。
- 同一 conversation 不能同时认领两个 running turn。
- 多段结构化回复合法、非法、空段和重复段处理。
- 成功表情包转换为独立 delivery。
- 失败表情包不生成 delivery 且不占成功额度。
- worker 重试不重复保存 Reply Group。
- 清空聊天后旧 running turn 不能提交回复。
- 摘要、记忆和关系按 batch 而不是气泡数量运行。

### 20.2 后端接口测试

- `POST /chat/messages` 在 Agent 未完成前返回 202。
- 文字和表情包权限校验。
- SSE 鉴权、heartbeat、typing、delivery 和 failed 事件。
- `after_id` 正确补齐，不能读取其他用户消息。
- `/chat/send` 只接受 call 模式，chat 模式应被 schema 拒绝。
- 限流、队列满和 token 失效错误映射。

### 20.3 Flutter Controller 测试

- 发送第一条后可以立即发送第二条。
- Echo typing 时可以发送文字和打开表情包面板。
- ACK 将临时消息替换为服务端消息。
- 请求超时后同一消息重试不重复。
- HTTP ACK 与 SSE 重复到达时只显示一条。
- Reply Group 按顺序插入多个气泡和独立表情包。
- 短回复、长回复和多段回复得到不同且受上限约束的展示时间。
- Agent 实际耗时超过目标时间时不追加等待。
- APP 后台、重连和历史补齐跳过过期动画。
- reveal queue 运行时继续发送消息，顺序不跳动。
- SSE 断开、重连和 `after_id` 补齐。
- 页面销毁不取消已经 accepted 的服务端 Agent turn。
- 清空聊天重置本地 pending、typing 和 SSE cursor。

### 20.4 Flutter Widget 测试

- 输入框在 Echo typing 时保持可编辑。
- 发送按钮不显示“等待”。
- 表情包入口在 Echo 处理中仍可点击。
- 单条消息发送中、失败和重试图标。
- 多段 Echo 气泡视觉分组。
- Echo 和用户表情包均无外围空白气泡。
- 查看历史时新消息提示，不强制滚动。
- 小屏、键盘弹出和长文本不重叠。

### 20.5 真机验收

1. 2 秒内连续发送 5 条文字，全部立即显示且不出现 409。
2. Echo typing 时继续发送文字和表情包。
3. Echo 对连续拆句给出一个连贯回复，不逐句机械回答。
4. Echo 返回两至三条文字时均为独立气泡。
5. Echo 返回文字加表情包时，图片无气泡且顺序正确。
6. 短回复较快出现，长回复适当延长 typing，但额外等待不超过策略上限。
7. 模型本身已经等待较久时，回复生成后不再重复延迟。
8. 多段回复按字长依次出现，动画期间仍可继续发送且顺序不跳动。
9. APP 切后台后等待 Echo 回复，再回前台能够补齐并跳过旧动画。
10. 回复过程中关闭网络再恢复，不重复显示消息。
11. 回复过程中重启后端，用户消息不丢，任务有限恢复。
12. 查看更早历史时收到新回复，当前阅读位置不跳动。
13. 语音通话 ASR、Agent 和 TTS 全流程不回归，且不发送表情包。

## 21. 验收标准

### 21.1 功能验收

- Echo 处理中可以继续发送任意合法文字或表情包。
- 同一会话不再因为上一条处理中返回业务 `409`。
- 每条 accepted 用户消息都能在历史接口中恢复。
- 同一会话最多一个 Agent turn 运行，待处理消息按顺序进入后续批次。
- Echo 每个 Reply Group 最多三条文字和一张成功表情包。
- 表情包始终是独立图片消息。
- SSE 断开不丢消息，重连不重复消息。
- 清空聊天后不会收到旧会话的迟到回复。
- 摘要不会删除原始消息，历史分页继续正常。
- 通话、Persona、长期记忆、关系和来信无回归。

### 21.2 工程验收

- `flutter analyze` 0 问题。
- `flutter test` 全部通过。
- 后端 Ruff、架构检查和测试全部通过。
- 数据库迁移可以对现有生产数据原地执行。
- 新 APK 的文字协议与同步通话协议边界明确，无旧聊天兼容分支。
- 服务器重建后聊天队列可以恢复。
- 日志和 SSE 不泄露 token、完整聊天正文或私人图片信息。

### 21.3 体验验收

- 正常网络下，用户消息接收 ACK 目标 p95 小于 500 ms，不包含图片上传场景。
- 用户不需要等待 Echo 才能继续输入和发送。
- 连续拆句不会造成 Echo 机械地逐条回复。
- 多段回复有自然语义边界，不按标点生硬切割。
- Echo typing 时间与回复字长有可感知差异，并扣除 Agent 已经产生的真实等待时间。
- 任何单轮额外展示等待都不能超过配置上限，长回复不能让用户无意义等待。
- 新消息到达时列表滚动行为稳定，无明显跳动和重复。

## 22. 分阶段实施计划

### Phase 0：协议和迁移测试

- 确定本文件待确认事项。
- 添加数据库 migration 和 repository 测试。
- 定义 `AcceptChatMessage`、`ChatTurnJob`、`AgentDeliveryPlan` 契约。
- 定义新 API 和 SSE schema。

验收：Fake Agent 下可以完成“接收消息 -> 队列 -> 多条回复 -> 历史恢复”。

### Phase 1：后端异步接收与持久化队列

- 实现 `/chat/messages`。
- 用户消息先保存再返回 202。
- 实现 collecting 窗口和 `chat_turn_jobs`。
- 实现单会话串行 worker 和重启恢复。
- 将 `/chat/send` 收紧为仅支持同步通话。

验收：并发发送不再返回 409，用户消息不会因 Agent 失败丢失。

### Phase 2：Agent 多段回复与独立交付

- 模型输出结构化 `text_segments`。
- `AgentTurnResult` 增加 delivery plan。
- Runtime 校验段数、长度和 sticker placement。
- Reply Group 原子写入多个 assistant 消息。
- 更新摘要、记忆、关系和来源持久化。

验收：普通聊天可自然返回一至三条文字，并可附带一张独立表情包。

### Phase 3：APP 连续发送与 SSE

- ChatController 移除全局发送锁。
- 增加 client message ID 和单条发送状态。
- 接入 SSE、typing、Reply Group 和断线补齐。
- 接入 Delivery Timing Policy 提示和本地 reveal queue。
- 调整输入区、表情包面板、滚动和新消息提示。

验收：真机上 Echo 处理中可连续发送，后台回来可恢复回复。

### Phase 4：上线收口

- Nginx SSE 配置和部署脚本。
- 队列、Agent、SSE 指标和日志。
- 新聊天协议与同步通话的边界测试。
- 压力测试和真机弱网测试。
- 更新 `Echo v1.0 业务流程与数据流.md`。

验收：服务器重启、弱网和多次重连不丢失或重复消息。

### Phase 5：后续体验增强

- 无发送类工具时的草稿重算和补充消息合并。
- 最新失败 turn 的手动“让 Echo 再试一次”。
- 加密的短期离线 outbox。
- 多设备实时同步。
- 更自然但不拖慢体验的分段显示节奏。

Phase 5 不阻塞本次核心优化。

## 23. 待确认事项

以下建议作为默认方案，审核时可调整：

1. **连续消息窗口**：采用 800 ms 静默窗口，最长等待 2500 ms；推荐确认。
2. **处理中新增消息**：第一阶段进入下一批，不中断正在运行的 Agent；推荐确认。
3. **Echo 多段上限**：每个 Reply Group 最多 3 条文字；推荐确认。
4. **表情包上限**：继续保持每个 Reply Group 最多成功发送 1 张；推荐确认。
5. **纯表情包回复**：轻松闲聊允许 Echo 只回复一张表情包；知识、安全、严肃和用户明确提问时必须有文字；推荐确认。
6. **回复节奏**：已确认按回复字长动态延长。默认采用“基础 600 ms + 每有效字素 32 ms”，目标 800～4800 ms；扣除 Agent 实际耗时，生成后额外等待最多 2500 ms。参数在真机验收后可调整。
7. **清空聊天**：清空时取消未完成批次，旧 Agent 结果不得迟到写入；推荐确认。
8. **部署协议**：不兼容旧文字聊天 APK；文字只走 `/chat/messages + /chat/events`，通话继续使用同步 `/chat/send mode=call`；已确认。

## 24. 最终决策摘要

本方案的核心不是让多个 Agent 同时回复，而是：

```text
用户消息可以并发进入
  + 服务端立即可靠保存
  + 相邻消息自然合并
  + Agent 按会话严格串行
  + Echo 输出结构化多段消息
  + APP 通过 SSE 异步接收
```

这样既能获得接近微信的连续发送体验，又不会牺牲 Agent 工具一致性、消息顺序、历史恢复和服务器可靠性。

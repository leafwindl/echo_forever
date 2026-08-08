# Echo 主动聊天、定时任务与通知系统开发文档

> 状态：核心代码与个推接入已实现，凭证鉴权已验证，待真机 CID 与厂商离线通道联调
>
> 日期：2026-08-08
>
> 适用范围：Android APP、Echo 后端、统一 Agent、异步聊天、个推与国内厂商通知
>
> 不适用范围：语音通话。通话继续保持用户主动发起，不发送主动消息和表情包通知。

## 1. 结论

该功能可以实现，并且不需要更换现有 Agent 架构，也不需要引入 LangGraph。

推荐把所有主动行为统一为“后端触发的一次正式聊天交付”：

```text
用户自然语言设定 / Echo 决定稍后联系 / 主动聊天策略命中
                           |
                           v
                   持久化调度任务
                           |
                           v
                 后端 Worker 到期认领
                           |
                           v
              统一 Agent 根据当前上下文生成
                           |
              +------------+-------------+
              |                          |
              v                          v
       保存 Echo 聊天消息          写入通知 Outbox
              |                          |
              v                          v
       前台通过 SSE 到达            后台通过个推到达
              |                          |
              +------------+-------------+
                           |
                           v
                 用户打开后看到同一条消息
```

消息必须先保存进聊天记录，再发送通知。通知只是提醒入口，不是消息本身。这样即使 APP 被关闭、网络中断或通知发送失败，Echo 的消息仍然存在，用户下次打开 APP 时可以看到。

## 2. 产品目标

### 2.1 目标

1. Echo 可以在没有新用户消息时主动发起聊天。
2. 用户可以直接说“晚上八点提醒我”“明天面试结束后来问我”，由 Agent 创建定时任务。
3. Echo 可以在聊天中判断“稍后再问候更自然”：例如用户说“我下午要去面试”，Echo 回复“你先去忙，晚上我来问问结果”，并在用户已开启允许 Echo 主动联系时创建一条“今晚问候面试结果”的一次性任务。它不是随机打扰，也不是自动创建每日循环提醒。
4. 用户可以查看、暂停、修改和取消所有定时任务。
5. APP 在前台时，主动消息像普通 Echo 消息一样实时进入聊天记录。
6. APP 在后台或退出时，通过系统通知提醒用户；点击通知进入聊天页。
7. 主动消息可以由 Agent 拆成多段文字，并最多附带一张表情包，继续复用现有发送节奏和表情包冷却规则。
8. 所有主动行为可关闭、可审计、可限频，不允许 Echo 无限自我调度。

### 2.2 非目标

1. 第一阶段不做秒级精确闹钟，也不承诺医疗、出行等安全关键提醒绝对准时。
2. 不依赖手机本地 Timer、WorkManager 或 Android 精确闹钟维持调度。
3. 不允许 Agent 直接写数据库或绕过业务层创建任务。
4. 不允许 Echo 创建无限循环、永久递归或用户不可见的定时任务。
5. 不在语音通话中创建主动消息，不为主动消息生成 TTS。
6. 第一阶段不支持群聊、多角色或跨用户主动消息。

## 3. 当前项目基础

### 3.1 已具备的能力

当前项目已经具备以下基础：

- 异步聊天消息会先落库，再由 Worker 运行 Agent。
- Echo 回复支持多段文字、独立表情包和交付延迟。
- APP 通过 `/chat/events` 的 SSE 接收实时回复，并通过聊天历史补偿断线消息。
- Agent 已有标准 Tool Registry、参数校验、超时、调用次数和运行轨迹。
- 后端已有每日来信、聊天回合、表情包生成等轮询 Worker 模式。
- APP 已声明 Android 通知权限，并实现个推 CID、前台消息、点击通知和路由跳转。
- `PushNotification` 已允许 `chat` 路由，可以跳转到聊天页。
- Persona 已有 `proactivity` 字段，可以直接映射主动聊天频率档位。

### 3.2 尚未完成的能力

当前通知闭环已经具备：

- Android 个推 AppID 已通过本地构建配置注入，服务端凭证不进入 APK。
- 后端已有 `push_targets`、`notification_outbox` 和注册/注销接口。
- 个推 RestAPI V2 鉴权、发送、失败重试和无效 CID 清理已实现。
- Debug APK 已构建成功，下一步需要真机登录产生 CID 后验证后台通知。
- 华为、荣耀、小米、OPPO、vivo 等厂商离线通道仍需分别配置凭证。
- 当前主动任务只有每日来信，没有通用聊天调度任务。

因此本功能不是“打开一个开关”即可完成，而是需要补齐主动调度和推送服务端链路。

## 4. 主动消息类型

### 4.1 用户明确设定

示例：

- “晚上八点提醒我喝水。”
- “明天下午三点叫我去取快递。”
- “每周五下班后问我这周过得怎么样。”
- “取消今晚的提醒。”

行为：

1. Agent 必须先调用可靠时间工具解析当前日期、时区和相对时间。
2. 时间明确时调用调度工具创建任务。
3. 时间存在歧义时先询问用户，不得自行猜测上午或下午。
4. 创建成功后由 Echo 自然确认时间和内容。
5. 用户明确设定的时间默认优先于 Echo 的安静时段，但设置页允许用户改成“安静时段内顺延”。

### 4.2 Echo 自主安排后续联系

示例：

- 用户说“我下午要去面试”，Echo 回复后决定晚上再来问结果。
- 用户说“我先去吃饭了”，Echo 可以在较晚时间自然问一句“吃得怎么样”。
- 用户情绪低落，Echo 可以在数小时后进行一次有限的关心。

约束：

1. 用户必须开启“允许 Echo 主动联系”。
2. Echo 第一阶段只能自主创建一次性任务，不能自行创建永久循环任务。
3. Echo 自主任务最远只能安排在未来 7 天内。
4. 同一聊天语境最多保留一个未执行的 Echo 后续任务。
5. Echo 连续两次主动消息都没有得到用户回复后，暂停自主主动聊天，直到用户再次发言。
6. Echo 自主任务必须受安静时段、每日额度和最小间隔限制。
7. 任务会出现在用户可管理的任务列表中，不做不可见的后台约定。

### 4.3 策略型自然主动聊天

这类消息没有用户明确指定时间，也不是 Echo 在某一轮里明确约定，而是系统根据关系和活跃度选择合适时机。

推荐采用“两阶段决策”，不能让 LLM 每分钟扫描所有用户：

```text
PostgreSQL 确定性筛选候选用户
  -> 检查主动开关、时区、安静时段、最近互动、未回复次数、每日额度
  -> 只有合格候选才调用 Agent
  -> Agent 根据上下文决定 send 或 skip
  -> send 才创建正式 Echo 消息
```

Agent 可以因为“没有自然话题”“用户刚刚离开”“当前关系阶段不合适”选择 `skip`。跳过不会通知用户，但需要记录原因供调试和成本分析。

## 5. 推荐频率策略

现有 Persona 的 `proactivity` 可以映射为三个档位：

| 档位 | 候选触发条件 | 每日上限 | 最小间隔 |
|---|---:|---:|---:|
| 保守 | 用户至少 24 小时未互动 | 每周最多 4 次 | 24 小时 |
| 平衡 | 用户至少 6 小时未互动 | 每天最多 4 次 | 6 小时 |
| 主动 | 用户至少 2 小时未互动 | 每天最多 6 次 | 2 小时 |

推荐默认值：

- 默认档位：平衡。
- 默认安静时段：用户当地时间 `22:30-08:00`。
- Echo 自主主动消息最多连续发送 2 次；两次均未回复则暂停。
- 用户正在 APP 内聊天或 2 分钟内刚发送消息时，不发送新的主动通知。
- 每次主动回合最多成功发送一张表情包，继续使用现有官方/私人表情包排序和冷却机制。
- 系统服务重启后，Echo 自主任务超过 60 分钟不补发；用户明确提醒可在 30 分钟宽限期内补发，超过后标记为错过。

## 6. 统一 Agent 设计

### 6.1 不需要 LangGraph

当前 Agent 已经支持：

- 多步模型调用。
- 标准工具描述。
- 参数模型校验。
- 工具超时和调用额度。
- 工具结果回传模型。
- 最终多段文字和表情包交付。

定时任务是持久化业务能力，不是需要长时间挂起的 LLM 工作流。Agent 只负责在当前回合创建、修改或取消一个任务，真正的等待由数据库和 Worker 完成。

### 6.2 新增工具

第一阶段新增四个工具：

```text
create_chat_schedule
list_chat_schedules
update_chat_schedule
cancel_chat_schedule
```

工具仅允许 `conversation_mode=chat`，不允许 `call`。

`create_chat_schedule` 建议参数：

```json
{
  "intent": "面试结束后问问结果",
  "schedule_type": "once",
  "local_datetime": "2026-08-09T20:00:00",
  "timezone": "Asia/Shanghai",
  "recurrence": null,
  "user_visible_label": "面试后的问候"
}
```

关键规则：

- `created_by` 不能由模型传入，必须由 ToolExecutionContext 根据本轮来源写入 `user_request` 或 `echo_agent`。
- 相对时间必须先调用 `get_current_time`。
- Tool Handler 只调用 Proactive Chat Application Service，不直接执行 SQL。
- 创建、修改和取消都必须返回稳定的 `schedule_id` 和最终解析时间。
- 同一 Agent 回合最多成功创建一个任务，避免重复调度。
- 重复的幂等请求返回已有任务，不创建副本。
- 循环任务只有用户明确要求时才允许创建。

### 6.3 到期后的 Agent 输入

任务到期时，不复用创建任务时的完整旧提示词，而是重新构建当前上下文：

```text
系统触发类型
任务意图与创建原因
当前可靠时间和用户时区
最近聊天消息
对话摘要
相关长期记忆
关系阶段和主动频率设置
最后一次用户互动时间
最近主动消息及用户是否回应
```

Agent 输出仍然使用现有交付协议：

- 一段或多段自然文字。
- 可选一张表情包。
- 不生成语音。
- 不描述内部定时器、Worker、工具或系统策略。

## 7. 后端模块设计

建议新增独立 Feature：

```text
Echo-backend/features/proactive_chat/
  domain/
    entities.py
    repositories.py
    services.py
  application/
    create_schedule.py
    manage_schedules.py
    select_candidates.py
    execute_due_job.py
  infrastructure/
    postgres_repository.py
    notification_outbox.py
    container.py
  interface/
    router.py
    schemas.py
  public.py
```

推送能力单独建设：

```text
Echo-backend/features/push/
  domain/
  application/
  infrastructure/getui_sender.py
  interface/router.py
```

模块边界：

- Proactive Chat 决定何时创建主动聊天任务。
- Agent 决定任务到期时具体说什么、是否使用表情包。
- Chat 负责保存和交付正式消息。
- Push 负责设备注册、通知 Outbox 和个推发送。
- Agent 不能直接依赖个推，也不能直接写聊天表。

## 8. 数据模型

### 8.1 主动聊天偏好

`proactive_chat_preferences`：

| 字段 | 用途 |
|---|---|
| `user_id` | 用户唯一标识 |
| `enabled` | 主动聊天总开关 |
| `allow_echo_scheduling` | 是否允许 Echo 自己创建后续任务 |
| `allow_spontaneous_chat` | 是否允许策略型自然主动聊天 |
| `proactivity_level` | conservative / balanced / active |
| `timezone` | IANA 时区 |
| `quiet_start` / `quiet_end` | 安静时段 |
| `explicit_reminder_quiet_policy` | honor / defer |
| `notification_preview` | 是否允许通知显示正文预览 |
| `updated_at` | 更新时间 |

### 8.2 定时任务

`chat_schedules`：

| 字段 | 用途 |
|---|---|
| `schedule_id` | 稳定任务 ID |
| `user_id` | 所属用户 |
| `created_by` | user_request / echo_agent / system_policy |
| `schedule_type` | once / daily / weekly |
| `intent` | 到期时要完成的语义目标 |
| `user_visible_label` | 设置页展示名称 |
| `timezone` | 原始 IANA 时区 |
| `next_run_at` | UTC 执行时间 |
| `recurrence_rule` | 结构化重复规则，不允许任意 cron 文本 |
| `status` | active / paused / completed / cancelled |
| `run_count` / `max_runs` | 执行次数约束 |
| `last_run_at` | 上次执行时间 |
| `idempotency_key` | 防止重复创建 |
| `created_at` / `updated_at` | 审计时间 |

### 8.3 执行任务

`proactive_chat_jobs`：

- 每个计划执行点生成一个 Job。
- 唯一约束：`(schedule_id, scheduled_for)`。
- 状态：`pending / running / succeeded / retry_wait / failed / suppressed / missed`。
- 使用 `attempt_count`、`max_attempts`、`lease_expires_at` 支持崩溃恢复。
- Worker 使用 `FOR UPDATE SKIP LOCKED` 认领，避免重复执行。

### 8.4 推送目标

`push_targets`：

| 字段 | 用途 |
|---|---|
| `user_id` / `device_id` | 用户设备 |
| `platform` | android |
| `provider` | getui |
| `target_type` / `target_value` | 推送目标，避免业务层写死具体标识形式 |
| `app_version` / `environment` / `locale` | 诊断与版本管理 |
| `status` | active / invalid / revoked |
| `last_seen_at` / `last_success_at` | 生命周期管理 |

### 8.5 通知 Outbox

`notification_outbox`：

- `notification_id`：全局幂等 ID。
- `user_id`、`message_id`、`notification_type`。
- `title`、`body_policy`，默认不保存敏感正文。
- `payload`：版本化路由数据。
- `status`、`attempt_count`、`next_attempt_at`、`last_error_code`。
- 消息落库和 Outbox 写入必须处于同一数据库事务。

## 9. 到期执行数据流

```text
Proactive Worker
  -> claim due job
  -> 再次检查用户开关、安静时段、额度和最近互动
  -> 获取当前 conversation_id
  -> 构建 proactive trigger context
  -> 调用统一 Agent（conversation_mode=proactive）
  -> 复用现有多段回复与表情包交付模型
  -> 一个事务中：
       保存 assistant 消息
       更新 schedule/job
       写 notification_outbox
  -> 发布 chat.delivery.created SSE 事件
  -> Push Worker 发送个推通知
```

如果用户此时正在前台：

- SSE 直接把消息送入聊天记录。
- 个推前台到达回调只显示 APP 内提示，不重复创建聊天消息。

如果用户在后台或 APP 已退出：

- 系统通知提示“Echo 发来了一条消息”。
- 点击通知跳转 `/chat?entity_id=<message_id>`。
- APP 重新加载聊天历史，消息来自数据库，不依赖通知正文。

## 10. 聊天协议改造

主动消息应继续复用 `chat.delivery.created`，只增加可选字段，不创建第二套客户端消息协议：

```json
{
  "origin": "proactive",
  "trigger_id": "schedule_xxx",
  "messages": [],
  "presentation": {}
}
```

旧版 APP 会忽略新增字段，仍然可以显示 `messages`。这符合多版本兼容原则。

聊天消息建议新增可选来源信息：

- `origin=user_reply | proactive | daily_letter`。
- `trigger_id`。
- `in_reply_to_message_id` 对主动消息可为空。

“清空聊天上下文”默认不删除定时任务。用户必须在主动聊天设置页单独取消任务，避免误删重要提醒。

## 11. 推送通知设计

### 11.1 消息类型

后台通知使用“通知内容 + data 路由”的组合：

```json
{
  "notification": {
    "title": "Echo",
    "body": "Echo 发来了一条消息"
  },
  "data": {
    "schema_version": "1",
    "type": "chat_proactive",
    "route": "chat",
    "notification_id": "notification_xxx",
    "entity_id": "message_xxx"
  }
}
```

默认通知不展示聊天正文、记忆、Persona、日程意图或表情包语义。后续可增加用户主动开启的正文预览选项。

### 11.2 Android 展示

- Android 13 及以上继续使用现有 `POST_NOTIFICATIONS` 运行时权限。
- 用户第一次开启主动聊天或创建提醒时，再解释用途并请求通知权限，不在首次启动时强行弹出。
- 创建 `echo_messages` 高重要性通知渠道，使后台消息具备横幅/弹窗资格。
- 用户在系统设置中降低渠道重要性后，APP 不得反复强制恢复。
- 前台继续使用现有 SnackBar 或聊天内提示；后台和退出状态交给系统通知展示。
- 用户拒绝通知权限时，主动消息仍写入聊天记录，只是不弹系统通知。

### 11.3 推送可靠性

- 使用个推 RestAPI V2，服务端通过短期鉴权 token 调用单 CID 推送接口。
- `AppKey`、`MasterSecret` 仅放服务器环境或密钥管理系统，不提交 Git，不打入 APK。
- 无效或注销的推送目标自动标记失效。
- 个推发送失败进入有限指数退避，聊天消息本身不回滚。
- 多设备默认给同一账号的所有 active 设备发送，客户端通过 `notification_id` 去重。
- 网络推送只能提供尽力而为的分钟级提醒，不承诺秒级准时。

## 12. APP 页面设计

聊天菜单新增“主动聊天与提醒”页面。

页面内容：

1. 主动聊天总开关。
2. “允许 Echo 自己安排后续联系”开关。
3. “允许 Echo 偶尔主动找我”开关。
4. 主动程度分段控制：保守 / 平衡 / 主动。
5. 时区和安静时段。
6. 通知权限状态和系统设置入口。
7. 定时任务列表：时间、重复规则、来源、状态。
8. 暂停、编辑和删除任务。

聊天中的自然语言仍然是主要创建入口，设置页主要负责控制和管理，不把聊天体验变成复杂日历工具。

任务创建成功后，Echo 使用自然回复确认，例如：

```text
好，明天晚上八点我来问你面试怎么样。
```

不显示“工具调用成功”“Job 已创建”等系统术语。

## 13. API 设计

### 13.1 主动偏好

```text
GET  /proactive/preferences
PUT  /proactive/preferences
```

### 13.2 任务管理

```text
GET    /proactive/schedules
POST   /proactive/schedules
PATCH  /proactive/schedules/{schedule_id}
DELETE /proactive/schedules/{schedule_id}
```

APP 的 POST/PATCH 用于设置页操作；Agent 工具直接调用 Application Service，不经过本机 HTTP 回环。

### 13.3 推送目标

与现有 APP 占位契约保持一致：

```text
PUT    /push/tokens/me
DELETE /push/tokens/me/{device_id}
```

服务端返回业务成功即可，绝不把推送目标写入日志或返回给其他设备。

## 14. 一致性、失败和幂等

### 14.1 必须保证

1. 相同 `schedule_id + scheduled_for` 最多生成一个主动回合。
2. 相同 `notification_id` 最多形成一次逻辑通知。
3. Agent 超时可以有限重试，但不能产生重复聊天消息。
4. 推送失败不能删除或回滚聊天消息。
5. 服务重启后 pending/running 任务可以通过 lease 恢复。
6. 任务取消和 Worker 执行并发时，以数据库锁内最终状态为准。
7. 用户注销当前设备后，该设备不能继续接收账号通知。

### 14.2 降级行为

- Agent 失败：Job 有限重试，超过次数标记 failed，不发送固定生硬消息。
- 表情包工具失败：仍发送 Agent 的文字，不影响任务成功。
- 个推失败：保留消息并重试通知。
- SSE 断开：APP 通过聊天历史补回消息。
- 通知权限关闭：设置页提示状态，消息仍保留。
- 用户在任务到期前再次发言：Echo 自主任务可以被重新评估、顺延或抑制，用户明确提醒不能无故取消。

## 15. 安全与体验边界

1. 主动聊天默认关闭或在用户明确开启后生效。
2. Echo 自主创建任务必须可见、可取消。
3. 不使用内疚、威胁、占有或“我一直在等你”等话术催促用户回来。
4. 不根据敏感记忆在锁屏通知中暴露内容。
5. 不把通知点击率当成关系分数或情感压力信号。
6. 用户关闭主动聊天后，暂停未执行的 Echo 自主任务；用户明确提醒是否保留由关闭确认弹窗决定。
7. 用户删除账号时同步删除调度任务、推送目标和通知 Outbox。
8. 所有 Agent 自主任务记录 `run_id`、触发原因和策略版本，便于追踪。

## 16. 分阶段实施

### 第一阶段：基础通知闭环

- 配置个推 Android 应用和 AppID。
- 实现推送目标注册、注销和个推 RestAPI V2 发送器。
- 实现通知 Outbox 和失败重试。
- 完成 Android 通知渠道、后台通知和点击跳转。
- 使用测试接口向指定用户发送一条无敏感正文的测试通知。

### 第二阶段：用户定时任务

- 实现主动偏好、任务表和 Worker。
- 实现创建、查询、修改和取消 API。
- 增加 Agent 调度工具。
- 支持一次性、每日和每周任务。
- 到期后生成正式聊天消息并推送。

### 第三阶段：Echo 自主后续联系

- ToolExecutionContext 区分用户要求和 Echo 自主决策。
- 接入安静时段、每日额度、最小间隔和未回复暂停。
- Echo 可在聊天回合内创建一次性后续任务。
- 设置页展示来源为“Echo 安排”。

### 第四阶段：自然主动聊天

- 实现确定性候选筛选。
- Agent 执行 `send / skip` 二次判断。
- 接入 Persona proactivity、关系阶段和最近互动。
- 增加成本、发送率、回复率和用户关闭率观测。

## 17. 测试与验收

### 17.1 后端测试

- 同一任务并发认领只执行一次。
- Worker 崩溃后 lease 到期可恢复。
- 取消任务不会再生成消息。
- 相对时间、时区和夏令时转换正确。
- 用户明确提醒和 Echo 自主任务使用不同策略。
- 安静时段、每日上限、最小间隔和未回复暂停正确。
- Agent 生成多段文字和一张表情包时保存顺序正确。
- 消息与通知 Outbox 原子写入。
- 个推临时失败重试，无效 CID 停用。
- 推送正文不包含敏感聊天内容。

### 17.2 APP 测试

- 前台收到主动消息后聊天列表实时更新。
- 后台收到系统横幅，点击进入聊天页。
- APP 被正常划掉后仍可收到通知。
- 通知权限拒绝后，消息仍能在重新打开 APP 时看到。
- 冷启动点击通知可以在登录和 Persona 路由守卫后正确进入聊天。
- 同一通知不会重复展示或重复导航。
- 任务列表支持暂停、编辑和删除。
- 不同屏幕尺寸下开关、时间和任务标题不溢出。

### 17.3 真机验收场景

1. 用户说“2 分钟后提醒我测试通知”。
2. Echo 确认任务，设置页出现该任务。
3. 将 APP 切到后台。
4. 到期后系统出现 Echo 通知。
5. 点击通知进入聊天页，看到 Echo 的正式消息。
6. 退出并重新打开 APP，该消息仍在历史记录中。
7. 创建重复任务并取消，确认下一周期不再发送。
8. 开启 Echo 自主联系，确认安静时段和未回复暂停生效。

## 18. 上线前需要的外部配置

实现推送前需要准备：

1. 个推 Android 应用。
2. Android 应用包名：`cn.echoaiforever.echo_app`。
3. Android AppID，用于构建新的 APK。
4. 服务端 AppKey 与 MasterSecret，只放服务器。
5. 腾讯云服务器到个推 RestAPI V2 的出站网络可用性验证。
6. Android 真机通知权限、后台、锁屏和省电策略测试。
7. 各厂商离线通道的应用凭证与上架状态。

个推 AppID 配置完成后必须重新构建 APK；只修改服务器无法让未集成个推 SDK 的旧安装包获得系统通知能力。

## 19. 待确认事项

以下为推荐默认方案，开发前需要产品确认：

1. 主动聊天默认关闭，还是在 Persona 初始化时询问用户是否开启。推荐默认关闭并引导开启。
2. 默认档位是否使用“平衡”：每日最多一次、最小间隔 8 小时。
3. 默认安静时段是否为用户当地时间 `22:30-08:00`。
4. 用户明确提醒是否允许越过安静时段。推荐允许，并在创建时明确显示时间。
5. Echo 自主任务是否需要在回复中明确说出“我晚点来问你”。推荐自然说明，避免不可见承诺。
6. 通知正文预览由用户自行设置，默认隐藏，只显示“Echo 发来了一条消息”。
7. 第一阶段是否只支持一次性任务，再逐步增加每日/每周重复。推荐第一阶段先做一次性任务，验证稳定后开放重复规则。

## 20. 最终建议

建议按“通知基础设施 -> 用户一次性提醒 -> Echo 自主后续 -> 自然主动聊天”的顺序开发。

其中最重要的架构原则是：

- 定时任务在后端持久化，不依赖手机进程。
- Agent 负责内容和工具决策，业务服务负责规则和数据。
- 主动消息与普通 Echo 回复使用同一聊天消息模型。
- 先保存消息，再发送通知。
- 所有 Echo 自主行为都有开关、频率上限、安静时段和未回复暂停。

这样既能实现接近真实聊天的主动感，也不会因为随机推送、重复任务或不可控 Agent 行为损害用户体验。

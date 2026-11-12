# Agent 工具面基线

更新日期：2026-11-11（阶段 3 完成）
作用：记录工具面与提示分层的起点数字、门禁命令与棘轮门槛。阶段完成后只更新数字与结论，不重写设计。工具规格的单一事实源在 `Echo-backend/tests/test_agent_tool_surface.py`，本文不复制第二份。

## 1. 门禁命令

```powershell
python -B scripts/check_architecture.py
python -B -m pytest Echo-backend/tests -q
python -B -m pytest Echo-backend/tests/test_agent_tool_surface.py Echo-backend/tests/test_tool_selection.py -q
```

架构检查只扫描 `Echo-backend/features/`，不覆盖测试与提示文本。

## 2. 当前结果

| 项 | 结果 |
| --- | --- |
| 架构检查 | 通过（exit 0） |
| 全量后端测试 | 552 passed / 9 skipped / 0 failed，约 11 秒 |
| 运行环境 | Python 3.13.12，本地 PostgreSQL + pgvector（Docker，`127.0.0.1:5433`） |

9 个跳过项：1 个 `test_relationship_interface`（需要 `DATABASE_URL`）、8 个 `test_speaker_lab`（声纹只允许隔离实验库）。

## 3. 注入面

### 3.1 注册面（registry，固定成本上限）

序列化口径：`json.dumps(model_descriptions(mode), ensure_ascii=False, separators=(",", ":"))`，token 用 `estimate_prompt_tokens`，是估算值。

| 模式 | 工具数 | 字符数 | 估算 tokens |
| --- | ---: | ---: | ---: |
| `chat` | 33 | 12,334 | 4,149 |
| `call` | 3 | 约 1,300 | 约 360 |
| `proactive` | 2 | 1,138 | 486 |
| `daily_letter` | 0 | 2 | 1 |

按"联网搜索未配置"计算；配置后 `chat` 与 `call` 各增加 1 个 `search_web`。

### 3.2 选择后（chat 模式每轮实际注入）

由 `select_chat_tool_names` 按运行时事实裁剪，实测：

| 场景 | 工具数 | 字符数 | 估算 tokens | 相对全量 |
| --- | ---: | ---: | ---: | ---: |
| 设备都离线 | 9 | 3,391 | 1,099 | −73% |
| 电脑在线（典型） | 17 | 6,206 | 2,174 | −48% |
| 手机在线 | 23 | 8,889 | 2,846 | −31% |
| 都在线 | 31 | 11,704 | 3,922 | −5% |
| 都在线 + 主动关键词 | 33 | 12,334 | 4,149 | 0% |

### 3.3 每轮固定提示文本（chat）

| 段 | 阶段 2 | 阶段 3 |
| --- | ---: | ---: |
| `CHAT_BEAT_INSTRUCTION`（独立 system） | 415 字符 | **0（已删除）** |
| `mode guidance.chat` | 193 字符 | 约 80 字符 |
| 工具描述合计 | 2,134 字符 | 约 1,470 字符 |
| 规则层 `natural-dialogue.md` | 1,147 字符 | 约 1,290 字符（气泡与贴纸合并为唯一完整版） |

净效果：每轮 chat 固定文本约 −900 字符、工具面 −501 tok。

### 3.4 提示三层归属

| 层 | 写什么 | 不写什么 |
| --- | --- | --- |
| 规则层 `prompts/rules/natural-dialogue.md` | 行为策略：何时用工具、怎么说话、边界 | 参数名、失败码 |
| 渠道层 `renderer._CONVERSATION_MODE_GUIDANCE` | 渠道形态（文字/电话/主动/来信） | 工具操作流程 |
| 能力层 工具 `description` | 工具做什么、参数怎么填、失败怎么表现 | 行为策略、性格语气 |

判断标准：模型"选哪把工具"看能力层，"怎么表现"看规则层。

### 3.5 Agent 运行时结构（阶段 4 起）

```text
OrchestrateChatWithAgent       兼容薄壳（80 行），保留旧构造与 execute 签名
        │
        ▼
AgentTurnRuntime               一次 turn 的入口：装配 → 循环 → 记账 → 结果
        │
        ├─ TurnPolicy          domain：模式 → TurnProfile（交付/步数/重试/静默）
        ├─ ModelToolLoop       模型↔工具循环 + 交付检查点
        │     ├─ DeliveryGate      文本→交付计划、恢复、贴纸声称
        │     └─ TurnFallbacks     确定性兜底文案
        └─ AgentRunRepository  轨迹
```

| 模块 | 文件 | 行数 | 职责 |
| --- | --- | ---: | --- |
| 兼容薄壳 | `application/orchestrate_chat.py` | 80 | 参数翻译，内部委托 runtime |
| Runtime | `application/agent_runtime.py` | 98 | 装配、记账、结果翻译 |
| 循环 | `application/model_loop.py` | 760 | 模型调用、工具执行、交付检查、重试 |
| 策略 | `domain/turn_policy.py` | 214 | 模式差异、初始消息、工具范围收窄 |
| 交付门禁 | `application/delivery_gate.py` | 132 | 文本切分、恢复、重试消息、贴纸声称 |
| 兜底 | `application/turn_fallbacks.py` | 69 | 确定性文案 |

工具结果自带交付声明（`AgentToolResult.published_segments` / `sticker_placement`），runtime 不再按工具名特判。

## 4. 工具清单（chat 注册顺序）

| # | 工具 | 域 | 注入条件 |
| ---: | --- | --- | --- |
| 1 | `send_sticker` | 交付 | 常驻 |
| 2 | `emit_chat_beats` | 交付 | 常驻 |
| 3 | `desktop_speak` | 桌面 | 桌面在线 |
| 4 | `desktop_status` | 桌面 | 常驻 |
| 5 | `desktop_open_app` | 桌面 | 桌面在线 |
| 6 | `desktop_media_control` | 桌面 | 桌面在线 |
| 7 | `desktop_look` | 桌面 | 桌面在线 |
| 8 | `desktop_music_search_play` | 桌面 | 桌面在线 |
| 9 | `desktop_notepad_write` | 桌面 | 桌面在线 |
| 10 | `desktop_dsh_task` | 桌面 | 桌面在线 |
| 11 | `desktop_screenshot` | 桌面 | 桌面在线 |
| 12 | `phone_status` | 手机 | 常驻 |
| 13 | `phone_observe` | 手机 | 手机在线 |
| 14 | `phone_screenshot` | 手机 | 手机在线 |
| 15 | `phone_screen_ocr` | 手机 | 手机在线 |
| 16 | `phone_launch_app` | 手机 | 手机在线 |
| 17 | `phone_action` | 手机 | 手机在线 |
| 18 | `phone_play_music` | 手机 | 手机在线 |
| 19 | `phone_wechat_send` | 手机 | 手机在线 |
| 20 | `phone_wechat_sticker` | 手机 | 手机在线 |
| 21 | `phone_xiaohongshu` | 手机 | 手机在线 |
| 22 | `phone_douyin` | 手机 | 手机在线 |
| 23 | `phone_bilibili` | 手机 | 手机在线 |
| 24 | `phone_notifications` | 手机 | 手机在线 |
| 25 | `phone_stop` | 手机 | 手机在线 |
| 26 | `phone_run_task` | 手机 | 手机在线 |
| 27 | `propose_relationship` | 关系 | 常驻 |
| 28 | `respond_relationship` | 关系 | 常驻 |
| 29 | `pause_proactive_contact` | 主动 | 关键词 |
| 30 | `resume_proactive_contact` | 主动 | 关键词 |
| 31 | `create_chat_schedule` | 提醒 | 常驻 |
| 32 | `list_chat_schedules` | 提醒 | 常驻 |
| 33 | `cancel_chat_schedule` | 提醒 | 常驻 |

## 5. 自主行动边界（临时）

阶段 3 按产品决定删除了设备工具描述中的"仅在用户明确要求时使用"，规则层 `natural-dialogue.md` 第 9 条同步改为允许自主使用，但保留三条事实边界：

1. 隐私读取（摄像头、屏幕内容）先说明用途，让用户有机会拒绝。
2. 对外发送（微信消息）与修改文件类任务（DSH）先说明。
3. 失败、被拒绝或设备离线时如实说明，不假装完成。

电脑端仍保留本地批准窗口（代码事实，不依赖提示词）。细粒度主动性边界待专门设计。

## 6. 已知偏差

- `search_web` 可用性判断仍有两处（`container._register_web_search_if_configured` 与 `route_call_tools` 调用处），条件一致但应抽公共判断。
- 手机端没有类似电脑端的本地批准机制，自主操作手机的风险高于电脑，待主动性设计时统一。
- `phone_action` 的 `max_calls` 已对齐为 4；其余 per-tool 限额与全局一致。
- 深谈长文与交付层存在形态分歧：规则层要求"1 条完整长文本"，但模型用空行分段后，`build_natural_delivery_plan` 会按段落拆成多条气泡（实测 444 字拆成 6 条）。是否接受这种"长文分段显示"待产品确认。

## 7. 棘轮与阶段门槛

`CHAT_TOKEN_BUDGET` 锁的是**注册面全量**，不随逐轮选择变化；新增工具仍会触发失败。

| 阶段 | 完成条件 | 注册面工具数 | 注册面 token 上限 |
| --- | --- | ---: | ---: |
| 0 | 快照建立 | 35 | 5,200 |
| 1 | 删时间工具、死字段，搜索条件注册 | 33 | 4,700 |
| 2 | 设备在线感知 + 条件注入 | 33 | 4,700 |
| 3（当前） | 工具描述瘦身、提示去重、规则归位 | 33 | 4,300（实测 4,149） |

## 8. 本地运行

```powershell
# 工作目录：Echo-backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

本地验证时关闭会自动触达用户的后台任务：

```powershell
$env:PRESENCE_ENABLED="false"
$env:PROACTIVE_CHAT_ENABLED="false"
$env:DAILY_LETTER_ENABLED="false"
$env:PUSH_ENABLED="false"
```

Android 调试包：

```powershell
cd app
flutter build apk --debug --target-platform android-arm64
adb reverse tcp:8000 tcp:8000
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

## 9. 阶段改动记录

### 阶段 0（2026-11-10）

- 新增注册面快照与 token 棘轮测试。
- 修复 `test_relationship_interface` 的测试隔离（补 patch + 无 DB 跳过）。
- 新增本文档。未修改生产代码。

### 阶段 1（2026-11-10）

- 删除时间工具整条链（`time_tools.py`、`Clock` / `SystemClock` / `resolve_local_time`、测试），时间统一由 `context_builder` 注入。
- `search_web` 改为条件注册。
- 删除 `ToolRisk` 与 `risk_level` / `is_idempotent` / `allow_proactive`。
- 验证：手机端问时间回答准确，`agent_tool_calls` 显示只调用了交付工具。

### 阶段 2（2026-11-10）

- 新增 `domain/tool_selection.py`（纯函数）与 `application/tool_availability.py`（线程池查在线状态）。
- `run_chat_agent` 在 chat 模式计算选择集，复用既有 `allowed_tool_names`。
- 验证：设备离线时问"看我的电脑"，模型只调 `desktop_status` 并如实回答未配对。

### 阶段 3（2026-11-11）

- 删除 `CHAT_BEAT_INSTRUCTION`（每轮 415 字符的独立 system），气泡与贴纸规则收敛到 `natural-dialogue.md` 第 5 条唯一完整版；修复规则文件编号（原缺第 9 条）。
- `CHAT_DEEP_TALK_INSTRUCTION` 精简（92 → 55 字符），去掉与规则层重复的"不要拆气泡"。
- `mode guidance.chat` 只保留渠道形态，删除工具操作流程。
- 工具描述瘦身：`emit_chat_beats` 181 → 约 45、`send_sticker` 201 → 约 75；桌面/手机描述删除"仅在用户明确要求时使用"，保留能力边界与本地批准事实；`list` / `cancel_chat_schedule` 改中文。
- `phone_action` 的 `max_calls` 8 → 4，与全局 `agent_max_tool_calls` 对齐。
- 规则层第 9 条改为允许自主使用设备能力，保留隐私读取、对外发送、破坏性任务三条说明义务。
- 棘轮 4,700 → 4,300。
- 验证：全量 552 passed；注册面 4,650 → 4,149 tok。实测三种场景：明确要求分条时模型调用 `emit_chat_beats`；普通闲聊由交付层自然拆成 2 条；深谈长文（444 字）被拆成 6 条气泡。

### 阶段 4（2026-11-11）

- `AgentToolResult` 新增 `published_segments` / `sticker_placement`，由工具自己声明交付形态；runtime 移除对 `emit_chat_beats` / `send_sticker` 工具名的特判。
- 新增 `domain/turn_policy.py`：`TurnProfile` 承载模式差异，`initial_messages` 接管模式提示与深谈注入，`next_tool_scope` 接管 call 模式动态收窄。
- 新增 `application/delivery_gate.py`：文本→计划、元数据前缀恢复、重试消息装配、贴纸声称检查；`sanitize_time_metadata` / `prefix_codepoints` 下沉到 `domain/delivery.py`，避免 domain 反向依赖 application。
- 新增 `application/turn_fallbacks.py`：确定性兜底文案。
- 新增 `application/model_loop.py`：模型↔工具循环与交付检查点，返回不可变 `LoopOutcome`。
- 新增 `application/agent_runtime.py`：`AgentTurn` 输入 → `AgentTurnResult` 输出，统一记录 run 开始/结束。
- `orchestrate_chat.py` 从 1062 行降到 80 行，只做构造与参数翻译。
- 测试同步：`_build_initial_messages` 改为 `TurnPolicy.initial_messages`，`_deterministic_tool_confirmation` 改为 `TurnFallbacks`；容器装配断言改走 `agent.runtime.loop.model`。
- 验证：架构检查通过；ruff 通过；全量 552 passed；手机端实测普通闲聊与分条要求均正常（2 条气泡），轨迹记录正常。
- 说明：拆分后总代码量略有增加（接口与文档成本），`model_loop.py` 仍较大（760 行，含循环与模型调用辅助），后续可继续细分。

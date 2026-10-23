"""Build an offline guide from verified source locations; never load runtime settings."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BACKEND = REPO / "Echo-backend"
refs = {}


def ref(path, needle, title):
    relative = "Echo-backend/" + path
    source = (REPO / relative).read_text(encoding="utf-8")
    lines = source.splitlines()
    matches = [i for i, line in enumerate(lines) if needle in line]
    assert matches, (relative, needle)
    index = matches[0]
    key = "r" + str(len(refs) + 1)
    refs[key] = {
        "id": key, "file": relative, "line": index + 1, "symbol": needle,
        "title": title, "excerpt": "\n".join(lines[index:index + 12]),
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }
    return key


P = {
    "renderer": "shared/prompting/renderer.py",
    "builder": "features/chat/infrastructure/context_builder.py",
    "agent": "features/agent/application/orchestrate_chat.py",
    "settings": "shared/config/settings.py",
    "history": "features/chat/infrastructure/postgres_repositories.py",
    "identity": "features/assistant_persona/infrastructure/default_persona.py",
}


def r(key, needle, title):
    return ref(P.get(key, key), needle, title)


sources = []


def source(id, title, origin, summary, steps, condition, validation, change, references):
    sources.append(dict(id=id, title=title, origin=origin, summary=summary, steps=steps,
                        condition=condition, validation=validation, change=change, refs=references))


source("config", "产品定位与配置", "人工维护 · 配置", "定义 Echo 是什么产品，并提供版本、预算和模式参数。",
       ["开发者在 Settings 中写默认 system_prompt 和配置字段。", "Pydantic Settings 读取配置；环境变量与声明的 .env 可覆盖默认值。", "get_settings() 缓存 Settings；Context Builder 将 system_prompt、prompt_version 传给共享渲染器。"],
       "普通聊天会加入产品定位。页面展示源码默认值，不代表部署中的实际覆盖值。",
       "配置字段经过类型和范围检查。产品定位正文是提示文本，不是权限校验。",
       "产品定位改 Settings.system_prompt 或部署配置；预算改对应配置字段。重启或重新加载进程后确认有效值。",
       [r("settings", "class Settings", "配置模型"), r("settings", "model_config =", "配置来源声明"),
        r("settings", "system_prompt: str", "产品定位默认正文"), r("settings", "def get_settings", "缓存配置入口"),
        r("settings", "persona_prompt_max_tokens: int", "偏好预算默认值"),
        r("settings", "memory_prompt_max_tokens: int", "记忆预算默认值"),
        r("settings", "summary_prompt_max_tokens: int", "摘要注入预算默认值"),
        r("renderer", "def _truncate_to_token_budget", "局部截断与估算")])
source("rules", "四份常驻／渠道规则", "人工维护 · Markdown", "规则正文已经外置，但仍由渲染器显式选择。",
       ["开发者维护 prompts/rules/ 下的四个 Markdown 文件。", "renderer 模块导入时，_load_rule() 通过 Path.read_text(encoding='utf-8') 读取正文。", "普通聊天加入 safety、natural-dialogue、response-calibration；通话改用 safety 与 call-dialogue。"],
       "安全规则常驻；自然对话、策略校准与通话规则按 conversation_mode 分支选择。并非每轮都注入四份。",
       "加载失败会抛异常；行为是否遵守仍取决于模型及后续有限门禁。MD 文件不会自己执行校验。",
       "改对应规则 MD；当前不是每轮热读，通常需要进程重载。单纯把文字移到 MD 不会减少输入 token。",
       [r("renderer", "def _load_rule", "文件加载器"), r("renderer", "BASELINE_SAFETY_POLICY =", "导入时加载"),
        r("renderer", "def render_prompt_layers", "规则选择与消息组装"),
        *[r("prompts/rules/" + name, "[", title) for name, title in [
            ("baseline-safety.md", "安全正文"), ("natural-dialogue.md", "自然对话正文"),
            ("response-calibration.md", "策略校准正文"), ("call-dialogue.md", "通话正文")]]])
source("identity", "助手身份与人格", "人工维护 · 结构化对象", "Echo 的固定人设由开发者写好，不是每次聊天临时生成。",
       ["default_persona.py 定义 ECHO_PERSONA_V2：角色、特质、交流原则、允许披露与禁止声称。", "assistant_persona_version 指定版本，get_assistant_persona() 经公开入口取回对象。", "render_assistant_persona() 转成一条 system 文本，连同该对象里的所有 dialogue_examples 一起加入。"],
       "正常组装会读取已配置人格；未知版本报错。旧 echo-persona-v1 配置当前也映射到 V2。",
       "对象有结构合同与版本解析；人格措辞本身主要是提示约束。当前没有按任务检索人格片段。",
       "改 default_persona.py 的内容源；渲染机制在 shared/prompting/renderer.py。当前人设正文尚未外置为 MD。",
       [r("identity", "ECHO_PERSONA_V2 =", "人设正文"), r("identity", "_PERSONAS =", "版本映射"),
        r("features/assistant_persona/public.py", "def get_assistant_persona", "业务公开入口"),
        r("renderer", "def render_assistant_persona", "人格转成消息")])
source("examples", "人格中的 Few-shot", "人工维护 · 虚构示范", "当前示例嵌在人格消息里，没有独立检索、挑选或预算模块。",
       ["开发者在 ECHO_PERSONA_V2.dialogue_examples 写输入／回复对。", "render_assistant_persona() 逐对渲染，标注为虚构口吻示例。", "整组示例随人格一同进入 system，不是额外追加的真实 user／assistant 历史。"],
       "人格存在时随之加入全部示例；不是必须放在请求末尾的一个独立层。",
       "通过提示标明不是用户事实、不要写入记忆；不是数据库历史隔离的自动证明。",
       "当前改 default_persona.py 的 dialogue_examples；规范批准按需管理，但完整资产注册／选择尚未实现。",
       [r("identity", "dialogue_examples=", "示例内容"), r("renderer", "def render_assistant_persona", "示例所在消息")])
source("preferences", "用户显式偏好", "用户填写 · 数据库", "persona feature 管的是用户偏好，与助手人格属于不同材料。",
       ["用户提交称呼、回复风格、长度、支持方式等设置，接口和领域规则先校验。", "PersonaManagementService.update() 通过仓储写入 user_personas。", "get_persona(user_id) 读取；没设置时生成默认偏好。render_persona() 映射为中文 guidance 并处理自由文本。"],
       "偏好对象存在且 enabled 时加入；默认 enabled 的偏好也会加入。读取异常时跳过。无账号私人数据权限的声纹角色不读取。",
       "请求结构、枚举、长度、首次设置称呼要求有代码校验；文本经过边界字符处理和局部长度截断。",
       "值由用户设置修改；允许字段／校验改 persona feature，提示措辞映射改共享 renderer。",
       [r("features/persona/interface/schemas.py", "class PersonaUpdateRequest", "请求字段"),
        r("features/persona/domain/entities.py", "def build_user_preferences", "领域校验"),
        r("features/persona/application/persona_management.py", "def get(", "读取或默认"),
        r("features/persona/application/persona_management.py", "def update(", "写入用例"),
        r("features/persona/infrastructure/postgres_repository.py", "INSERT INTO user_personas", "持久化位置"),
        r("renderer", "def render_persona", "偏好转成文字")])
source("relationship", "相处方式与熟悉进度", "用户选择 · 规则计算 · 数据库", "朋友或 AI 恋人由用户选择；熟悉进度独立积累，不由模型自行宣布。",
       ["已保存对话经 record_turn() 检测边界、正向反馈等信号，推进状态并记录事件。", "PUT /relationship/me 保存选择到 relationship_states.relationship_mode；重置进度保留类型。", "本轮 get_relationship_context() 读取状态，结合当前用户原话、关系节奏及亲昵偏好计算表达上限。"],
       "常规会注入关系 guidance；读取失败或私密数据隔离场景回退到 new／normal／contextual，不省略该 guidance。",
       "类型仅接受 friend／ai_partner，并按已鉴权用户保存；阶段与信号由规则计算，本轮边界立即影响表达。不是对真实心理的测量。",
       "阶段和信号规则在 relationship/domain/rules.py；模型看到的措辞在 render_relationship_guidance()。",
       [r("features/relationship/application/relationship_management.py", "def get_context", "读取当前关系上下文"),
        r("features/relationship/application/relationship_management.py", "def record_turn", "保存后推进"),
        r("features/relationship/domain/rules.py", "def build_relationship_context", "结合本轮信号"),
        r("features/relationship/domain/rules.py", "def advance_relationship_state", "状态推进"),
        r("features/relationship/infrastructure/postgres_repository.py", "INSERT INTO relationship_states", "状态存储"),
        r("renderer", "def render_relationship_guidance", "关系转成文字")])
source("memory", "跨会话长期记忆", "模型抽取 · 校验后存储", "先从真实对话抽取保存，后续请求再按当前输入召回。",
       ["回复持久化后，记忆服务经抽取门槛创建持久任务；执行时让模型提出 create／update／deactivate／ignore 等操作。", "程序解析结果、检查类型、置信度、目标及可用来源编号，再写 user_memories，并维护 memory_embeddings。", "本轮检索先读取最多 200 条活跃记忆映射；有活跃记忆时，将当前输入交给 Embedding 服务转成向量，这会产生额外的嵌入请求。", "从 memory_embeddings 读取对应模型的向量，在应用内计算余弦相似度，按相似度和重要性排序；默认阈值 0.25，最多取 5 条，再格式化。", "有向量但未命中时保持空；没有可用向量或检索异常时，回退到最多 8 条活跃记忆。"],
       "memory_enabled 开启、有账号权限并有非空结果时加入。普通通话默认跳过；明确回忆类表达才尝试扩展上下文。",
       "有结构、置信度和目标等校验；来源编号在允许范围内不等于逐条事实为真。外部文本转义与标记也不能彻底阻止提示注入。",
       "抽取规则在 memory/domain/extraction_rules.py；调度与应用操作在 memory_extraction.py；召回策略在 context_builder.py。",
       [r("features/memory/domain/extraction_rules.py", "def should_extract_memory", "抽取门槛"),
        r("features/memory/application/memory_extraction.py", "def schedule_memory_extraction", "持久任务"),
        r("features/memory/application/memory_extraction.py", "async def _apply_extracted_memory", "操作校验"),
        r("features/memory/infrastructure/postgres_repositories.py", "def add_user_memory", "记忆存储"),
        r("features/memory/infrastructure/vector_index.py", "async def retrieve_relevant_memories", "嵌入请求、评分与筛选"),
        r("features/memory/infrastructure/vector_index.py", "def _get_active_memory_map", "活跃记忆候选范围"),
        r("features/memory/infrastructure/postgres_repositories.py", "def list_memory_embedding_records", "读取已保存向量"),
        r("builder", "async def _load_long_term_memories", "召回和回退"),
        r("renderer", "def format_long_term_memories", "记忆格式化")])
source("summary", "当前会话摘要", "模型压缩 · 数据库", "摘要压缩较早对话，长期记忆保存跨会话事实，两者不是同一份数据。",
       ["保存回复后的处理检查尚未摘要的消息量，默认超过 24 条才更新，保留最近 12 条原文。", "旧摘要与较早原文一起交给模型，要求区分 USER_FACTS／DORMANT_TOPICS 并附来源编号。", "结果 strip 后非空才保存到 conversations.summary，并更新 summary_message_id。", "下次读取摘要，再取摘要边界之后的近期历史；摘要为空则跳过注入。"],
       "需要 conversation_id、memory_enabled 与账号数据权限；普通短通话默认不读取，明确回忆时可扩展。",
       "当前更新函数主要做去空白和非空检查；来源归属、区块格式与事实正确性主要靠提示，没有逐条事实核验。",
       "摘要生成／合并在 conversation_summary.py；存储在 chat 仓储；背景标签和注入截断在 shared renderer。",
       [r("features/chat/infrastructure/conversation_summary.py", "async def maybe_update_conversation_summary", "更新门槛与生成"),
        r("features/chat/infrastructure/conversation_summary.py", "def _build_summary_messages", "摘要任务提示"),
        r("history", "def get_conversation_summary", "读取摘要"),
        r("history", "def update_conversation_summary", "写入摘要和边界")])
source("history", "最近对话原文", "用户／助手 · 数据库", "保留真实消息角色与时间，不是把整份聊天记录都发给模型。",
       ["chat_messages 保存已接收用户消息与已交付助手回复。", "get_history() 按 user_id、会话、active 状态和消息边界查询，取最近若干条再恢复时间顺序。", "摘要边界之前不再重复读，当前批次第一条消息之前截止，避免当前输入又出现在历史里。", "渲染消息时间与可信附件语义；间隔较大时可另插 system 会话时间边界。"],
       "普通聊天最多读取 20 条数据库消息，不保证正好 10 轮；memory_enabled 关闭或无私人数据权限时不带历史。",
       "按用户、会话和边界过滤；排除相应无账号权限的设备语音记录。历史数量上限不是总 token 上限。",
       "读取／时间标记在 chat/infrastructure/postgres_repositories.py；普通聊天数量在 context_builder.py。",
       [r("builder", "async def build_chat_context", "聊天上下文总入口"),
        r("history", "def get_history", "历史查询与边界"), r("history", "def _render_timestamped_history", "时间和会话边界"),
        r("builder", "MAX_HISTORY_MESSAGES =", "普通聊天数量上限")])
source("time", "本轮时间上下文", "服务端计算 · 时区记录", "日期和间隔由程序提供；不是模型根据训练知识猜当前时间。",
       ["get_user_timezone() 从 proactive_chat_preferences 读时区，缺失／无效时使用配置回退值。", "读取上次对话时间，与 datetime.now(UTC) 一起交给 build_temporal_context()。", "代码计算本地日期、时间段、相对日期表达及会话间隔，序列化成 JSON；前面附一段使用 guidance。"],
       "常规组装会加入；无私人数据权限时不读私人对话时间；通话使用精简字段。",
       "时区和日期由代码解析。相对时间范围不表示事件已经发生；可靠实时查询还可由 get_current_time 工具完成。",
       "时间计算在 chat/domain/temporal_context.py；解释 JSON 的 guidance 当前写在 context_builder.py。",
       [r("history", "def get_user_timezone", "获取时区"), r("history", "def get_conversation_timing", "对话时间"),
        r("features/chat/domain/temporal_context.py", "def build_temporal_context", "计算时间事实"),
        r("builder", "temporal_guidance =", "时间使用指引")])
source("focus", "当前轮表达指引", "规则判断 · 动态文字", "根据近期对话判断追问和问候是否需要收敛。",
       ["should_pause_followup_questions() 检查历史及当前输入。", "should_suppress_repeated_greeting() 结合消息和间隔判断重复问候。", "render_turn_focus_guidance() 把布尔判断转成当前轮 system 文本。"],
       "普通聊天会生成这一条消息，即使两个抑制标记都未触发。",
       "输出后 find_dialogue_style_violations() 进行有限模式检测，命中后 apply_dialogue_fallback() 清理或替换。可能误判、漏判。",
       "判断／检测在 chat/domain/dialogue_style.py；指引措辞在 shared renderer；后处理调用在 GenerateChatReply。",
       [r("features/chat/domain/dialogue_style.py", "def should_pause_followup_questions", "追问判断"),
        r("features/chat/domain/dialogue_style.py", "def should_suppress_repeated_greeting", "问候判断"),
        r("renderer", "def render_turn_focus_guidance", "指引渲染"),
        r("features/chat/domain/dialogue_style.py", "def find_dialogue_style_violations", "有限表达检测")])
source("input", "当前用户任务与附件", "本轮输入 · 已接收批次", "应用要求与用户任务分开：用户本轮说的话仍作为 user 输入。",
       ["后台 ProcessChatTurns 取已接收消息组成批次，用 combined_content 准备回复。", "GenerateChatReply.prepare() 调用上下文构建；当前批次正文在历史之后追加为 user。", "若有可信表情语义，Agent 另在前部插入一条说明；这不代表用户请求再发一张表情。"],
       "本页主线是普通文字聊天。主动触发使用 system 任务消息；明确相对提醒创建成功时有直接确认分支，可不请求模型。",
       "消息接收、身份、批次和业务分支负责输入可用性；可信附件语义不等于原始自由文本天然可信。",
       "批次处理在 process_turns.py，任务编排在 generate_reply.py，当前输入角色选择在 _turn_input_message()。",
       [r("features/chat/application/process_turns.py", "async def run_once", "后台入口"),
        r("features/chat/application/generate_reply.py", "async def prepare", "准备回复"),
        r("builder", "def _turn_input_message", "用户与主动触发的角色"),
        r("agent", "clean_intent = sticker_intent.strip()", "附件语义插入")])
source("agent", "Agent 执行与交付指令", "人工维护 · 场景分支", "在基础上下文前再加一条 system，约束工具事实与回复交付方式。",
       ["_build_initial_messages() 根据 chat／call／proactive／daily_letter 选择执行、表情和交付要求。", "将 orchestration_rule + sticker_rule + delivery_rule 合成 instruction。", "result = [instruction, *context_messages]，因此 renderer 中安全层排第一不等于最终请求第一条。"],
       "进入统一 Agent 回路时加入；有附件语义时插在 instruction 后；通话还可能插入路由指令。",
       "这些文字帮助模型理解；执行次数、模式、时限等仍由 Agent／ToolExecutor 代码控制。",
       "应用执行合同在 agent/application/orchestrate_chat.py；不要为了集中提示词，把实际业务执行也搬入 shared。",
       [r("agent", "def _build_initial_messages", "Agent 前置组装"), r("agent", "result = [instruction, *context_messages]", "最终前缀"),
        r("agent", "async def execute(", "模型和工具主回路")])
source("tools", "本次可用工具描述", "实际注册 · 参数模型", "tools 是请求的独立字段，不是普通聊天中的一段伪工具说明。",
       ["agent/infrastructure/container.py 将实际工具 handler、规格和参数模型注册到 ToolRegistry。", "model_descriptions() 按 allowed_modes 及本次允许名称筛选。", "ToolDefinition.model_description() 从 arguments_model.model_json_schema() 生成参数 schema；Provider 连同 messages、tool_choice 一起发送。"],
       "实际工具集合由配置、渠道、路由与当前步骤决定；不是注册过就每次全部可用。来信任务无聊天工具。",
       "Agent 检查本步白名单和整轮预算；执行器检查名称、模式、同轮重复原始参数、次数、Pydantic 参数和超时，再进入业务 handler。",
       "工具规格／模型和 handler 在实际 tools 文件；注册在 container；不要另写一份 MD 参数定义造成不一致。",
       [r("features/agent/infrastructure/container.py", "def get_chat_agent", "工具装配"),
        r("features/agent/domain/tools.py", "def model_description(", "从模型生成 schema"),
        r("features/agent/domain/tools.py", "def model_descriptions(", "筛选工具"),
        r("features/agent/application/execute_tool.py", "async def execute(", "执行门禁"),
        r("features/agent/infrastructure/model.py", "async def complete(", "请求模型适配器")])
source("results", "本轮工具调用与回填", "模型申请 · 实际执行结果", "描述定义能力，执行结果才说明动作有没有完成。",
       ["模型返回调用申请后，保留 assistant.tool_calls，含调用 id、工具名和参数。", "执行器实际执行或返回拒绝／失败／超时，Agent 按相同 call_id 构造 role=tool 消息。", "结果使用适合给模型的 safe_for_model 与状态／错误信息，追加到同一消息列表后再次请求模型。"],
       "只在本轮发生工具调用时追加；受步骤、次数与总时间预算限制。这里不是自动重放全部历史工具轨迹。",
       "调用与结果按 id 配对；业务 handler 还需自己的归属与有效性检查。同轮相同参数去重不能替代跨轮幂等。",
       "消息协议在 _assistant_tool_call_message() 与 _tool_result_message()；执行规则在 ToolExecutor 和具体业务用例。",
       [r("agent", "def _assistant_tool_call_message", "调用申请消息"), r("agent", "def _tool_result_message", "工具结果消息"),
        r("agent", "agent_messages.append(self._tool_result_message(tool_result))", "结果加入同轮"),
        r("features/agent/application/execute_tool.py", "matching_results =", "同轮去重")])
source("format", "输出格式与程序检查", "提示合同 · 有限程序门禁", "普通聊天、语音与来信有不同交付要求，格式校验不验证所有事实。",
       ["Agent delivery_rule 描述气泡、口述或来信字段；它与身份、人设不是同一个职责。", "普通聊天对最终内容做交付段检查；部分异常场景有有限重试或确定性兜底。", "每日来信通过模型适配器请求 JSON 对象，并交给来信业务校验；普通聊天没有全局 JSON 输出开关。"],
       "按任务／渠道选择；本页拼接演示以普通文字聊天为主。",
       "validate_agent_delivery_segments() 检查空段、重复段、段数、部分内部字段泄漏等；不等于通用真实性或所有提示泄漏检测。",
       "交付规则在 Agent；段检查在 agent/domain/delivery.py，保存前也有检查；JSON 开关在模型适配器。",
       [r("agent", "delivery_rule =", "交付提示分支"),
        r("features/agent/domain/delivery.py", "def validate_agent_delivery_segments", "交付段校验"),
        r("features/agent/infrastructure/model.py", 'response_format={"type": "json_object"}', "结构化输出开关"),
        r("features/chat/application/generate_reply.py", "style_violations =", "表达检查调用")])

layers = []


def layer(id, title, category, role, owner, description, source_id, preview, when="always"):
    layers.append(dict(id=id, title=title, category=category, role=role, owner=owner,
                       description=description, source=source_id, preview=preview, when=when))


layer("agent", "Agent 执行与交付要求", "规则＋输出", "system", "Agent 前置", "先把执行事实、表情策略和最终交付要求合成一条；它在最终消息列表最前面。", "agent", "[内容摘要，非原文] 使用当前真实工具；未成功执行不能声称成功；按聊天交付合同回复。")
layer("sticker", "当前附件的可信语义", "上下文", "system", "Agent 插入", "本轮有可信表情语义时插在 Agent 首条之后，不表示用户要求发送另一张。", "input", "[虚构附件示例] 当前用户消息附带的表情语义：打招呼。", "sticker")
layer("safety", "基础安全边界", "规则", "system", "共享 Renderer", "渲染器内部的第一层；最终位置在 Agent 前缀之后。", "rules", (BACKEND / "prompts/rules/baseline-safety.md").read_text(encoding="utf-8"))
layer("product", "产品定位与提示版本", "身份", "system", "共享 Renderer", "使用 Settings 的产品正文，加上 prompt_version 标记；部署覆盖值可能不同。", "config", "[内容摘要，非运行时原文] Echo 产品定位 + prompt_version。")
layer("persona", "助手人格，内含整组示例", "身份＋示例", "system", "共享 Renderer", "将人工结构化人格渲染为 system；Few-shot 就在本条内部，不独立排在末尾。", "identity", "[内容摘要，非原文] 固定角色、特质、原则、自我披露边界，以及全部 dialogue_examples。")
layer("natural", "自然对话规则", "规则", "system", "共享 Renderer", "普通文字聊天加入；通话改用 call-dialogue，不同时堆入这两份文字聊天政策。", "rules", (BACKEND / "prompts/rules/natural-dialogue.md").read_text(encoding="utf-8"))
layer("calibration", "回应策略校准", "规则", "system", "共享 Renderer", "帮助模型区分分享、求助、边界等表达；仍属于提示，而非工具授权程序。", "rules", (BACKEND / "prompts/rules/response-calibration.md").read_text(encoding="utf-8"))
layer("mode", "当前交互渠道指引", "规则", "system", "共享 Renderer", "conversation_mode=chat 决定文字聊天风格；call、proactive、daily_letter 采用不同内容。", "format", "[内容摘要，非原文] 当前是文字聊天；按即时通讯表达，按问题复杂度组织内容。")
layer("relationship", "关系阶段与表达上限", "上下文＋规则", "system", "共享 Renderer", "持久状态结合本轮信号生成 guidance；失败时仍有初识关系的回退指引。", "relationship", "[虚构状态示例] new / normal / contextual。状态是业务数据，不代表真实心理。")
layer("preferences", "用户显式偏好", "上下文", "system", "共享 Renderer", "默认启用偏好也会占一条；对象不存在、禁用或读取失败时可不加入。", "preferences", "[虚构偏好示例] 希望解释详细一点；保持自然语气。", "preferences")
layer("memory", "召回的长期记忆", "上下文", "system", "共享 Renderer", "相关性召回或无向量时回退；非空才注入，并标为背景数据。", "memory", "[虚构记忆示例，非用户事实] 用户在学习 Python。仅为演示数据块位置。", "memory")
layer("summary", "当前会话摘要", "上下文", "system", "共享 Renderer", "来自 conversations.summary；为空跳过，与最近原文由摘要边界分隔。", "summary", "[虚构摘要示例] USER_FACTS：用户想理解变量。DORMANT_TOPICS：之前讨论过学习计划。", "summary")
layer("focus", "本轮追问与问候指引", "规则", "system", "Context Builder", "由历史、输入与会话间隔计算开关，再渲染当前轮 guidance。", "focus", "[内容摘要，非原文] 回应当前输入，按判断结果收敛连续追问或重复问候。")
layer("time", "时间使用说明与时间 JSON", "上下文＋规则", "system", "Context Builder", "代码计算的时间 JSON 与解释其使用范围的指引合在一条。", "time", "[虚构时间示例] 本地日期、时区、时间段、会话间隔、相对日期解析。不是当前真实时间。")
layer("history-user", "近期原文：用户消息", "上下文", "user", "Context Builder", "示意只展示一条历史用户消息；实际按边界查询、按时间顺序追加。", "history", "[虚构历史] 我刚开始学编程。", "history")
layer("history-assistant", "近期原文：助手回复", "上下文", "assistant", "Context Builder", "保留 assistant 角色；原实现可能有更多条原文、附件语义或 system 时间边界消息。", "history", "[虚构历史] 可以从变量和简单输入输出开始。", "history")
layer("current", "本轮真实用户任务", "用户任务", "user", "Context Builder", "普通聊天放在基础上下文最后；本页内容是虚构演示，不读取真实消息。", "input", "[虚构本轮输入] 用生活里的例子解释一下变量。")
layer("call", "模型提出工具调用", "工具回路", "assistant", "Agent 后续追加", "模型给出 tool_calls；这只是调用申请，并不说明执行成功。", "results", "[虚构协议示例] tool_calls: call_demo → get_current_time(timezone=Asia/Shanghai)。", "toolRound")
layer("result", "实际工具结果", "工具回路", "tool", "Agent 后续追加", "结果通过 tool_call_id=call_demo 配对；成功、失败、无结果或超时都必须如实反馈。", "results", "[虚构协议示例] tool_call_id=call_demo；status=completed；具体内容来自实际工具。", "toolRound")

diagrams = []
diagram_copy = []


def diagram(title, groups, nodes, edges, note):
    prefix = "d" + str(len(diagrams) + 1)
    membership = {node: f"{prefix}g{i}" for i, (_, ids) in enumerate(groups, 1) for node in ids}
    diagrams.append({"id": prefix, "title": title, "type": "flowchart",
        "layout": {"direction": "TB", "rankSpacing": "normal", "edgeRouting": "curved"},
        "groups": [{"id": f"{prefix}g{i}", "label": label, "nodeIds": [f"{prefix}n{n}" for n in ids]} for i, (label, ids) in enumerate(groups, 1)],
        "nodes": [{"id": f"{prefix}n{i}", "label": label, "kind": kind, "group": membership[i]} for i, (label, kind, _, _) in enumerate(nodes, 1)],
        "edges": [{"id": f"{prefix}e{i}", "from": f"{prefix}n{a}", "to": f"{prefix}n{b}", "label": label, "kind": kind} for i, (a, b, label, kind) in enumerate(edges, 1)],
        "notes": [note, "分组用节点颜色与详情标识；节点位置和连线由本地 Dagre 自动计算。"]})
    diagram_copy.append({f"{prefix}n{i}": {"description": text, "source": sid} for i, (_, _, text, sid) in enumerate(nodes, 1)})


diagram("从读取材料，到一份模型请求", [("业务准备", [1, 2, 3, 4, 5]), ("共享机制", [6]), ("请求组装", [7, 8, 9, 10, 11])], [
    ("已接收消息批次", "start", "后台取已保存批次，准备本轮回复；明确提醒成功有直接确认的例外路径。", "input"),
    ("准备本轮回复", "process", "GenerateChatReply.prepare() 编排普通聊天并调用上下文端口。", "input"),
    ("文件与配置", "data", "配置、人格对象与规则 Markdown 是人工维护的稳定来源。", "config"),
    ("数据库与计算", "data", "偏好、关系、记忆、摘要、近期消息和时间进入本轮材料集合。", "memory"),
    ("读取并选择材料", "process", "Context Builder 按用户、会话、模式、隐私条件与召回结果读取。各来源不是每次都存在。", "history"),
    ("渲染基础消息", "service", "shared/prompting/renderer.py 将规则、人格与已选背景转成 system 消息。", "identity"),
    ("追加本轮和历史", "process", "Builder 追加当前轮 guidance、时间 JSON、近期原文与当前输入。", "time"),
    ("前置执行合同", "process", "Agent 把执行和交付 instruction 放在最前，并按需插入附件语义。", "agent"),
    ("筛选工具描述", "service", "工具由实际参数模型生成 schema，再按模式和允许名称筛选。", "tools"),
    ("请求输入字段", "data", "messages 与 tools 两路在请求层汇合；tools 不伪装成历史或当前用户原话。", "tools"),
    ("发送模型请求", "service", "模型适配器交给 Provider。最终字段还有 tool_choice、温度、输出上限等。", "tools")],
    [(1, 2, "", "flow"), (2, 5, "常规路径", "flow"), (3, 5, "稳定材料", "data"), (4, 5, "动态材料", "data"), (5, 6, "", "flow"), (6, 7, "", "flow"), (7, 8, "", "flow"), (8, 10, "messages", "data"), (9, 10, "tools", "data"), (10, 11, "", "flow")],
    "主链从上到下；文件、数据库作为来源支路，工具在请求处汇入。此图是步骤概括，消息逐条顺序见下方拼接演示。")
diagram("动态材料如何产生，并供下一轮读取", [("已保存对话", [1]), ("长期记忆", [2, 3, 4, 5]), ("摘要", [6, 7, 8]), ("关系", [9, 10]), ("后续读取", [11])], [
    ("回复已持久化", "start", "保存后的处理准备后续材料；这不是在模型内部自动形成永久记忆。", "input"),
    ("记忆抽取门槛", "decision", "先判断是否值得抽取，再创建可恢复的持久任务。", "memory"),
    ("模型提出记忆", "service", "模型提出结构化操作，尚不能直接写库。", "memory"),
    ("检查并应用操作", "process", "类型、置信度、目标及允许来源等通过后，应用记忆操作。", "memory"),
    ("记忆与向量存储", "data", "user_memories 保存事实条目，memory_embeddings 支持相关性检索。", "memory"),
    ("摘要数量门槛", "decision", "未摘要消息默认超过 24 条才尝试，保留最近 12 条原文。", "summary"),
    ("模型合并摘要", "service", "旧摘要加较早消息生成新摘要；事实归属主要靠提示要求。", "summary"),
    ("摘要与覆盖边界", "data", "非空结果写 conversations.summary，并更新 summary_message_id。", "summary"),
    ("规则检测关系信号", "process", "信号与进度由确定性规则处理；不是模型给自己评定关系。", "relationship"),
    ("关系状态存储", "data", "保存关系状态与事件，为后续阶段表达提供数据。", "relationship"),
    ("后续请求按需读", "process", "已保存材料供后续请求读取；异步记忆任务可能尚未完成，不保证紧接下一轮一定可见。", "memory")],
    [(1, 2, "记忆分支", "flow"), (2, 3, "达到门槛", "flow"), (3, 4, "", "flow"), (4, 5, "有效操作", "data"), (5, 11, "按输入召回", "data"), (1, 6, "摘要分支", "flow"), (6, 7, "达到门槛", "flow"), (7, 8, "非空结果", "data"), (8, 11, "按会话读取", "data"), (1, 9, "关系分支", "flow"), (9, 10, "", "data"), (10, 11, "状态加本轮", "data")],
    "记忆、摘要、关系三条分支并排。未达到门槛时跳过该分支，省略跳过连线以避免交叉。")
diagram("工具调用后，上下文怎样继续增长", [("请求与模型", [1, 2, 3, 8]), ("受限执行", [4, 5, 6, 7]), ("交付", [9])], [
    ("初始消息与工具", "data", "初始 messages 配合当前步骤可用 tools 送入模型。", "tools"),
    ("模型生成", "service", "模型可以提出调用，也可以给出最终文本。", "agent"),
    ("需要工具吗", "decision", "工具请求是申请，必须经程序门禁，不能据此宣称已完成动作。", "results"),
    ("保留调用申请", "data", "追加 assistant.tool_calls，保留每个 call_id。", "results"),
    ("程序校验与预算", "decision", "白名单、模式、同轮重复、次数、参数、总时限与执行超时共同限制。", "tools"),
    ("执行或返回失败", "service", "通过校验调用业务 handler；拒绝、失败和超时也返回真实状态。", "results"),
    ("回填配对结果", "data", "追加 role=tool，通过 tool_call_id 对应申请。", "results"),
    ("携带结果再请求", "process", "保留先前上下文与本轮工具结果，再请求模型；不是只发送工具返回的一小段。", "results"),
    ("检查后交付回复", "process", "模型给出最终内容后进入表达和交付检查。回路预算耗尽还有受限收尾路径。", "format")],
    [(1, 2, "", "flow"), (2, 3, "", "flow"), (3, 4, "提出调用", "flow"), (4, 5, "", "flow"), (5, 6, "允许或拒绝", "flow"), (6, 7, "真实状态", "data"), (7, 8, "", "flow"), (8, 2, "预算内继续", "optional"), (3, 9, "最终文本", "flow")],
    "主回路从上到下；再次请求的回边走外围。多个工具调用在节点详情说明，不展开重复平行线。")

# Fail the build on invalid semantic specs or stale references.
all_ids = set()
for d in diagrams:
    assert len(d["nodes"]) <= 12
    node_ids = {n["id"] for n in d["nodes"]}
    assert len(node_ids) == len(d["nodes"])
    used, pairs = set(), set()
    for item in d["nodes"] + d["edges"]:
        assert item["id"] not in all_ids
        all_ids.add(item["id"])
        if "label" in item:
            assert len(item["label"]) <= (12 if "kind" in item and "from" not in item else 8), item
    for e in d["edges"]:
        assert e["from"] in node_ids and e["to"] in node_ids and e["from"] != e["to"]
        assert (e["from"], e["to"]) not in pairs
        pairs.add((e["from"], e["to"]))
        used.update((e["from"], e["to"]))
    assert used == node_ids
    assert {n for g in d["groups"] for n in g["nodeIds"]} == node_ids

persona_ast = ast.parse((BACKEND / P["identity"]).read_text(encoding="utf-8"))
persona_call = next(n.value for n in persona_ast.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ECHO_PERSONA_V2" for t in n.targets))
examples = ast.literal_eval(next(k.value for k in persona_call.keywords if k.arg == "dialogue_examples"))
data = {"snapshot": "2026-10-23", "scope": "普通文字聊天；源码快照，不是实时请求追踪", "sources": sources,
        "references": refs, "layers": layers, "diagrams": diagrams, "diagramCopy": diagram_copy,
        "examples": examples, "metrics": json.loads((HERE.parent / "persona-prompt-review/current-prompt-metrics.json").read_text(encoding="utf-8"))}
engine = (HERE.parent / "chat-flow-page/vendor/dagre.min.js").read_text(encoding="utf-8")
template = (HERE / "template.html").read_text(encoding="utf-8")
assert template.count("__GUIDE_DATA__") == template.count("__DAGRE_ENGINE__") == 1
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
html = template.replace("__GUIDE_DATA__", payload).replace("__DAGRE_ENGINE__", engine)
(HERE / "index.html").write_text(html, encoding="utf-8")
(HERE / "diagrams.json").write_text(json.dumps({"diagrams": diagrams}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Built offline HTML: {len(sources)} sources, {len(refs)} verified references, {len(layers)} message entries, {len(diagrams)} diagrams.")

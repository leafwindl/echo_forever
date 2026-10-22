"""Build a source-linked, offline context and rules explainer."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
REPO = ROOT.parents[1]
SHARED = ROOT.parent / 'chat-flow-page'
CONTEXT = ROOT.parent / 'chat-context-page'

paths = {
    'settings': 'shared/config/settings.py',
    'assistant': 'features/assistant_persona/infrastructure/default_persona.py',
    'assistant_public': 'features/assistant_persona/public.py',
    'pref_schema': 'features/persona/interface/schemas.py',
    'pref_route': 'features/persona/interface/router.py',
    'pref_domain': 'features/persona/domain/entities.py',
    'pref_service': 'features/persona/application/persona_management.py',
    'pref_repo': 'features/persona/infrastructure/postgres_repository.py',
    'relation_service': 'features/relationship/application/relationship_management.py',
    'relation_rules': 'features/relationship/domain/rules.py',
    'relation_repo': 'features/relationship/infrastructure/postgres_repository.py',
    'context': 'features/chat/infrastructure/context_builder.py',
    'renderer': 'shared/prompting/renderer.py',
    'history': 'features/chat/infrastructure/postgres_repositories.py',
    'summary': 'features/chat/infrastructure/conversation_summary.py',
    'time': 'features/chat/domain/temporal_context.py',
    'style': 'features/chat/domain/dialogue_style.py',
    'generate': 'features/chat/application/generate_reply.py',
    'worker': 'features/chat/application/process_turns.py',
    'chat_container': 'features/chat/infrastructure/container.py',
    'async_repo': 'features/chat/infrastructure/async_postgres_repository.py',
    'memory_rules': 'features/memory/domain/extraction_rules.py',
    'memory_service': 'features/memory/application/memory_extraction.py',
    'memory_repo': 'features/memory/infrastructure/postgres_repositories.py',
    'agent': 'features/agent/application/orchestrate_chat.py',
    'executor': 'features/agent/application/execute_tool.py',
    'tools': 'features/agent/domain/tools.py',
    'tool_defs': 'features/agent/infrastructure/tools/sticker_tools.py',
    'agent_container': 'features/agent/infrastructure/container.py',
    'delivery': 'features/agent/domain/delivery.py',
}
for key in ['assistant_persona', 'persona_feature', 'relationship_feature', 'prompt_renderer', 'context_builder', 'dialogue_style', 'agent_feature', 'memory_extractor', 'conversation_summary', 'async_chat_feature']:
    paths['test_'+key] = 'tests/test_'+key+'.py'

references = {}
def ref(key, needle, role):
    rel = 'Echo-backend/' + paths[key]
    source = (REPO / rel).read_text(encoding='utf-8')
    matches = [(i, text) for i, text in enumerate(source.splitlines(), 1) if needle in text]
    assert matches, (rel, needle)
    line = matches[0][0]
    identity = f'{key}:{needle}'
    references[identity] = {'id': identity, 'file': rel, 'line': line, 'symbol': needle, 'role': role, 'isTest': paths[key].startswith('tests/')}
    return identity

def r(key, needle, role='实现'): return ref(key, needle, role)
def t(key, needle): return ref('test_'+key, needle, '测试定义，未在本次运行')

diagrams, content = [], []
def add(title, subtitle, groups, nodes, edges, points, notes):
    prefix = f's{len(diagrams)+1}'
    membership = {i:f'{prefix}g{g}' for g,(_,items) in enumerate(groups,1) for i in items}
    diagrams.append({'id':f'diagram-{len(diagrams)+1}', 'title':title, 'type':'flowchart',
        'layout':{'direction':'TB','rankSpacing':'normal','edgeRouting':'orthogonal'},
        'groups':[{'id':f'{prefix}g{g}','label':label,'nodeIds':[f'{prefix}n{i}' for i in items]} for g,(label,items) in enumerate(groups,1)],
        'nodes':[{'id':f'{prefix}n{i}','label':label,'kind':kind,'group':membership[i]} for i,(label,kind,detail,refs) in enumerate(nodes,1)],
        'edges':[{'id':f'{prefix}e{i}','from':f'{prefix}n{a}','to':f'{prefix}n{b}','label':label,'kind':kind} for i,(a,b,label,kind) in enumerate(edges,1)],
        'notes':notes})
    content.append({'subtitle':subtitle,'points':points,'details':{f'{prefix}n{i}':detail for i,(_,_,detail,_) in enumerate(nodes,1)},
        'evidence':{f'{prefix}n{i}':refs for i,(_,_,_,refs) in enumerate(nodes,1)}})

add('产品定位和 Echo 人格，是谁写出来的？','这两项是代码中的产品配置，不是每次聊天由模型临时生成。',
    [('人工维护的定义',[1,2,3,4]),('加载与提示渲染',[5,6,7,8,9])], [
    ('产品定位默认值','data','开发者在 Settings.system_prompt 写产品定位文案。它是配置字段，不是聊天时让模型生成的身份。配置加载可能覆盖默认值；本页不读取实际 .env 或秘密值。',[r('settings','system_prompt: str','产品文案定义')]),
    ('人格版本选择','process','Settings.assistant_persona_version 选择人格版本；配置通过 Pydantic Settings 加载，并声明 .env。修改默认值与修改部署环境的有效值不是同一件事。',[r('settings','assistant_persona_version: str','人格版本选择'),r('settings','model_config =','配置加载')]),
    ('人格内容定义','data','ECHO_PERSONA_V2 是人工编写的 AssistantPersona 对象，含角色、性格、原则、自我披露边界与口吻示例。不是从用户历史中自动学习出来的人格。',[r('assistant','ECHO_PERSONA_V2 =','人格正文'),t('assistant_persona','test_echo_persona_v2_has_stable_behavior_contract')]),
    ('口吻示例','note','dialogue_examples 是人工构造的示范，帮助模型理解接话方式。Renderer 明确注明它们不是历史、不得写入用户记忆；这些要求本身仍是提示约束。',[r('assistant','dialogue_examples=','示例定义'),r('renderer','def render_assistant_persona','示例渲染'),t('prompt_renderer','test_persona_examples_are_labeled_as_fiction_not_user_history')]),
    ('加载应用配置','service','get_settings 创建并缓存 Settings。它读取配置声明的来源；本页只展示定义和默认策略，不展示环境实际覆盖结果。',[r('settings','def get_settings','配置入口')]),
    ('解析人格版本','decision','get_configured_assistant_persona 根据版本表选对象；未知版本抛出错误。当前代码把旧 echo-persona-v1 映射到 V2，避免恢复旧身份。',[r('assistant','def get_configured_assistant_persona','版本解析'),r('assistant','_PERSONAS =','版本映射'),t('assistant_persona','test_unknown_persona_version_is_rejected'),t('assistant_persona','test_existing_environment_pin_cannot_restore_the_old_identity')]),
    ('渲染产品与人格','process','render_prompt_layers 写入产品定位，render_assistant_persona 将结构化人格变成模型能读的 system 文本。配置源与最终发出的文本是两个阶段。',[r('renderer','def render_prompt_layers','层级组装'),r('renderer','def render_assistant_persona','人格转文本')]),
    ('加入基础规则','process','安全边界、自然对话、策略选择和模式指引主要定义在 prompt_renderer.py。它们与人格相邻但不是同一个配置对象。',[r('renderer','BASELINE_SAFETY_POLICY =','安全政策'),r('renderer','NATURAL_DIALOGUE_POLICY =','对话规则'),r('renderer','RESPONSE_CALIBRATION_POLICY =','策略规则')]),
    ('交给上下文构建','service','Context Builder 调用 get_assistant_persona 读取指定版本，再调用 render_prompt_layers；随后继续添加本轮时间、历史与输入。',[r('context','assistant_persona = get_assistant_persona','运行时读取'),r('assistant_public','def get_assistant_persona','模块公开入口')])],
    [(1,5,'默认配置','data'),(2,5,'版本参数','data'),(3,6,'候选对象','data'),(3,4,'示例部分','dependency'),(5,6,'指定版本','flow'),(5,7,'产品文案','data'),(6,7,'选中人格','data'),(7,8,'','flow'),(8,9,'','flow')],
    ['产品定位和人格正文由开发者维护。','版本参数决定读取哪份人格。','人格示例是示范，不是真实聊天记录。','规则文本与人格对象分开定义。'],
    ['配置与人格两条来源分支汇合到渲染步骤；示例说明放在侧边。','点击节点查看真实项目路径、定位行与测试定义。'])

add('用户偏好与关系状态，怎样产生和保存？','用户偏好来自显式设置；关系状态来自程序规则计算。',
    [('显式用户偏好',[1,2,3,4,5,6]),('计算出的关系上下文',[7,8,9,10,11,12])], [
    ('用户提交偏好','start','用户通过 Persona 接口提交称呼、回复风格、长度、支持方式等设置。它不是模型自由生成的系统提示词。',[r('pref_route','def persona_update','写入接口'),r('pref_schema','class PersonaUpdateRequest','输入字段')]),
    ('接口长度校验','decision','请求 Schema 先限制字段类型、文本长度和列表长度。这个阶段能拒绝结构不合格的请求，但并不包办所有业务枚举校验。',[r('pref_schema','class PersonaUpdateRequest','请求结构检查')]),
    ('领域字段校验','decision','build_user_preferences 归一化空白，检查允许的枚举、长度与话题列表；首次设置还由管理服务要求填写称呼。拒绝非法值属于程序校验。',[r('pref_domain','def build_user_preferences','领域校验'),r('pref_domain','def _normalize_choice','枚举白名单'),r('pref_service','def update','首次设置约束'),t('persona_feature','test_rejects_invalid_enum_and_oversized_fields')]),
    ('保存用户偏好','data','PersonaManagementService 调用 PostgresPersonaRepository，把设置写入 user_personas。更新和恢复默认只管理显式偏好，不改长期记忆或聊天历史。',[r('pref_service','def update','更新用例'),r('pref_repo','INSERT INTO user_personas','数据库持久化')]),
    ('读取或返回默认','process','get_persona 读取该用户记录；未设置时用 default_user_preferences 构造默认对象。Renderer 再把白名单值映射成中文表达偏好。',[r('pref_service','def get','读取与默认'),r('pref_domain','def default_user_preferences','默认对象'),r('renderer','def render_persona','渲染偏好')]),
    ('带入当前上下文','service','两条支路最终汇合：用户偏好成为数据层；关系阶段与表达上限成为关系指引。它们仍受产品规则、安全边界和当前输入约束。',[r('context','persona = get_persona','读取偏好'),r('renderer','def render_relationship_guidance','关系转提示')]),
    ('真实对话已保存','start','聊天回复持久化之后，后处理会记录关系信号。先记录真实对话，再更新关系状态；不是模型随口说熟悉就直接升级。',[r('generate','async def _run_post_persistence','保存后处理')]),
    ('检测结构化信号','process','detect_relationship_signals 用规则识别用户边界、认可亲近、正向关系反馈和纠正。普通开心不一定就是关系信号，匹配规则也有覆盖边界。',[r('relation_rules','def detect_relationship_signals','信号规则'),t('relationship_feature','test_positive_share_is_warm_without_becoming_relationship_signal')]),
    ('计算进度与阶段','process','advance_relationship_state 结合活跃天数、轮数、共享记忆数等计算进度；resolve_relationship_stage 根据分数与天数门槛决定阶段，亲近阶段还要求显式信号。',[r('relation_rules','def advance_relationship_state','进度计算'),r('relation_rules','def resolve_relationship_stage','阶段门槛'),t('relationship_feature','test_message_volume_alone_cannot_bypass_active_day_gate')]),
    ('保存状态与事件','data','关系仓储把状态写入 relationship_states，把结构化信号写入 relationship_events。这是业务状态，不是模型自己形成的隐藏记忆。',[r('relation_service','def record_turn','记录入口'),r('relation_repo','INSERT INTO relationship_states','状态持久化'),r('relation_repo','INSERT INTO relationship_events','信号持久化')]),
    ('下轮读取关系','process','get_relationship_context 读取已保存状态，同时考虑本轮用户表达与偏好。用户本轮明确划边界时可立即收敛，不必等待保存后的阶段变化。',[r('relation_service','def get_context','读取上下文'),r('relation_rules','def build_relationship_context','本轮修正'),t('relationship_feature','test_explicit_boundary_immediately_restrains_affection_and_warmth')]),
    ('形成表达上限','process','关系层只向模型提供阶段、温度与亲近表达上限，不应暴露内部分数和门槛，也不表示已经知道用户心理。',[r('renderer','def render_relationship_guidance','关系提示规则'),t('prompt_renderer','test_assistant_persona_and_relationship_are_independent_layers')])],
    [(1,2,'','flow'),(2,3,'结构通过','flow'),(3,4,'业务通过','flow'),(4,5,'后续读取','data'),(5,6,'偏好层','data'),(7,8,'','flow'),(8,9,'','flow'),(9,10,'','data'),(10,11,'后续读取','data'),(11,12,'','flow'),(12,6,'关系层','data')],
    ['偏好由用户提交，接口与领域分别校验。','未设置时读取默认值，不需要模型生成。','关系由规则计算后保存为业务状态。','明确边界会影响本轮表达上限。'],
    ['用户偏好与关系状态两条链并排，最后汇合到当前上下文。','为避免密集错误分支，校验失败在节点说明中解释。'])

add('长期记忆和摘要，是怎样生成的？','模型负责提出压缩或记忆内容；程序负责调度、部分校验和持久化。',
    [('长期记忆生命周期',[1,2,3,4,5,6,7]),('会话摘要生命周期',[8,9,10,11,12])], [
    ('对话回复已保存','start','生成回复后的后处理触发或调度记忆、摘要和关系更新。模型请求前读取的是已有材料，保存后才准备后续轮次的材料。',[r('generate','async def _run_post_persistence','后处理起点')]),
    ('记忆抽取门禁','decision','should_extract_memory 判断是否有值得记忆的信号；还支持周期性批量回顾。不是每条闲聊都调用记忆模型。',[r('memory_rules','def should_extract_memory','是否抽取'),r('memory_service','def schedule_memory_extraction','任务调度'),t('memory_extractor','test_gate_skips_plain_chat'),t('memory_extractor','test_periodic_batch_review_bypasses_narrow_realtime_gate')]),
    ('生成抽取任务','data','把用户输入、助手回复和可用来源消息编号写入持久任务，随后认领并执行。任务负责支持后续恢复，不把抽取直接等同于聊天回复。',[r('memory_service','def schedule_memory_extraction','创建任务'),r('memory_repo','def create_job','任务持久化')]),
    ('模型提出记忆','service','build_extraction_messages 提示模型输出 create、update、deactivate 或 ignore 等结构化操作，限定记忆类型并要求来源。模型输出还不能直接当作数据库操作。',[r('memory_rules','def build_extraction_messages','抽取 Prompt'),r('memory_service','async def extract_and_store_memories','调用抽取模型'),t('memory_extractor','test_extraction_prompt_requires_source_message_provenance')]),
    ('解析与业务检查','decision','解析 JSON，检查记忆类型、非空内容与置信度；解析目标记录、处理重复。候选来源 ID 只有命中允许集合才用于替换来源，不能把这当成对每个事实的真实性证明。',[r('memory_rules','def parse_memory_extraction','解析'),r('memory_service','async def _apply_extracted_memory','操作校验与应用')]),
    ('保存记忆与向量','data','将记忆写入 user_memories，按操作更新或失效；为内容维护 memory_embeddings。向量失败作为增强能力失败处理，不等于整轮聊天失败。',[r('memory_repo','def add_user_memory','记忆保存'),r('memory_repo','def upsert_memory_embedding_record','向量索引'),r('memory_service','async def _safe_upsert_memory_embedding','增强失败处理')]),
    ('下轮相关性召回','process','Context Builder 用当前消息检索相关记忆；默认 top_k=5，无向量等特定情况回退读取最多 8 条活跃记忆。召回内容再受局部预算约束。',[r('context','async def _load_long_term_memories','读取与回退'),r('renderer','def format_long_term_memories','记忆转提示')]),
    ('检查摘要触发条件','decision','maybe_update_conversation_summary 查看未摘要消息数量。默认超过 24 条后尝试更新，并留最近 12 条原文；数字来自配置，可被环境覆盖。',[r('summary','async def maybe_update_conversation_summary','摘要调度条件'),r('settings','conversation_summary_trigger_messages: int','触发阈值')]),
    ('组成摘要输入','process','读取已有摘要与需要压缩的历史，保留消息编号和角色。摘要 Prompt 要求用户事实只来自 user 原话，助手内容仅帮助理解指代。',[r('summary','def _build_summary_messages','摘要 Prompt'),r('summary','def _format_messages_for_summary','编号与角色')]),
    ('模型生成新摘要','service','摘要模型合并新旧内容，要求分出 USER_FACTS 和 DORMANT_TOPICS。来源编号、事实归属与区块格式主要通过 Prompt 要求。',[r('summary','async def maybe_update_conversation_summary','摘要模型调用'),t('conversation_summary','test_summary_uses_provenance_prompt_and_dedicated_generation_budget')]),
    ('保存摘要与边界','data','当前函数对模型结果做 strip 和非空检查后，保存摘要及覆盖的消息边界。此函数没有逐条验证来源事实或严格解析摘要区块，不能把 Prompt 要求视作全部已经程序验证。',[r('summary','updated_summary =','生成后检查'),r('history','def update_conversation_summary','摘要持久化')]),
    ('下轮摘要加原文','process','读取已保存摘要，叠加摘要边界之后的最近原文。摘要与记忆都属于可能出错的生成材料，应保留原始消息用于排查。',[r('context','summary_state =','读取摘要'),r('history','def get_history','最近原文')])],
    [(1,2,'记忆支路','flow'),(2,3,'需要抽取','flow'),(3,4,'执行任务','flow'),(4,5,'生成结果','data'),(5,6,'允许操作','flow'),(6,7,'未来请求','data'),(1,8,'摘要支路','flow'),(8,9,'达到条件','flow'),(9,10,'','data'),(10,11,'非空结果','data'),(11,12,'未来请求','data')],
    ['记忆提取与摘要压缩都涉及额外模型请求。','记忆操作有类型、置信度等程序检查。','摘要的事实与区块要求主要依靠 Prompt。','保存后的材料在后续请求中读取。','模型生成内容仍可能错误，需要保留原话。'],
    ['记忆与摘要两条生命周期并排，不将摘要流程接入记忆链。','门禁未通过时跳过对应生成；为减少分支交叉，跳过路径仅在节点说明中展示。'])

add('这些文件，怎样连成一次模型请求？','公开入口读材料，Renderer 转文字，Agent 再补充执行与交付约束。',
    [('模块读取与渲染',[1,2,3,4,5,6]),('模型请求与迭代',[7,8,9,10,11])], [
    ('后台生成回复','start','Worker 调用 GenerateChatReply.prepare；常规文字聊天进入上下文构建。若明确相对提醒直接创建成功，则有不经过模型的快捷分支。',[r('worker','async def run_once','后台入口'),r('generate','async def prepare','回复准备')]),
    ('读取各模块材料','process','build_chat_context 通过各模块 public 入口读取人格、偏好、关系、记忆及会话数据。模块入口是调用边界，具体保存逻辑在各自仓储。',[r('context','async def build_chat_context','组装入口')]),
    ('计算当前时间','process','从数据库取用户时区，用服务端当前时间和会话时间计算日期、相对表达与会话间隔。这些主要是代码计算，不依赖模型猜测。',[r('context','timezone_name =','时区读取'),r('time','def build_temporal_context','计算时间上下文')]),
    ('渲染基础提示层','process','render_prompt_layers 将规则、人格、模式、关系、偏好、记忆、摘要按固定顺序转成 system 消息。背景数据有标记，但仍使用 system 承载。',[r('renderer','def render_prompt_layers','固定层级'),t('prompt_renderer','test_layers_keep_safety_first_and_data_separated')]),
    ('加本轮规则与历史','process','计算是否暂缓追问、是否重复问候，追加当前轮规则和时间，再追加近期 user/assistant 历史。当前批次之前的历史边界用于避免本轮内容重复加入。',[r('context','pause_followup_questions =','当前轮判断'),r('renderer','def render_turn_focus_guidance','本轮 Prompt'),r('context','messages.extend(history)','追加历史')]),
    ('追加当前用户输入','data','当前批次作为最后的 user 输入加入基础上下文。历史与本轮消息分开，不会因为历史里出现某个旧请求就自动把它当本轮任务。',[r('context','messages.append(_turn_input_message','当前输入')]),
    ('Agent 前置约束','process','Agent._build_initial_messages 把工具事实、表情策略和最终交付要求放在基础上下文前面；因此 Renderer 的安全层在基础层中第一，不等于最终请求的第一条。',[r('agent','def _build_initial_messages','Agent 前置规则'),r('agent','result = [instruction, *context_messages]','最终消息拼接')]),
    ('注册筛选工具','process','agent/infrastructure/container.py 注册工具并读取执行上限。ToolRegistry 根据模式和允许列表输出工具描述与参数 schema，作为独立 tools 字段。',[r('agent_container','def get_chat_agent','依赖组装与注册'),r('tools','def model_descriptions','模式筛选')]),
    ('请求当前模型','service','同一轮消息列表配合工具定义提交给模型；模型给出自然回复或调用申请。人格、记忆和工具结果不会让模型自动访问未提供的数据库。',[r('agent','response, llm_timeout_retries_remaining','模型调用入口')]),
    ('实际工具结果回填','data','工具执行后把 assistant 的调用消息与对应 tool 结果加回同一消息列表。回填结果包含状态、可供模型使用的结果和错误码。',[r('agent','def _assistant_tool_call_message','模型调用消息'),r('agent','def _tool_result_message','工具结果消息')]),
    ('准备最终交付','process','Agent 受步骤数、调用数和总时间限制。得到最终回复后，进入对话表达检查和交付检查，再持久化。',[r('generate','style_violations =','表达检查调用点'),r('delivery','def validate_agent_delivery_segments','交付门禁')])],
    [(1,2,'常规路径','flow'),(2,3,'','flow'),(3,4,'','flow'),(4,5,'','flow'),(5,6,'','flow'),(6,7,'messages','data'),(7,9,'消息列表','data'),(8,9,'tools','data'),(9,10,'调用工具后','data'),(10,9,'继续同轮','data'),(9,11,'最终回复','flow')],
    ['容器负责接线，public 入口负责跨模块调用。','Renderer 把材料转成分层消息文本。','Agent 在基础提示层之前再补充规则。','工具 schema 与 messages 是不同请求材料。','执行结果会继续加入本轮模型上下文。'],
    ['从读取到模型请求纵向排列；工具定义在模型侧边汇入。','模型与工具结果回路使用外围线，不与最终交付分支交叉。'])

add('新加的规则，在哪里定义和校验？','规则不在单一文件：需要沿着定义、执行位置、失败处理和测试一起查。',
    [('模型生成之前',[1,2,3]),('工具执行与输出之后',[4,5,6,7,8,9,10,11])], [
    ('规则定义','start','大部分说话方式定义在 prompt_renderer.py；人格内容在 default_persona.py；Agent 表情、工具与交付策略在 orchestrate_chat.py。执行限制还来自配置与工具规格。',[r('renderer','NATURAL_DIALOGUE_POLICY =','行为规则'),r('assistant','ECHO_PERSONA_V2 =','人格约定'),r('agent','FINAL_RETRY_INSTRUCTION =','Agent 收尾规则')]),
    ('输入与背景处理','process','偏好先经请求和领域校验，Renderer 再做白名单映射、文本边界处理和局部预算截断。背景低权限主要是 Prompt 语义，当前并没有独立消息角色隔离。',[r('pref_domain','def build_user_preferences','偏好校验'),r('renderer','def _escape_untrusted_text','自由文本处理'),r('renderer','def _truncate_to_token_budget','局部预算')]),
    ('模型生成内容','decision','提示文本影响输出，但“不虚构”“不泄露”“不要主动恢复旧话题”等不能仅凭写入 Prompt 就保证遵守。下面只有部分情况配有程序门禁。',[r('renderer','BASELINE_SAFETY_POLICY =','模型侧政策')]),
    ('工具执行门禁','decision','ToolExecutor 检查工具存在、模式、重复原始参数、次数与参数模型，执行时限制超时；Agent 另检查本步允许工具与整轮预算。失败返回结构化原因。',[r('executor','async def execute','工具门禁'),r('agent','if call.tool_name not in step_tool_names:','当前步骤白名单'),t('agent_feature','test_executor_rejects_duplicate_tool_call')]),
    ('业务处理或拒绝','service','通过门禁才执行工具 handler；实际业务还需自己的有效性和归属检查。工具正常返回状态不替代业务幂等；跨轮防重仍需看具体动作实现。',[r('executor','definition.handler(context, arguments)','执行位置'),r('tool_defs','def register_sticker_tools','工具规格与业务绑定')]),
    ('成功声明校验','process','例如表情场景，Agent 检查是否确有成功发送结果和交付附件；无凭据声明触发有限修正或安全回复。这是特定能力规则，不是任意事实验证器。',[r('agent','def _has_successful_sticker_delivery','成功凭据检查'),t('agent_feature','test_unbacked_sticker_claim_is_rewritten_once_before_delivery')]),
    ('表达规则检测','decision','find_dialogue_style_violations 用规则检测舞台动作、虚构离线状态、多个问题、重复问候、部分无请求建议和依赖表达。匹配范围有限，会有漏检与误判。',[r('style','def find_dialogue_style_violations','表达检测'),r('generate','style_violations =','检测调用点'),t('dialogue_style','test_repeated_greeting_is_removed_by_deterministic_fallback')]),
    ('确定性兜底','process','GenerateChatReply 发现风格违规后调用 apply_dialogue_fallback，对命中的情况清理或替换为确定性回复；这里不应仅依据注释推断会额外调用模型改写。',[r('style','def apply_dialogue_fallback','兜底实现'),r('generate','reply = apply_dialogue_fallback','实际调用位置')]),
    ('交付格式校验','decision','validate_agent_delivery_segments 检查空段、重复段、段数及部分内部字段、标识或控制文本泄漏。失败会抛出交付异常；Agent 部分场景有有限格式重试。',[r('delivery','def validate_agent_delivery_segments','可交付检查'),r('delivery','def _validate_delivery_segment','内部内容模式'),t('agent_feature','test_protocol_output_is_failed_without_leaking_protocol_fragment')]),
    ('保存前再次检查','data','回复准备完成后与数据库持久化前都有交付段检查。重复检查用于挡住错误交付，但检查内容仍限于已有规则，不验证所有事实或所有提示泄漏。',[r('generate','validate_agent_delivery_segments(segments)','准备阶段'),r('async_repo','validate_agent_delivery_segments(text_segments)','持久化门禁')]),
    ('测试记录规则预期','note','测试定义描述预期行为：有的只检查 Prompt 中存在某句话，有的使用假模型测试拒绝、修正与超时。定位到测试不等于本次已运行，也不等于真实模型始终遵守。',[t('prompt_renderer','test_natural_dialogue_policy_rejects_stage_directions_and_fake_body'),t('agent_feature','test_agent_timeout_never_executes_side_effect_tool'),t('dialogue_style','test_text_affection_and_kaomoji_survive_without_fallback')])],
    [(1,2,'进入请求前','flow'),(2,3,'提示材料','data'),(3,4,'申请工具','flow'),(4,5,'允许或拒绝','flow'),(5,6,'实际结果','data'),(6,3,'结果与修正','data'),(3,7,'最终文字','flow'),(7,8,'命中违规','flow'),(7,9,'检查通过','flow'),(8,9,'修正后','flow'),(9,10,'通过','flow'),(1,11,'对应测试','dependency')],
    ['定义、运行门禁、输出兜底、测试是不同环节。','部分规则只有提示要求，没有完整程序校验。','风格检测和事实核验不是同一种检查。','测试存在不代表本次已执行或全部覆盖。','下方规则对照表可按文件与函数搜索。'],
    ['工具执行支路与最终文字支路并排；结果回填放外侧。','测试作为说明支线，不放入运行时请求主链；不为每个失败情况增加交叉线。'])

# Evidence-backed rule matrix: definition, runtime handling, tests, and limits.
rules = [
    {'name':'人格身份与口吻','definition':[r('assistant','ECHO_PERSONA_V2 ='),r('renderer','def render_assistant_persona')], 'runtime':[r('renderer','def render_prompt_layers'),r('style','def find_dialogue_style_violations')], 'tests':[t('assistant_persona','test_echo_persona_v2_has_stable_behavior_contract')], 'limit':'人格合同测试主要检查配置内容；风格检测只覆盖部分句式，不是全量语义验证。'},
    {'name':'记忆与摘要只作背景','definition':[r('renderer','BASELINE_SAFETY_POLICY ='),r('renderer','def render_turn_focus_guidance')], 'runtime':[r('renderer','def _escape_untrusted_text'),r('renderer','def render_prompt_layers')], 'tests':[t('prompt_renderer','test_persona_injection_text_cannot_forge_renderer_boundary')], 'limit':'背景仍用 system 角色。分隔与转义不等于独立权限隔离；旧话题限制主要依靠 Prompt。'},
    {'name':'不要连续追问或重复问候','definition':[r('renderer','def render_turn_focus_guidance')], 'runtime':[r('style','def should_pause_followup_questions'),r('style','def find_dialogue_style_violations'),r('style','def apply_dialogue_fallback')], 'tests':[t('dialogue_style','test_question_cooldown_after_two_consecutive_assistant_questions'),t('dialogue_style','test_repeated_greeting_is_removed_by_deterministic_fallback')], 'limit':'基于历史与文本模式判断，无法覆盖所有表达变体；应测试保留正常问句的情况。'},
    {'name':'偏好字段必须有效','definition':[r('pref_schema','class PersonaUpdateRequest'),r('pref_domain','def build_user_preferences')], 'runtime':[r('pref_service','def update')], 'tests':[t('persona_feature','test_rejects_invalid_enum_and_oversized_fields')], 'limit':'字段有效不表示自由文本中的每个事实都被核实；偏好不能修改工具授权。'},
    {'name':'关系阶段与用户边界','definition':[r('relation_rules','_PACE_THRESHOLDS ='),r('relation_rules','def detect_relationship_signals')], 'runtime':[r('relation_rules','def resolve_relationship_stage'),r('relation_rules','def build_relationship_context')], 'tests':[t('relationship_feature','test_explicit_boundary_immediately_restrains_affection_and_warmth')], 'limit':'关系状态是业务规则产物；依靠句式识别的本轮信号存在覆盖范围。'},
    {'name':'工具参数、次数与模式','definition':[r('tools','class ToolDefinition'),r('settings','agent_max_steps: int')], 'runtime':[r('executor','async def execute'),r('agent','if call.tool_name not in step_tool_names:')], 'tests':[t('agent_feature','test_executor_rejects_duplicate_tool_call'),t('agent_feature','test_call_mode_rejects_sticker_tool_even_if_model_hallucinates_it')], 'limit':'同轮原始参数去重不等于跨轮幂等；副作用动作仍需业务校验。'},
    {'name':'不能无凭据说表情已发送','definition':[r('agent','def _build_initial_messages')], 'runtime':[r('agent','def _has_successful_sticker_delivery')], 'tests':[t('agent_feature','test_unbacked_sticker_claim_is_rewritten_once_before_delivery')], 'limit':'这是表情能力的专项处理，不能推导成全部动作、全部事实都有验证器。'},
    {'name':'不交付内部协议与时间标记','definition':[r('delivery','_INTERNAL_CONTEXT_MARKER =')], 'runtime':[r('delivery','def validate_agent_delivery_segments'),r('async_repo','validate_agent_delivery_segments(text_segments)')], 'tests':[t('agent_feature','test_protocol_output_is_failed_without_leaking_protocol_fragment')], 'limit':'现有模式能挡住特定格式；不是通用敏感信息检测或事实审核。'},
    {'name':'摘要事实带来源','definition':[r('summary','def _build_summary_messages')], 'runtime':[r('summary','async def maybe_update_conversation_summary')], 'tests':[t('conversation_summary','test_summary_uses_provenance_prompt_and_dedicated_generation_budget')], 'limit':'调用链主要检查非空后保存；没有在此严格解析区块、逐条核验来源与事实。'},
    {'name':'长期记忆操作有效','definition':[r('memory_rules','def build_extraction_messages')], 'runtime':[r('memory_service','async def _apply_extracted_memory')], 'tests':[t('memory_extractor','test_extraction_prompt_requires_source_message_provenance')], 'limit':'检查类型、置信度和目标记录等不等于证明记忆内容真实；测试来源要求不等于全面事实验证。'},
]

spec = {'diagrams':diagrams}
node_ids, edge_ids = set(), set()
for d,c in zip(diagrams,content):
    assert len(d['nodes']) <= 12 and 3 <= len(c['points']) <= 5
    assert all(len(point)<=40 for point in c['points'])
    local = {n['id'] for n in d['nodes']}
    assert not node_ids & local; node_ids |= local
    pairs, connected = set(), set()
    for n in d['nodes']:
        assert len(n['label'])<=12 and c['evidence'][n['id']]
    for e in d['edges']:
        pair = (e['from'],e['to'])
        assert set(pair)<=local and pair[0]!=pair[1] and pair not in pairs
        assert e['id'] not in edge_ids and len(e['label'])<=8
        pairs.add(pair); edge_ids.add(e['id']); connected.update(pair)
    assert connected == local
(ROOT/'diagrams.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'source-index.json').write_text(json.dumps({'references':list(references.values()),'rules':rules},ensure_ascii=False,indent=2),encoding='utf-8')

template=(ROOT/'template.html').read_text(encoding='utf-8')
for key,value in [('__SPEC__',spec),('__CONTENT__',content),('__REFERENCES__',references),('__RULES__',rules)]:
    template=template.replace(key,json.dumps(value,ensure_ascii=False).replace('</','<\\/'))
template=template.replace('/*__ENGINE__*/',(SHARED/'vendor/dagre.min.js').read_text(encoding='utf-8'))
template=template.replace('__LICENSE__',(SHARED/'vendor/DAGRE-LICENSE.txt').read_text(encoding='utf-8'))
(ROOT/'index.html').write_text(template,encoding='utf-8')
print(f'Built source map: {len(diagrams)} diagrams, {len(node_ids)} nodes, {len(edge_ids)} edges, {len(references)} verified file/symbol locations, {len(rules)} rule mappings.')

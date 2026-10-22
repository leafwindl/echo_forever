"""Generate the offline context and prompt explainer using bundled Dagre."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
SHARED = ROOT.parent / 'chat-flow-page'
diagrams, content = [], []

def add(title, subtitle, direction, groups, nodes, edges, points, notes):
    prefix = f'c{len(diagrams)+1}'
    group_for = {i: f'{prefix}g{g}' for g, (_, items) in enumerate(groups, 1) for i in items}
    diagrams.append({
        'id': f'diagram-{len(diagrams)+1}', 'title': title, 'type': 'flowchart',
        'layout': {'direction': direction, 'rankSpacing': 'normal', 'edgeRouting': 'orthogonal'},
        'groups': [{'id': f'{prefix}g{g}', 'label': label, 'nodeIds': [f'{prefix}n{i}' for i in items]} for g, (label, items) in enumerate(groups, 1)],
        'nodes': [{'id': f'{prefix}n{i}', 'label': label, 'kind': kind, 'group': group_for[i]} for i, (label, kind, detail) in enumerate(nodes, 1)],
        'edges': [{'id': f'{prefix}e{i}', 'from': f'{prefix}n{a}', 'to': f'{prefix}n{b}', 'label': label, 'kind': kind} for i, (a,b,label,kind) in enumerate(edges, 1)],
        'notes': notes,
    })
    content.append({'subtitle': subtitle, 'points': points, 'details': {f'{prefix}n{i}': detail for i, (_,_,detail) in enumerate(nodes,1)}})

add('上下文从哪里来？', '模型只看到本次请求实际带入的材料，不能自动读取整个数据库。', 'LR',
    [('材料来源', [1,2,3,4,5,6,7]), ('组装与请求', [8,9,10,11])], [
    ('产品与人格配置','data','来源：后端固定规则、产品配置，以及指定版本的助手 Persona。它们定义 Echo 是谁、如何表达，以及不能做什么。'),
    ('用户偏好记录','data','来源：用户偏好模块。称呼、语气、回复长短、支持方式等白名单字段会映射为有限偏好；自由文本经过分隔符处理。'),
    ('历史与会话摘要','data','来源：聊天数据库。近期原文用于接续当前话题，旧内容由摘要模块压缩后保存。摘要是生成内容，需要追溯原话，不等于原始证据。'),
    ('长期记忆库','data','来源：记忆抽取流程保存的活跃记忆。优先按当前消息做向量检索；有向量但没有相关结果时可不加入记忆，不会为了填满而硬塞。'),
    ('关系模块','service','来源：已保存的关系状态与本轮表达判断。控制可使用的熟悉程度和亲近表达，不代表模型知道用户真实心理。'),
    ('服务端时间信息','data','来源：服务端当前时间、数据库中的用户时区、历史消息时间。用于解析相对时间、日期和会话间隔，而不是让模型猜时间。'),
    ('本轮消息批次','start','来源：本轮已接收的用户文字或表情消息。连续输入可能合并成同一批次；这是本轮需要优先回应的内容。'),
    ('组装上下文','process','Context Builder 选择并排列材料：固定规则、背景数据、当前轮提示、近期历史、当前输入。不会把全部历史直接塞进去。'),
    ('Agent 补充规则','process','Agent 在上下文前面加入工具使用、表情策略和最终交付要求。工具循环中还会追加 assistant 调用与 tool 结果消息。'),
    ('当前工具定义','data','来源：工具注册表，按聊天模式和允许列表筛选。工具名称、描述与参数结构通过请求的 tools 字段提供，不是已执行结果。'),
    ('发送模型请求','service','模型接收 messages 与可用工具定义。需要工具时先提出申请，服务端校验并执行，再把结果加入本轮消息列表继续请求。')],
    [(i,8,'','data') for i in range(1,8)]+[(8,9,'messages','data'),(9,11,'消息列表','data'),(10,11,'tools','data')],
    ['固定规则、用户背景和当前输入来源不同。','历史原文、摘要和长期记忆各司其职。','工具定义表示能力，工具结果表示执行事实。','相关背景可以为空，不要求每轮全部出现。'],
    ['材料来源纵向排列，汇入组装节点，再向右进入模型请求。','图 2 展开消息组装顺序；图 3 展开约束与执行；图 4 展开长度和召回。'])

add('送进模型的材料，按什么顺序排？', '这是消息排列顺序；“放在前面”不等于获得独立的权限隔离。', 'TB',
    [('固定规则与行为', [1,2,3,4,5]), ('背景数据', [6,7,8]), ('当前对话', [9,10,11,12])], [
    ('Agent 运行规则','process','最终请求中先放 Agent 补充的 system 消息：工具执行事实、表情策略、自然回复和交付格式。若有当前表情语义，还会在此后补充说明。'),
    ('安全与产品定位','process','Context Builder 的基础提示从安全政策和产品定位开始。安全政策明确声明：用户偏好、关系、记忆、摘要或历史不能覆盖这些规则。'),
    ('Echo 稳定人格','process','指定版本的助手 Persona 包含性格、表达原则、允许与禁止的自我声称。口吻示例是虚构示范，不是真实历史，不能变成用户记忆。'),
    ('自然对话与策略','process','文字模式注入自然对话规则与策略选择：先回应眼前内容，按寒暄、分享、求助等选择主要回应方式，避免默认说教和连续追问。'),
    ('模式与关系规则','process','模式指引说明这是文字聊天；关系指引说明阶段、互动温度和亲近表达上限。关系信息是行为约束，不是用户心理事实。'),
    ('用户偏好背景','data','偏好启用且有内容时加入。实现使用 system 消息承载，但明确标记为偏好数据；称呼、风格、长度等映射为有限表达偏好。'),
    ('相关长期记忆','data','有召回结果时才加入。用数据分隔标记说明这些内容只作背景事实，不是指令；只应在当前问题相关时使用。'),
    ('旧对话摘要','data','存在摘要时加入，标记为低权限休眠背景。历史未完成话题不是待办，不能因为摘要里记着就主动恢复或追问。'),
    ('本轮重点与时间','process','追加当前轮规则：是否暂缓追问、是否避免重复问候，以及不主动恢复旧话题。再附服务端计算的日期、时区、相对时间和会话间隔。'),
    ('近期历史原文','data','从摘要覆盖边界之后选取最近消息，并限制在当前批次之前，按时间顺序排列。普通文字聊天最多读取 20 条数据库消息；时间标注可能增加提示文本。'),
    ('当前用户输入','start','把当前批次的合并内容作为 user 消息放在历史之后，使它成为本轮直接问题。当前输入仍不能覆盖安全与工具执行规则。'),
    ('模型判断下一步','service','这时调用模型。直接回答可进入交付检查；申请工具则追加 assistant 的调用信息和对应 tool 结果，再请求模型继续。工具定义另在 tools 字段中。')],
    [(i,i+1,'','flow') for i in range(1,12)],
    ['图中相邻小层合并展示，细节可点击查看。','背景层没有内容时会跳过。','历史保留原角色，当前输入使用 user。','工具结果在本轮调用后追加，属于 tool 消息。','消息排列顺序不等于安全权限证明。'],
    ['主流程自上而下，三类分组按顺序相接，禁止手工指定节点坐标。','图 1 解释来源，图 3 解释这些规则如何落实；工具定义通过独立字段提供。'])

add('哪些靠 Prompt，哪些靠代码？', 'Prompt 告诉模型应当怎样做；执行门禁决定动作能否真的发生。', 'TB',
    [('模型侧要求', [1,2,3,4,5]), ('代码执行与结果', [6,7,8,9,10,11])], [
    ('接收组装上下文','start','接续图 2。本页把文字约束和程序限制分开讲，避免把提示词里写了规则误认为程序已经强制保证。'),
    ('提示词行为约束','process','通过 system 文案要求不泄露内部信息、不虚构经历、背景只在相关时使用、不凭口头宣称工具成功。它影响生成，但不能保证每次都遵守。'),
    ('背景分隔与转义','process','用户偏好、记忆与摘要使用数据边界标记，并处理部分括号等字符，减少自由文本伪造 Renderer 边界的机会。这不是完整的提示注入防护。'),
    ('仍使用系统角色','note','关键实现边界：上述背景目前仍使用 system 角色承载。“低权限”是提示文案中的含义，没有独立协议角色或专门权限沙箱。此说明不表示已经验证存在漏洞。'),
    ('模型输出下一步','decision','模型可能直接生成回复，也可能提出工具调用。工具申请不是已执行动作，更不是成功凭证。'),
    ('工具与次数门禁','decision','服务端校验工具是否注册、当前步骤及模式是否允许、同轮同原始参数是否重复，并检查总调用次数和单工具次数。'),
    ('参数与业务校验','decision','工具参数模型验证类型、必填项和约束；通过后由业务处理器检查自己的业务规则。不能仅靠提示模型“请传正确参数”。'),
    ('限时执行动作','service','按单工具超时与整轮剩余时间执行。未知工具、非法参数、超时和异常会返回相应状态；次数和时间限制由代码执行。'),
    ('拒绝执行并记录','data','校验失败时不执行处理器，生成对应拒绝结果。直接拒绝和真实执行的结果都按调用编号记录，并可回填模型。'),
    ('结果回填模型','data','回填实际成功、无结果、失败或超时等状态，继续受限模型回路。动作能否跨轮或进程重试防重，仍取决于具体业务幂等。'),
    ('检查回复再交付','process','直接回答或工具回路结束后检查可交付格式，应用部分表达兜底。表情发送声明还需对应成功结果支持；这些不是通用事实核验器。')],
    [(1,2,'','flow'),(2,3,'','flow'),(3,4,'实现边界','dependency'),(3,5,'','flow'),(5,11,'直接回答','flow'),(5,6,'申请工具','flow'),(6,7,'允许','flow'),(6,9,'拒绝','flow'),(7,8,'通过','flow'),(7,9,'不通过','flow'),(8,10,'真实结果','data'),(9,10,'拒绝原因','data'),(10,5,'回填再判断','data')],
    ['提示词要求属于生成约束，不能视为绝对保证。','背景虽标记低权限，实际仍用 system 承载。','工具名称、次数、参数、超时由代码检查。','输出检查不等于对整份回答做事实核验。','同轮去重不等于跨轮业务幂等。'],
    ['说明节点放在背景分隔节点旁；工具拒绝支线放在主校验链侧边。','工具结果回填使用外围回边；避免与直接回复分支交叉。'])

add('怎样控制长度，又不带错背景？', '先选材料，再做局部截断；当前还需要关注整份请求的总预算。', 'TB',
    [('历史与记忆选择', [1,2,3,4,5]), ('局部预算', [6,7,8,9,10])], [
    ('当前消息与会话','start','以当前输入作为记忆检索查询，以用户和会话标识定位历史与摘要。图中展示项目默认策略，不展示真实用户数据；配置可被部署环境覆盖。'),
    ('读取会话摘要','data','读取已保存的摘要及覆盖边界。默认未摘要消息超过 24 条后尝试更新摘要，并保留最近 12 条不压缩；摘要任务不是每次请求实时重算。'),
    ('选择近期原文','process','取摘要边界之后、当前批次之前的最近最多 20 条消息。20 条是数据库消息条数，不一定是 10 轮，也不是 20 个模型角色消息的绝对上限。'),
    ('语义召回记忆','decision','默认语义检索 top_k=5，阈值为配置值 0.25。存在向量但无相关结果时返回空；无向量记录或检索异常时走活跃记忆回退。'),
    ('活跃记忆回退','data','回退最多取 8 条活跃记忆。只有回退条件满足才使用，不会在每次向量无匹配时补满 8 条。'),
    ('偏好预算四百','process','默认用户偏好独立预算约 400 token；用户偏好区块先为固定头尾预留预算，再对正文截断。数值是默认配置，不是实时环境观测。'),
    ('记忆预算八百','process','默认对格式化记忆正文使用约 800 token 预算，随后添加区块包装文本。使用字符权重估算，不是对应模型 tokenizer 的精确计数。'),
    ('摘要预算八百','process','默认摘要正文约 800 token，截断后添加摘要数据区块标记。摘要生成阶段另有输出预算，与注入聊天时的预算不同。'),
    ('合并为模型请求','service','加入固定规则、人格、时间、本轮输入、历史与工具定义后发送；工具循环还会追加结果。局部预算不等于整份请求都有总长控制。'),
    ('关注总量与衔接','note','两个待验证点：固定规则、历史与工具结果未被上述三项局部预算全部覆盖；20 条近期窗口与超过 24 条才触发摘要之间，可能有尚未摘要却已掉出窗口的消息。')],
    [(1,2,'历史支路','flow'),(2,3,'摘要之后','flow'),(1,4,'记忆支路','flow'),(4,5,'满足回退','flow'),(4,7,'相关或为空','data'),(5,7,'活跃记忆','data'),(1,6,'偏好支路','flow'),(2,8,'摘要正文','data'),(3,9,'近期原文','data'),(6,9,'','data'),(7,9,'','data'),(8,9,'','data'),(9,10,'检查重点','dependency')],
    ['近期原文最多 20 条，不能简单当作 10 轮。','记忆默认召回 5 条，特定条件回退最多 8 条。','偏好、记忆、摘要有各自的估算预算。','局部预算不等于整份请求的总预算。','摘要更新与历史窗口的衔接还需测试。'],
    ['历史、记忆、偏好三条支路并排，再汇入模型请求。','400、800、800 是配置默认的局部估算预算；不是整轮请求的总上限。'])

spec = {'diagrams': diagrams}
all_nodes, all_edges = set(), set()
for d in diagrams:
    assert len(d['nodes']) <= 12
    nodes = {n['id'] for n in d['nodes']}
    assert not nodes & all_nodes
    all_nodes |= nodes
    connected, pairs = set(), set()
    for n in d['nodes']:
        assert len(n['label']) <= 12
    for e in d['edges']:
        pair = (e['from'], e['to'])
        assert e['id'] not in all_edges and pair not in pairs and pair[0] != pair[1]
        assert set(pair) <= nodes and len(e['label']) <= 8
        all_edges.add(e['id']); pairs.add(pair); connected.update(pair)
    assert connected == nodes
for c in content:
    assert 3 <= len(c['points']) <= 5 and all(len(p) <= 40 for p in c['points'])
(ROOT / 'diagrams.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

template = (ROOT / 'template.html').read_text(encoding='utf-8')
page = template.replace('/*__ENGINE__*/', (SHARED / 'vendor/dagre.min.js').read_text(encoding='utf-8'))
page = page.replace('__SPEC__', json.dumps(spec, ensure_ascii=False).replace('</', '<\\/'))
page = page.replace('__CONTENT__', json.dumps(content, ensure_ascii=False).replace('</', '<\\/'))
page = page.replace('__LICENSE__', (SHARED / 'vendor/DAGRE-LICENSE.txt').read_text(encoding='utf-8'))
(ROOT / 'index.html').write_text(page, encoding='utf-8')
print(f'Built context page: {len(diagrams)} diagrams, {len(all_nodes)} nodes, {len(all_edges)} edges. Semantic checks passed.')

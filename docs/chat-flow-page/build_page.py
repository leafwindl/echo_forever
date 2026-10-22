"""Build a self-contained offline explainer from semantic diagrams."""
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).parent

def diagram(number, title, subtitle, groups, nodes, edges, notes, points):
    prefix = f'd{number}'
    return {
        'id': f'diagram-{number}', 'title': title, 'type': 'flowchart',
        'layout': {'direction': 'TB', 'rankSpacing': 'normal', 'edgeRouting': 'orthogonal'},
        'groups': [{'id': f'{prefix}g{i}', 'label': label, 'nodeIds': [f'{prefix}n{n}' for n in ids]} for i, (label, ids) in enumerate(groups, 1)],
        'nodes': [{'id': f'{prefix}n{i}', 'label': label, 'kind': kind,
                   'group': next(f'{prefix}g{g}' for g, (_, ids) in enumerate(groups, 1) if i in ids)}
                  for i, (label, kind, detail) in enumerate(nodes, 1)],
        'edges': [{'id': f'{prefix}e{i}', 'from': f'{prefix}n{a}', 'to': f'{prefix}n{b}', 'label': label, 'kind': kind}
                  for i, (a, b, label, kind) in enumerate(edges, 1)],
        'notes': notes,
    }, {'subtitle': subtitle, 'points': points,
        'details': {f'{prefix}n{i}': detail for i, (_, _, detail) in enumerate(nodes, 1)}}

diagrams, content = [], []
def add(*args):
    d, c = diagram(*args)
    diagrams.append(d)
    content.append(c)

add(1, '发出去之前，先确认消息有效', '发送成功，代表服务器已接收；AI 回复还在后面。',
    [('客户端', [1,2,3,4,12]), ('服务端接收', [5,6,7,8,9,10,11])], [
    ('点击发送', 'start', '这里讲的是 APP 的文字与表情聊天。语音通话使用另一条交付链路。'),
    ('本地校验', 'decision', '检查当前能否输入。文字去掉首尾空白后不能为空，客户端上限为 2000 字符；表情检查标识和可用地址。'),
    ('提示修改', 'process', '本地校验不通过时不提交请求；具体提示取决于界面处理。'),
    ('编号并显示', 'process', '生成 client_message_id，先显示“发送中”气泡，再提交消息。'),
    ('身份与请求校验', 'decision', '服务端从登录令牌识别用户；校验消息格式、类型、长度与表情使用权，并执行频率及配额限制。'),
    ('检查消息编号', 'decision', '按用户和客户端消息编号查重。同编号且同内容会复用原接收结果；内容不同则拒绝。'),
    ('返回已有结果', 'data', '这是消息幂等：网络重试不应再创建同一条用户消息。重试仍需先通过身份校验与限流。'),
    ('检查队列容量', 'decision', '计算待处理消息数量；超过容量返回“稍后再发”，避免队列无限增长。'),
    ('保存并加入批次', 'data', '在数据库事务中保存用户消息，并创建或追加后台聊天批次。短时间连续输入可合并处理。'),
    ('确认已接收', 'process', '返回 HTTP 202 与已保存消息。APP 合并本地气泡；这不表示 AI 已完成回答。'),
    ('拒绝并提示', 'process', '无效请求、限流、队列满或编号内容冲突会返回错误；前端保留失败状态。'),
    ('发送失败可重试', 'process', '请求失败时标记发送失败。用户重试复用原编号；如果服务端早已保存，可取回原结果。')],
    [(1,2,'','flow'),(2,3,'不通过','flow'),(2,4,'通过','flow'),(4,5,'提交请求','data'),
     (5,6,'通过','flow'),(5,11,'拒绝','flow'),(6,7,'相同内容','flow'),(6,11,'内容冲突','flow'),
     (6,8,'新编号','flow'),(8,9,'有容量','flow'),(8,11,'已满','flow'),(9,10,'保存成功','flow'),
     (7,10,'复用结果','flow'),(11,12,'','flow'),(4,12,'网络失败','optional'),(12,5,'原编号重试','optional')],
    ['主流程从上到下，拒绝和重试放在侧支；重试使用外围回边。', 'diagram-1 的“保存并加入批次”衔接 diagram-2；接收确认不等待模型。'],
    ['先做本地校验，再做服务端校验。','消息编号让同一次发送可以安全重试。','限流控制请求速度，队列上限控制积压。','202 只表示已接收，不表示已经回复。'])

add(2, '后台怎样理解并处理这轮消息', '先排队、再组装上下文；部分明确提醒可走快捷分支。',
    [('后台调度', [1,2,3,4]), ('回复准备', [5,6,7,8,9,10,11])], [
    ('等待批次就绪', 'start', '接续图 1。按安静窗口收集连续消息，并以最长窗口、条数和字符数限制批次。'),
    ('领取后台任务', 'service', 'Worker 领取到期任务，并用租约记录占用；租约过期任务可在尝试次数限制内重新排队。'),
    ('用户执行锁', 'decision', '同一用户的文字处理与同步通话共用执行门禁，避免同时运行 Agent 干扰上下文。'),
    ('稍后再处理', 'process', '无法获得门禁时把任务重新安排到稍后执行，不忙等占用模型。'),
    ('显示正在输入', 'process', '通过事件通道通知 APP 正在处理，然后读取本批次合并后的内容。'),
    ('明确相对提醒', 'decision', '配置提醒存储时，先尝试识别明确的相对时间提醒。匹配且创建成功可直接生成确认。'),
    ('尝试创建提醒', 'service', '这一快捷分支直接调用提醒业务，不经过模型工具选择；创建失败则继续常规处理。'),
    ('组装对话上下文', 'data', '组合当前输入、近期历史、摘要、相关长期记忆、人物与关系设定、服务端时间信息；提示层设有内容预算。'),
    ('运行模型与工具', 'service', '进入图 3 的受限 Agent 回路；模型可以直接回答，也可以先申请工具调用。'),
    ('进入回复交付', 'process', '将准备好的回复交给图 4，校验后保存并通知客户端。'),
    ('任务失败通知', 'process', '未被内部兜底处理的异常使任务失败，并发布失败事件。最终释放执行门禁、结束输入状态。')],
    [(1,2,'批次到期','flow'),(2,3,'','flow'),(3,4,'被占用','flow'),(4,1,'重新排队','optional'),
     (3,5,'已获得','flow'),(5,6,'','flow'),(6,7,'匹配','flow'),(6,8,'未匹配','flow'),
     (7,10,'创建成功','flow'),(7,8,'创建失败','flow'),(8,9,'','data'),(9,10,'已准备','flow'),
     (9,11,'未恢复异常','optional')],
    ['提醒快捷分支与常规模型分支并排，随后汇合到交付节点。', 'diagram-3 展开“运行模型与工具”；diagram-4 展开回复交付。', '失败节点概括整个任务处理期间未恢复的异常，避免给每个节点增加错误连线。'],
    ['连续短消息可合并，减少重复模型请求。','同一用户串行处理，避免上下文互相干扰。','上下文包含历史、记忆、设定与时间信息。','明确相对提醒有直接处理的快捷分支。'])

add(3, '模型提出调用，系统决定能否执行', '工具调用是一项待校验的请求，实际结果才是执行依据。',
    [('模型回路', [1,2,3,4,11,12]), ('工具执行门禁', [5,6,7,8,9,10])], [
    ('接收对话上下文', 'start', '接续图 2。按当前聊天模式向模型提供可用工具描述与参数结构。'),
    ('模型生成下一步', 'service', '模型根据当前上下文生成回复或工具申请。它提出调用请求，实际执行由服务端负责。'),
    ('是否申请工具', 'decision', '无工具申请时进入最终交付检查；有申请时逐个进入调用限制与执行校验。'),
    ('检查运行预算', 'decision', 'Agent 限制模型步骤、工具调用总数和总运行时间。耗尽时转入收尾或兜底，避免无限循环。'),
    ('检查工具与模式', 'decision', '确认工具已注册、当前步骤允许调用，且允许在本轮聊天模式使用。'),
    ('去重与次数检查', 'decision', '同一轮内，同工具同原始参数的重复调用被拒绝；同时检查该工具调用与成功次数限制。此去重不等于跨轮幂等。'),
    ('校验工具参数', 'decision', '执行前用工具参数模型验证类型、必填项和约束；业务处理器继续执行自身规则。'),
    ('限时执行工具', 'service', '在单工具超时与整轮剩余时间约束下执行；异常被转成失败结果，不直接当作成功。'),
    ('记录真实结果', 'data', '记录成功、无结果、失败或超时。将可供模型使用的结果按调用编号回填；同轮多个调用依次处理。'),
    ('生成拒绝结果', 'data', '名称、模式、次数或参数不合格时，不执行处理器，将拒绝原因作为工具结果返回。'),
    ('收尾或失败兜底', 'process', '在预算限制下尝试生成可交付回复；仍无法完成时返回兜底内容。部分模型超时与格式错误有有限重试。'),
    ('形成最终回复', 'process', '转到图 4。还会检查可交付内容；表情发送声明需要成功结果支持，不能只凭模型口头声称。')],
    [(1,2,'','data'),(2,3,'','flow'),(3,12,'直接回答','flow'),(3,4,'申请调用','flow'),
     (4,5,'仍有预算','flow'),(4,11,'已耗尽','flow'),(5,6,'允许','flow'),(5,10,'拒绝','flow'),
     (6,7,'允许','flow'),(6,10,'拒绝','flow'),(7,8,'通过','flow'),(7,10,'不通过','flow'),
     (8,9,'执行结果','data'),(10,9,'拒绝原因','data'),(9,2,'回填再判断','data'),(11,12,'','flow')],
    ['校验节点沿主流程排列，拒绝结果放在侧边；回填模型使用外围回边。', '相同参数去重仅覆盖本轮已记录结果，不代表重启后动作绝不重复。'],
    ['先检查工具可用性，再验证参数并执行。','同轮相同原始参数调用会被拒绝。','工具逐个处理，次数和运行时间都有上限。','成功、无结果、失败、超时都会回填模型。','跨轮动作防重仍需验证业务幂等。'])

add(4, '回复怎样显示，断线后怎样补齐', '先保存，再通知；断线重连依靠历史记录恢复消息。',
    [('服务端交付', [1,2,3,4]), ('客户端展示与恢复', [5,6,7,8,9,10])], [
    ('检查交付内容', 'start', '接续图 2 或图 3。检查回复分段与内部元信息，并应用部分表达兜底；这不等于通用事实核验。'),
    ('保存整组回复', 'data', '按自然段保存文字及独立表情消息，记录回复组、组内顺序与关联消息。文字分段有安全上限。'),
    ('执行保存后处理', 'process', '回复保存后更新或调度摘要、记忆提取与关系信号。Worker 会等待本步骤返回再发布交付事件；异常会记录并继续。'),
    ('发布回复事件', 'service', 'SSE 是服务端向 APP 推送事件的长连接。文字聊天推送保存后的回复组，不是逐字直出模型内容。'),
    ('连接是否正常', 'decision', '客户端接收输入状态与回复事件；连接结束或出错时安排重连。'),
    ('排队展示回复', 'process', '按回复组顺序展示，首条及时出现；后续气泡按服务端节奏信息展示，避免多组回复混排。'),
    ('按编号合并消息', 'process', '结合服务端消息标识与客户端编号合并本地和远端记录，减少重连或确认造成的重复气泡。'),
    ('回复显示完成', 'process', '后台处理与展示队列都结束后停止输入提示。已接收消息与本轮回复失败属于不同状态。'),
    ('延迟后自动重连', 'process', '客户端使用分级重连间隔，并携带已知最新服务端消息编号；页面销毁后停止连接。'),
    ('补发遗漏历史', 'data', '服务端从指定消息编号之后分页同步历史，再继续推送新事件。该机制主要恢复已保存消息，不保证重放全部瞬时状态。')],
    [(1,2,'通过检查','flow'),(2,3,'','flow'),(3,4,'','flow'),(4,5,'事件通道','data'),
     (5,6,'正常','flow'),(6,7,'','flow'),(7,8,'','flow'),(5,9,'断开','flow'),
     (9,10,'携带编号','data'),(10,7,'合并历史','data'),(10,5,'恢复订阅','flow')],
    ['正常展示与重连补发并排，统一汇入消息合并节点。', '图中“回复显示完成”只表示本轮展示完成，事件通道继续保持。'],
    ['先保存回复，再推送事件，便于断线补齐。','文字聊天按回复组交付，不是逐字流出。','发送失败可重试，回复失败不能混为一谈。','保存后处理位于推送前，也可能增加等待。','本页基于代码阅读，未作运行压测或完整审计。'])

spec = {'diagrams': diagrams}
ids, edge_ids = set(), set()
for d in diagrams:
    assert len(d['nodes']) <= 12
    node_ids = {n['id'] for n in d['nodes']}
    assert not ids & node_ids
    ids |= node_ids
    pairs, connected = set(), set()
    for n in d['nodes']:
        assert len(n['label']) <= 12
    for e in d['edges']:
        assert e['id'] not in edge_ids
        edge_ids.add(e['id'])
        assert e['from'] in node_ids and e['to'] in node_ids
        assert e['from'] != e['to'] and (e['from'], e['to']) not in pairs
        assert len(e['label']) <= 8
        pairs.add((e['from'], e['to']))
        connected.update((e['from'], e['to']))
    assert connected == node_ids
(ROOT / 'diagrams.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

# Bundle the local layout engine into the HTML; opening the result needs no network.
vendor = ROOT / 'vendor'
vendor.mkdir(exist_ok=True)
engine_path = vendor / 'dagre.min.js'
if not engine_path.exists():
    with urlopen('https://unpkg.com/@dagrejs/dagre@1.1.5/dist/dagre.min.js', timeout=45) as r:
        engine_path.write_bytes(r.read())
license_path = vendor / 'DAGRE-LICENSE.txt'
if not license_path.exists():
    with urlopen('https://unpkg.com/@dagrejs/dagre@1.1.5/LICENSE', timeout=45) as r:
        license_path.write_bytes(r.read())

template = (ROOT / 'template.html').read_text(encoding='utf-8')
page = template.replace('/*__ENGINE__*/', engine_path.read_text(encoding='utf-8'))
page = page.replace('__SPEC__', json.dumps(spec, ensure_ascii=False).replace('</', '<\\/'))
page = page.replace('__CONTENT__', json.dumps(content, ensure_ascii=False).replace('</', '<\\/'))
page = page.replace('__LICENSE__', license_path.read_text(encoding='utf-8'))
(ROOT / 'index.html').write_text(page, encoding='utf-8')
print(f'Built {ROOT / "index.html"}; {len(diagrams)} diagrams, {len(ids)} nodes, {len(edge_ids)} edges; all semantic checks passed.')

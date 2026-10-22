from pathlib import Path

ROOT=Path(__file__).parent
SOURCE=ROOT.parent/'chat-context-page'
s=(SOURCE/'template.html').read_text(encoding='utf-8')
changes={
    '上下文的组成 · Echo Prompt 讲解':'上下文来源与规则地图 · Echo 源码导览',
    'Echo 上下文的来源、组装顺序、Prompt 约束与局部预算。完全离线的交互式讲解页面。':'Echo 项目上下文来源、生成流程、规则定义、运行校验和测试定位。可离线使用的源码地图。',
    'Echo / 上下文笔记':'Echo / 来源与规则地图',
    'PROJECT WALKTHROUGH / 02':'PROJECT WALKTHROUGH / 03',
    '模型这一轮，<br>究竟<em>看到了什么。</em>':'每一份上下文，<br>都能<em>找到来处。</em>',
    '上下文不是完整聊天记录的复制品。它由规则、相关背景、近期原文和当前消息共同组成；沿着四张图，看懂信息怎样进入模型，又怎样受到约束。':'继续往项目里走一层：哪些内容是开发者写的，哪些由用户填写，哪些由规则计算或模型生成？沿着五张图，追到定义文件、保存位置、运行校验与测试。',
    '每次请求，重新准备一份材料。':'定义 → 生成或读取 → 校验 → 使用',
    '模型不能自动翻阅数据库。后端先选取本轮材料，再组装消息列表；工具能力单独提供，真实执行结果则在调用后加入。':'点选任意节点，右侧就会显示项目文件、定位行和函数。下方规则对照表把“写了什么”和“实际怎么检查”放在一起；所有测试均标注为已定位、未运行。',
    '<span>来源可追溯</span><span>分层组装</span><span>约束分工</span><span>长度预算</span>':'<span>源码定位</span><span>生成生命周期</span><span>运行校验</span><span>测试证据</span>',
    '阅读路径　01 → 02 → 03 → 04':'阅读路径　配置 → 用户状态 → 生成材料 → 请求组装 → 规则校验',
    '导出图表 JSON':'导出图表 JSON',
    'Echo · 上下文与 Prompt 讲解':'Echo · 上下文来源与规则地图',
    'echo-context-diagrams.json':'echo-source-map-diagrams.json',
    '回到信息来源 ↺':'回到产品与人格 ↺',
    '01 / 携带 ≠ 必须提起':'01 / 找到定义，再看执行',
    '材料里有称呼、记忆或旧话题，不表示回复必须提它们。普通问候不应因为带了工作记忆，就突然追问工作。':'改了一句 Prompt，不代表增加了运行门禁。先定位定义，再检查谁消费这条规则、如何处理失败。',
    '02 / 低权限标记 ≠ 独立隔离':'02 / 生成内容，保留出处',
    '当前背景仍通过 system 消息承载。“只作数据”的提示有帮助，但不能当成完整的权限隔离或防注入证明。':'记忆和摘要是模型产物。需要能回看用户原话、保存边界与生成规则；背景标记不能替代事实核验。',
    '03 / 局部预算 ≠ 总请求上限':'03 / 测试存在 ≠ 已验证通过',
    '偏好、记忆和摘要各自截断后，还会加入固定规则、历史、工具定义与结果；整份上下文仍需关注总量。':'有些测试只断言文案存在，有些验证假模型与执行器。既要查看断言内容，也要实际运行，不能据文件名认定覆盖完整。',
    '说明范围为常规文字聊天的上下文与 Prompt 组装。明确相对提醒创建成功时可以绕过模型；语音通话、主动聊天和每日来信有不同分支。数字为配置默认值，未读取部署环境的实际覆盖值。未进行后端运行验证或完整安全审计；代码变化后说明也需更新。':'本页基于当前工作区的常规文字聊天代码。文件和定位符在构建时检查存在，行号是构建时快照；代码修改后行号可能变化。未读取 .env 内容、用户数据库或部署密钥；不展示私人数据。未运行后端测试、真实模型评测或安全审计。规则测试均为“已定位、未运行”，不是通过报告。',
}
for old,new in changes.items():
    assert old in s,old
    s=s.replace(old,new)
start=s.index('<nav class="tabs"')
end=s.index('</nav>',start)+len('</nav>')
tabs=[('产品与人格','人工定义与版本加载'),('用户偏好与关系','填写、计算与持久化'),('记忆与摘要','模型生成的生命周期'),('请求如何组装','读取、渲染与回填'),('规则如何落地','定义、校验与测试')]
nav='<nav class="tabs" role="tablist" aria-label="源码导览章节">'
for i,(title,desc) in enumerate(tabs):
    nav+=f'<button class="tab" id="tab-{i}" role="tab" aria-controls="panel" aria-selected="{str(i==0).lower()}" tabindex="{0 if i==0 else -1}"><span class="num">0{i+1}</span><span><strong>{title}</strong><small>{desc}</small></span></button>'
s=s[:start]+nav+'</nav>'+s[end:]
s=s.replace('repeat(4,1fr)','repeat(5,1fr)')
s=s.replace('max-width:1440px','max-width:1540px')
s=s.replace('1fr) 310px','1fr) 370px')
s=s.replace('<div class="group-pills" id="groups">','<section class="evidence" aria-label="当前节点的源码与测试"><p class="aside-label">SOURCE / 定义、执行与测试位置</p><div id="node-evidence"></div></section><div class="group-pills" id="groups">')
s=s.replace('EXPLORE / 点击节点查看解释','EXPLORE / 点击节点追溯来源')
s=s.replace('<section class="audit">','''<section class="rule-section" aria-labelledby="rules-title"><div class="section-heading"><div><p class="eyebrow">RULE CROSSWALK / 定义与检查对照</p><h2 id="rules-title">一条规则，沿着四个位置查。</h2><p>先读定义，再看执行与断言。这里记录的是测试位置，不是测试通过状态。</p></div><div><label for="rule-search">搜索规则、文件或函数</label><input type="search" id="rule-search" placeholder="例如：摘要、追问、execute_tool" autocomplete="off"><span id="rule-count" role="status"></span></div></div><div class="table-scroll"><table><thead><tr><th scope="col">规则</th><th scope="col">在哪里定义</th><th scope="col">在哪里执行或检查</th><th scope="col">对应测试 · 未运行</th><th scope="col">实际边界</th></tr></thead><tbody id="rule-rows"></tbody></table></div></section><section class="audit">''')
s=s.replace('<details><summary>依据与范围：','<details><summary>依据与范围：')
s=s.replace('<details><summary>布局与离线说明</summary>','<details><summary>完整源码定位清单 · 可搜索</summary><label for="file-search">按项目路径或定位符筛选</label><input id="file-search" type="search" placeholder="例如：default_persona.py、user_personas、test_" autocomplete="off"><p id="file-count" role="status"></p><div id="all-references" class="reference-index"></div></details><details><summary>布局与离线说明</summary>')
s=s.replace('</style>','''
.tabs{gap:8px}.tab{padding:12px 10px;gap:8px}.tab strong{font-size:13px}.tab small{font-size:10px}.evidence{margin:0 0 22px}.source-item{border:1px solid #d9e1d1;border-radius:7px;background:#fafbf5;padding:10px 12px;margin:8px 0}.source-item strong{display:block;font-size:10px;letter-spacing:.2px;color:#56704f}.source-item code{display:block;font:11px/1.65 ui-monospace,Consolas,monospace;overflow-wrap:anywhere;user-select:all;color:#384e43;margin-top:4px}.source-item .symbol{color:#657263;font-size:10px}.source-item.test{border-style:dashed;background:transparent}.source-item.test strong{color:#916b3a}.rule-section{margin-top:38px;padding-top:25px;border-top:1px solid var(--line)}.section-heading{display:flex;justify-content:space-between;align-items:center;gap:30px}.section-heading h2{font-size:25px;margin:8px 0}.section-heading p{color:var(--muted);font-size:13px;max-width:660px}.section-heading label,details>label{display:block;font-size:12px;color:#53674f}input[type=search]{display:block;margin:7px 0;background:var(--white);border:1px solid #bccab2;border-radius:6px;padding:10px 12px;min-width:280px;max-width:100%;font:12px system-ui,sans-serif;color:var(--ink)}input:focus-visible{outline:3px solid #c4d992;outline-offset:2px}#rule-count,#file-count{font-size:11px;color:var(--muted)}.table-scroll{overflow:auto;margin-top:16px;border:1px solid var(--line);border-radius:9px}table{width:100%;min-width:1020px;border-collapse:collapse;text-align:left;table-layout:fixed;font-size:12px}th{background:#e9eedf;padding:13px 12px;font-size:11px;color:#52664b;vertical-align:top}td{padding:13px 12px;vertical-align:top;border-top:1px solid var(--line);background:#fffef9;overflow-wrap:anywhere}th:first-child{width:12%}th:nth-child(2){width:21%}th:nth-child(3){width:24%}th:nth-child(4){width:24%}th:last-child{width:19%}td .source-item{margin:0 0 8px;padding:7px 8px}td .source-item:last-child{margin-bottom:0}.reference-index{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px;max-height:540px;overflow:auto}.reference-index .source-item{margin:0}.detail{min-height:0}.graph-scroll{max-height:830px}.group-pills{margin-top:14px}.card-head h2{font-size:20px}.legend{font-size:10px}
@media(max-width:1100px){.tabs{grid-template-columns:repeat(3,1fr)}.workspace{grid-template-columns:minmax(0,1fr) 310px}.section-heading{display:block}}@media(max-width:740px){.workspace{grid-template-columns:1fr}.tabs{grid-template-columns:1fr 1fr}.reference-index{grid-template-columns:1fr}.section-heading h2{font-size:22px}.graph-scroll{max-height:680px}.section-heading{display:block}.toolbar-label{font-size:10px}.source-item code{font-size:11px}}
</style>''')
s=s.replace('const copy=__CONTENT__;','const copy=__CONTENT__;\nconst references=__REFERENCES__;\nconst rules=__RULES__;\nconst sectionCount=specification.diagrams.length;')
s=s.replace("$('detail-copy').textContent=copy[active].details[id]}","$('detail-copy').textContent=copy[active].details[id];renderEvidence(id)}")
s=s.replace("index===3?", "index===sectionCount-1?")
s=s.replace('(i+1)%4','(i+1)%sectionCount').replace('(i+3)%4','(i+sectionCount-1)%sectionCount').replace('next=3;','next=sectionCount-1;').replace('(active+1)%4','(active+1)%sectionCount')
extra='''
function refCard(id){const ref=references[id],box=document.createElement('div');box.setAttribute('class','source-item'+(ref.isTest?' test':''));const role=document.createElement('strong');role.textContent=ref.role;const file=document.createElement('code');file.textContent=ref.file+':'+ref.line;const symbol=document.createElement('code');symbol.setAttribute('class','symbol');symbol.textContent=ref.symbol;box.append(role,file,symbol);return box}
function renderEvidence(id){$('node-evidence').replaceChildren(...copy[active].evidence[id].map(refCard))}
function renderRules(query=''){const clean=query.trim().toLowerCase();const matches=rules.filter(rule=>{const refs=[...rule.definition,...rule.runtime,...rule.tests].map(id=>references[id]);return (rule.name+' '+rule.limit+' '+refs.map(ref=>ref.file+' '+ref.symbol).join(' ')).toLowerCase().includes(clean)});const rows=matches.map(rule=>{const row=document.createElement('tr'),name=document.createElement('td');name.textContent=rule.name;row.append(name);for(const group of ['definition','runtime','tests']){const cell=document.createElement('td');cell.append(...rule[group].map(refCard));row.append(cell)}const limit=document.createElement('td');limit.textContent=rule.limit;row.append(limit);return row});$('rule-rows').replaceChildren(...rows);$('rule-count').textContent=matches.length+' / '+rules.length+' 条规则 · 测试未运行';return matches.length}
function renderReferences(query=''){const clean=query.trim().toLowerCase(),items=Object.values(references).filter(ref=>(ref.file+' '+ref.symbol+' '+ref.role).toLowerCase().includes(clean)).sort((a,b)=>a.file.localeCompare(b.file)||a.line-b.line);$('all-references').replaceChildren(...items.map(ref=>refCard(ref.id)));$('file-count').textContent=items.length+' 个源码定位 · 行号为构建时快照';return items.length}
$('rule-search').addEventListener('input',event=>renderRules(event.target.value));
$('file-search').addEventListener('input',event=>renderReferences(event.target.value));
renderRules();renderReferences();
'''
s=s.replace('try{select(0)}',extra+'\ntry{select(0)}')
start=s.index('<div class="sources">')
end=s.index('</div>',start)+len('</div>')
s=s[:start]+'<p>完整文件、函数和测试位置可在上方节点说明、规则对照表及下方定位清单中查询。行号随工作区变化，请优先结合函数名定位。</p>'+s[end:]
(ROOT/'template.html').write_text(s,encoding='utf-8')

test=(SOURCE/'verify_page.cjs').read_text(encoding='utf-8')
test=test.replace('length:4','length:5').replace('i<4','i<5').replace("tabs[3].events.keydown", "tabs[4].events.keydown")
test=test.replace("const spec=JSON.parse", "assert.equal(ids.get('rule-rows').children.length,10);\nassert(vm.runInContext(\"renderRules('不存在的规则-123')\",context)===0);\nassert(vm.runInContext(\"renderRules('摘要')\",context)>0);\nassert(vm.runInContext(\"renderReferences('default_persona.py')\",context)>0);\nvm.runInContext(\"renderRules();renderReferences();\",context);\nconst spec=JSON.parse")
test=test.replace("assert(ids.get('detail-copy').textContent.length>5);", "assert(ids.get('detail-copy').textContent.length>5);assert(ids.get('node-evidence').children.length>0);")
(ROOT/'verify_page.cjs').write_text(test,encoding='utf-8')
print('Prepared source-map template and offline runtime check.')

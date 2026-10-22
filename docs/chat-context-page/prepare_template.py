"""Reuse the existing local explainer shell for the context walkthrough."""
from pathlib import Path

root = Path(__file__).parent
shared = root.parent / 'chat-flow-page'
s = (shared / 'template.html').read_text(encoding='utf-8')
replacements = {
    '一条消息的旅程 · Echo 聊天流程': '上下文的组成 · Echo Prompt 讲解',
    'Echo 项目聊天流程：消息校验、后台任务、工具调用与断线恢复。完全离线的交互式讲解页面。': 'Echo 上下文的来源、组装顺序、Prompt 约束与局部预算。完全离线的交互式讲解页面。',
    'Echo / 流程笔记': 'Echo / 上下文笔记',
    'PROJECT WALKTHROUGH / 01': 'PROJECT WALKTHROUGH / 02',
    '一条消息，<br>怎样变成<em>一次回复。</em>': '模型这一轮，<br>究竟<em>看到了什么。</em>',
    '从点击发送，到校验、排队、模型思考与工具执行，再回到聊天气泡。沿着四张图，看懂项目当前的文字聊天流程。': '上下文不是完整聊天记录的复制品。它由规则、相关背景、近期原文和当前消息共同组成；沿着四张图，看懂信息怎样进入模型，又怎样受到约束。',
    '先接收，再处理，最后交付。': '每次请求，重新准备一份材料。',
    'APP 发送消息后，服务端先保存并返回确认。后台再生成回复，通过事件长连接送回页面。你可以继续发送，处理端按规则合并与排队。': '模型不能自动翻阅数据库。后端先选取本轮材料，再组装消息列表；工具能力单独提供，真实执行结果则在调用后加入。',
    '<span>双层校验</span><span>消息防重</span><span>受限工具回路</span><span>断线补齐</span>': '<span>来源可追溯</span><span>分层组装</span><span>约束分工</span><span>长度预算</span>',
    '发送与校验': '信息来源', '消息如何安全进入系统': '材料分别从哪里取得',
    '排队与理解': '组装顺序', '后台如何准备回复': '本次请求怎样排列',
    '模型与工具': '约束分工', '调用怎样受到约束': '提示词要求与程序限制',
    '回复与恢复': '选择与预算', '保存、展示与断线补齐': '怎样避免过长与带错',
    '“正确、高效”怎么判断？': '先记住三个区别',
    '已有保护机制，是检查的起点。': '理解上下文，最容易混淆的是这些。',
    '01 / 发送不重复': '01 / 携带 ≠ 必须提起',
    '重点验证：服务端已保存但确认包丢失后，用原编号重试，应只有一条用户消息。': '材料里有称呼、记忆或旧话题，不表示回复必须提它们。普通问候不应因为带了工作记忆，就突然追问工作。',
    '02 / 动作有真实依据': '02 / 低权限标记 ≠ 独立隔离',
    '重点验证：非法参数、重复调用、超时均不会被误报成功；有副作用的动作还要验证跨轮幂等。': '当前背景仍通过 system 消息承载。“只作数据”的提示有帮助，但不能当成完整的权限隔离或防注入证明。',
    '03 / 等待可分段解释': '03 / 局部预算 ≠ 总请求上限',
    '分别观察排队、上下文构建、模型、工具与保存后处理耗时，再决定优化哪里。': '偏好、记忆和摘要各自截断后，还会加入固定规则、历史、工具定义与结果；整份上下文仍需关注总量。',
    '说明范围为 APP 文字与表情聊天。语音通话、主动聊天与每日来信没有在本页展开。未启动后端、未执行聊天测试或性能压测；本页不是完整正确性证明。代码改动后，文案与规格需要同步更新。': '说明范围为常规文字聊天的上下文与 Prompt 组装。明确相对提醒创建成功时可以绕过模型；语音通话、主动聊天和每日来信有不同分支。数字为配置默认值，未读取部署环境的实际覆盖值。未进行后端运行验证或完整安全审计；代码变化后说明也需更新。',
    'Echo · 项目聊天流程讲解': 'Echo · 上下文与 Prompt 讲解',
    'echo-chat-diagrams.json': 'echo-context-diagrams.json',
    '回到发送流程 ↺': '回到信息来源 ↺',
    "d.notes.find(n=>n.includes('diagram-'))||'工具回路结束后，继续阅读下一部分的保存与交付。'": 'd.notes[0]',
}
for old, new in replacements.items():
    assert old in s, old
    s = s.replace(old, new)
start = s.index('<div class="sources">')
end = s.index('</div>', start) + len('</div>')
files = [
    'chat/infrastructure/context_builder.py', 'shared/prompting/renderer.py',
    'chat/infrastructure/postgres_repositories.py', 'chat/infrastructure/conversation_summary.py',
    'chat/application/generate_reply.py', 'agent/application/orchestrate_chat.py',
    'agent/application/execute_tool.py', 'agent/domain/tools.py', 'memory/application/memory_extraction.py',
]
s = s[:start] + '<div class="sources">' + ''.join(f'<code>Echo-backend/{name if name.startswith("shared/") else "features/" + name}</code>' for name in files) + '<code>Echo-backend/shared/config/settings.py</code></div>' + s[end:]
(root / 'template.html').write_text(s, encoding='utf-8')
(root / 'verify_page.cjs').write_text((shared / 'verify_page.cjs').read_text(encoding='utf-8'), encoding='utf-8')
print('Context template prepared.')

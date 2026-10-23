"""Measure rendered prompt text without loading settings, secrets, DBs or providers.

Uses the application's character-weight estimate, not a model tokenizer.
"""
import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

HERE = Path(__file__).parent
REPO = HERE.parents[1]
BACKEND = REPO / 'Echo-backend'
def tree(relative):
    return ast.parse((BACKEND / relative).read_text(encoding='utf-8'))

renderer = tree('shared/prompting/renderer.py')
scope = {'Path': Path, '__file__': str(BACKEND / 'shared/prompting/renderer.py'), 'Sequence': Sequence, 'AssistantPersona': object, 'UserPreferences': object, 'RelationshipContext': object}
body = [node for node in renderer.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
exec(compile(ast.Module(body=body, type_ignores=[]), '<isolated-renderer>', 'exec'), scope)
persona_tree = tree('features/assistant_persona/infrastructure/default_persona.py')
persona_node = next(node for node in persona_tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ECHO_PERSONA_V2' for t in node.targets))
persona = eval(compile(ast.Expression(persona_node.value), '<persona-literal>', 'eval'), {'AssistantPersona': SimpleNamespace})
settings = next(node for node in tree('shared/config/settings.py').body if isinstance(node, ast.ClassDef) and node.name == 'Settings')
identity = ast.literal_eval(next(node.value for node in settings.body if isinstance(node, ast.AnnAssign) and node.target.id == 'system_prompt'))
prefs = SimpleNamespace(enabled=True, preferred_name=None, reply_style='natural', reply_length='balanced', support_mode='balanced', proactivity='balanced', relationship_pace='natural', affection_style='contextual', avoid_topics=(), about_user=None)
messages = scope['render_prompt_layers'](product_identity=identity, persona=prefs, long_term_memories=[], conversation_summary='', prompt_version='echo-v1.1.0', persona_maximum_tokens=400, memory_maximum_tokens=800, summary_maximum_tokens=800, assistant_persona=persona, relationship=None, conversation_mode='chat')
messages.append({'role':'system','content':scope['render_turn_focus_guidance'](False, False)})
context_tree = tree('features/chat/infrastructure/context_builder.py')
temporal = next(node for node in ast.walk(context_tree) if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='temporal_guidance' for t in node.targets))
time_rule = eval(compile(ast.Expression(temporal.value), '<temporal-prose>', 'eval'), {'is_call':False})
messages.append({'role':'system','content':time_rule})
agent_class = next(node for node in tree('features/agent/application/orchestrate_chat.py').body if isinstance(node,ast.ClassDef) and node.name=='OrchestrateChatWithAgent')
agent_method = next(node for node in agent_class.body if isinstance(node,ast.FunctionDef) and node.name=='_build_initial_messages')
agent_method.decorator_list=[]
agent_scope={}
exec(compile(ast.Module(body=[agent_method],type_ignores=[]),'<isolated-agent-rules>','exec'),agent_scope)
messages=agent_scope['_build_initial_messages'](messages=messages,conversation_mode='chat',sticker_intent='',allow_proactive_stickers=True)
estimate=scope['estimate_prompt_tokens']
rows=[{'layer':m['content'].splitlines()[0][:80], 'characters':len(m['content']), 'estimated_tokens':estimate(m['content'])} for m in messages]
result={'method':'application character-weight estimate; not tokenizer or billed tokens', 'scenario':'default chat, enabled default preferences, new relationship; excludes history, memories, summary contents, time JSON, user input, tool schemas and tool results; no retries', 'layers':rows, 'totals':{'characters':sum(r['characters'] for r in rows),'estimated_tokens':sum(r['estimated_tokens'] for r in rows)}, 'runtime_policy_counts':{key:len(scope[key]) for key in ['BASELINE_SAFETY_POLICY','NATURAL_DIALOGUE_POLICY','RESPONSE_CALIBRATION_POLICY']}}
style_tree=tree('features/chat/domain/dialogue_style.py')
style_scope={'re':re}
exec(compile(ast.Module(body=[n for n in style_tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))],type_ignores=[]),'<isolated-style-rules>','exec'),style_scope)
user='帮我排查一下登录失败的问题。'
history=[{'role':'assistant','content':'网络还好吗？'},{'role':'assistant','content':'什么时候开始的？'}]
candidate='能提供一下具体错误提示吗？'
pause=style_scope['should_pause_followup_questions'](history,user)
violations=style_scope['find_dialogue_style_violations'](candidate,user,pause_followup_questions=pause)
result['isolated_reproduction']={'history':history,'user':user,'candidate':candidate,'pause_followup_questions':pause,'violations':violations,'actual_fallback':style_scope['apply_dialogue_fallback'](candidate,user,violations),'scope':'isolated domain-function execution; not an end-to-end chat test'}
(HERE/'current-prompt-metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))

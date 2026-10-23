"""Build a private offline walkthrough from a read-only, local chat snapshot.

No runtime settings, database, model provider or network is loaded by this build.
The personalized output stays under the repository's ignored data/ directory.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BACKEND = ROOT / "Echo-backend"
PRIVATE = ROOT / "data/chat-turn-walkthrough"


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def isolated_module(relative, scope):
    tree = ast.parse(read("Echo-backend/" + relative))
    body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    exec(compile(ast.Module(body=body, type_ignores=[]), relative, "exec"), scope)
    return scope


def source_prompts():
    """Run only pure renderer code, excluding all application imports."""
    scope = isolated_module("shared/prompting/renderer.py", {
        "Path": Path, "__file__": str(BACKEND / "shared/prompting/renderer.py"),
        "Sequence": Sequence, "AssistantPersona": object,
        "UserPreferences": object, "RelationshipContext": object,
    })
    tree = ast.parse(read("Echo-backend/features/assistant_persona/infrastructure/default_persona.py"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "ECHO_PERSONA_V3" for t in n.targets))
    persona = eval(compile(ast.Expression(node.value), "persona-literal", "eval"),
                   {"AssistantPersona": SimpleNamespace})
    settings = next(n for n in ast.parse(read("Echo-backend/shared/config/settings.py")).body
                    if isinstance(n, ast.ClassDef) and n.name == "Settings")
    identity = ast.literal_eval(next(n.value for n in settings.body if isinstance(n, ast.AnnAssign)
                                    and n.target.id == "system_prompt"))
    messages = scope["render_prompt_layers"](
        product_identity=identity, persona=None, long_term_memories=[], conversation_summary="",
        prompt_version="echo-v1.1.0", persona_maximum_tokens=400, memory_maximum_tokens=800,
        summary_maximum_tokens=800, assistant_persona=persona, relationship=None,
        conversation_mode="chat",
    )
    agent_tree = ast.parse(read("Echo-backend/features/agent/application/orchestrate_chat.py"))
    cls = next(n for n in agent_tree.body if isinstance(n, ast.ClassDef)
               and n.name == "OrchestrateChatWithAgent")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_build_initial_messages")
    method.decorator_list = []
    agent_scope = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "isolated-agent-prefix", "exec"), agent_scope)
    # This is the current optional-sticker branch, not a historical policy snapshot.
    result = agent_scope["_build_initial_messages"](
        messages=messages, conversation_mode="chat", sticker_intent="",
    )
    return result, scope["estimate_prompt_tokens"]


def build(snapshot, output):
    case = json.loads(snapshot.read_text(encoding="utf-8"))
    assert len(case["messages"]) == 12, "Expected the selected twelve-row teaching case"
    assert [m["id"] for m in case["messages"]] == list(range(1, 13))
    assert case["turn"]["message_count"] == 1
    assert case["run"]["step_count"] == 1 and case["tools"] == []
    current = case["messages"][9]
    assert current["role"] == "user"
    replies = case["messages"][10:]
    assert all(m["in_reply_to_message_id"] == current["id"] for m in replies)
    refs = {}

    def ref(key, path, needle, title):
        text = read(path)
        lines = text.splitlines()
        line = next(i for i, value in enumerate(lines) if needle in value)
        refs[key] = dict(id=key, file=path, line=line + 1, title=title, symbol=needle,
                         excerpt="\n".join(lines[line:line + 11]),
                         sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())

    B = "Echo-backend/"
    ref("client", "app/lib/features/chat/data/dto/chat_dtos.dart", "class AsyncChatMessageRequestDto", "手机组装请求体")
    ref("api", "app/lib/features/chat/data/chat_api.dart", "Future<ChatMessageAcceptanceDto> acceptMessage", "发送与事件订阅")
    ref("harmony", "harmony_app/entry/src/main/ets/data/EchoRepository.ets", "async sendMessage(", "鸿蒙端使用同一文字请求协议")
    ref("schema", B + "features/chat/interface/schemas.py", "class AsyncChatMessageRequest", "请求结构校验")
    ref("auth", B + "shared/interface/dependencies.py", "def get_current_user", "从凭据识别当前用户")
    ref("router", B + "features/chat/interface/router.py", "def accept_message(", "配额、权限与受理响应")
    ref("accept", B + "features/chat/application/accept_message.py", "def execute(", "消息业务校验")
    ref("store", B + "features/chat/infrastructure/async_postgres_repository.py", "existing = self._find_existing_message", "同一消息去重与事务保存")
    ref("batch", B + "features/chat/infrastructure/async_postgres_repository.py", "def load_batch(", "读取一轮内的输入消息")
    ref("worker", B + "features/chat/application/process_turns.py", "async def run_once", "领取任务、生成、保存和推送")
    ref("context", B + "features/chat/infrastructure/context_builder.py", "async def build_chat_context", "准备模型上下文")
    ref("history", B + "features/chat/infrastructure/postgres_repositories.py", "def get_history(", "按账号、会话和边界读取近期消息")
    ref("historyTime", B + "features/chat/infrastructure/postgres_repositories.py", "def _render_timestamped_history(", "历史消息带时间标记")
    ref("renderer", B + "shared/prompting/renderer.py", "def render_prompt_layers(", "材料转成 role/content 列表")
    ref("product", B + "shared/config/settings.py", "system_prompt: str", "产品定位默认值与部署覆盖")
    ref("settings", B + "shared/config/settings.py", "class Settings", "读取环境配置和 .env")
    ref("persona", B + "features/assistant_persona/infrastructure/default_persona.py", "ECHO_PERSONA_V3 =", "固定人设；当前无闲聊示例")
    ref("ruleLoad", B + "shared/prompting/renderer.py", "def _load_rule", "导入时读取 Markdown 规则")
    for key, file in [("safety", "baseline-safety.md"), ("natural", "natural-dialogue.md"), ("calibration", "response-calibration.md")]:
        ref(key, B + "prompts/rules/" + file, "[", "规则正文：" + file)
    ref("prefs", B + "shared/prompting/renderer.py", "def render_persona(", "偏好字段转成有限行为提示")
    ref("relationship", B + "shared/prompting/renderer.py", "def render_relationship_guidance(", "关系数据转成表达指引")
    ref("time", B + "features/chat/domain/temporal_context.py", "def build_temporal_context(", "服务端计算时间事实")
    ref("prefix", B + "features/agent/application/orchestrate_chat.py", "def _build_initial_messages(", "Agent 增加执行与交付要求")
    ref("catalog", B + "features/agent/domain/tools.py", "def model_description(", "工具参数模型生成 JSON Schema")
    ref("registry", B + "features/agent/infrastructure/container.py", "def get_chat_agent(", "注册本渠道可用的工具")
    ref("model", B + "features/agent/infrastructure/model.py", "async def complete(", "把消息和工具清单交给模型 Provider")
    ref("loop", B + "features/agent/application/orchestrate_chat.py", "while model_steps < self.max_steps", "生成和工具调用的有限回路")
    ref("executor", B + "features/agent/application/execute_tool.py", "async def execute(", "工具执行前的程序门禁")
    ref("toolResult", B + "features/agent/application/orchestrate_chat.py", "def _tool_result_message(", "按调用编号追加工具结果")
    ref("timeTool", B + "features/agent/infrastructure/tools/time_tools.py", "class GetCurrentTimeArguments", "真实时间工具的参数模型")
    ref("prepare", B + "features/chat/application/generate_reply.py", "async def prepare(", "生成回复并进行表达和交付处理")
    ref("delivery", B + "features/agent/domain/delivery.py", "def validate_agent_delivery_segments(", "气泡段的有限内容校验")
    ref("events", B + "features/chat/interface/router.py", "async def chat_events(", "通过 SSE 推送与断线补齐")
    ref("ui", "app/lib/features/chat/presentation/chat_controller.dart", "void _mergeServerMessages(", "按服务端编号合并消息")

    def material(id, title, where, acquisition, why, references, status="unknown"):
        return dict(id=id, title=title, where=where, acquisition=acquisition, why=why,
                    refs=references, status=status)

    materials = [
        material("fixed", "产品、人设与规则", "源码、MD 与部署配置", "Settings 取配置；人格公开入口取固定对象；Renderer 读取规则文件并渲染。", "告诉模型 Echo 是谁、如何表达。当前普通聊天不附带固定 Few-shot。", ["product", "persona", "ruleLoad", "renderer"], "source"),
        material("preferences", "你的个性化设置", "user_personas 表", "get_persona(user_id) 读取；启用时映射风格、长度、称呼等白名单字段。", "偏好用于调整表达；它和 Echo 自己的人格不是同一份数据。", ["context", "prefs"]),
        material("relationship", "关系类型与熟悉进度", "relationship_states 表＋本轮信号", "get_relationship_context() 合并关系类型、阶段、边界与当前表达信号。", "朋友／AI 恋人与初识／熟悉等进度是不同维度。此处不拿今天的值冒充当时值。", ["context", "relationship"]),
        material("memory", "相关长期记忆", "user_memories、memory_embeddings 表", "用当前输入做相关性召回；无向量时可按重要性回退；非空才注入。", "只取可用背景，不是把整个数据库塞给模型。旧轮次实际召回内容未保存。", ["context", "renderer"]),
        material("summary", "会话摘要", "conversations.summary 与摘要边界", "读取当前会话摘要和 summary_message_id；摘要之外再读取近期原文。", "用摘要覆盖更早内容，减少反复携带全部聊天。此轮摘要快照未保存。", ["context", "history", "renderer"]),
        material("history", "这句之前的聊天", "chat_messages 表", "按账号、会话、摘要边界、当前输入之前的编号过滤；普通聊天最多取 20 条，再按先后排列。", "数据库确认此前有 9 条原文。页面使用这 9 条演示；当时最终选中了哪些条目未留快照。", ["history", "historyTime"], "record"),
        material("time", "本轮节奏与时间", "历史计算结果＋服务器时钟", "计算是否减少追问、重复问候，再生成时区、日期与会话间隔等事实。", "时间标记用于理解上下文；不能由日期推断某件事已经完成。历史时间 JSON 未保存。", ["context", "time"]),
        material("tools", "可调用工具的说明", "ToolRegistry 与工具参数模型", "按渠道和本步白名单筛选；Pydantic 参数模型生成 JSON Schema，单独放入 tools。", "说明书只表示能力。执行器和具体业务仍需检查权限、参数和执行结果。", ["registry", "catalog", "executor"], "source"),
    ]

    fixed, estimate = source_prompts()
    block_meta = [
        ("agent", "执行与交付要求", "prefix", "规则＋输出", "当前源码：普通聊天、允许主动表情的分支"),
        ("safety", "安全规则", "safety", "规则", "当前规则 MD 原文"),
        ("product", "Echo 产品定位", "product", "身份", "源码默认值；当时部署覆盖值未记录"),
        ("persona", "人格，无闲聊示例", "persona", "身份", "当前人格对象渲染全文；并非当时版本快照"),
        ("natural", "自然对话规则", "natural", "规则", "当前规则 MD 原文"),
        ("calibration", "回应策略", "calibration", "规则", "当前规则 MD 原文"),
        ("mode", "文字聊天指引", "renderer", "规则", "当前 chat 模式的实际渲染正文"),
    ]
    blocks = []
    for message, meta in zip(fixed[:7], block_meta):
        id, title, source, category, provenance = meta
        blocks.append(dict(id=id, title=title, role="system", content=message["content"],
                           ref=source, category=category, provenance=provenance,
                           evidence="source", estimatedTokens=estimate(message["content"])))
    for id, title, reference, conditional in [
        ("relationship", "关系表达指引", "relationship", False),
        ("preferences", "个性化偏好", "prefs", True),
        ("memory", "长期记忆", "renderer", True),
        ("summary", "会话摘要", "renderer", True),
        ("focus", "本轮追问与问候", "context", False),
        ("time", "时间指引与时间数据", "time", False),
    ]:
        text = "【教学占位：当时的" + title + "未保存快照" + ("；仅在存在且启用时加入" if conditional else "") + "】"
        blocks.append(dict(id=id, title=title, role="system", content=text, ref=reference,
                           category="上下文" if id not in {"focus"} else "规则",
                           evidence="unknown", provenance="位置示意；不代表当时的实际内容或是否存在",
                           conditional=conditional, estimatedTokens=0))
    zone = timezone(timedelta(hours=8))
    for message in case["messages"][:9]:
        stamp = datetime.fromisoformat(message["created_at"]).astimezone(zone).isoformat(timespec="seconds")
        content = f"[消息时间 {stamp} 周五 上午]\n{message['content']}"
        blocks.append(dict(id="history-" + str(message["id"]), title="历史原文 " + str(message["id"]),
                           role=message["role"], content=content, ref="historyTime", category="上下文",
                           evidence="replay", provenance="聊天原文真实；时间标记按当前格式和 UTC+8 复原；历史筛选边界未捕获",
                           estimatedTokens=estimate(content)))
    blocks.append(dict(id="current", title="你本轮的消息", role="user", content=current["content"],
                       ref="context", category="用户任务", evidence="record", provenance="服务器保存的真实输入原文",
                       estimatedTokens=estimate(current["content"])))

    steps = [
        dict(id="input", title="先有一句话", short="输入", place="手机", headline="你输入的是一句话，还没有 Prompt 大礼包。",
             body="这就是主线里唯一的新任务。此前的‘这么客气啊’会作为历史背景；可爱、傲娇的要求保留为本轮用户消息。",
             change="新增：本轮文本。人设、记忆和工具清单还没有装进手机请求。",
             conclusion="先记住主角：这一轮由你发出的 19 个字符开始。", refs=["client", "api", "harmony"],
             checks=["文字请求不能是空白。", "手机会先显示待发送气泡；这不代表服务器已收到。"], packet="input"),
        dict(id="envelope", title="装进手机请求", short="信封", place="手机 → Echo 服务端", headline="给文字装一个小信封，让服务端知道它是哪条消息。",
             body="POST /chat/messages 的请求体只携带本次文本、消息类型和客户端唯一编号。登录凭据随请求头发送；当前用户身份由服务端解析。",
             change="新增：client_message_id、message_type。正文仍然是原来的那句话。",
             conclusion="这个请求发给自己的 Echo 服务端；它不是直接发给大模型的请求。", refs=["client", "api", "harmony", "auth"],
             checks=["客户端编号使用 UUID；失败后重试同一条消息应复用编号。", "请求体不接受客户端随意指定其他账号的 user_id。"], packet="request"),
        dict(id="validate", title="先过服务端检查", short="校验", place="Echo 服务端", headline="先确认‘谁发的、格式对不对、能不能收’，再生成回复。",
             body="接口解析 UUID、消息类型和字段；身份验证、频率配额、业务长度、队列容量等检查共同保护入口。表情消息还要查归属和可用性。下面只是本地校验教学模拟。",
             change="新增：经过验证的当前账号与合格内容；失败在入口返回错误。",
             conclusion="Prompt 不是消息校验器，入口限制由程序执行。", refs=["auth", "schema", "router", "accept"],
             checks=["结构校验：空白文本、错误 UUID 或不兼容字段会被拒绝。", "接口 text 上限 10000 字符；业务上限配置默认 2000，可部署覆盖。", "频率、每日配额和队列容量也会拦截；不是只查长度。"], packet="request"),
        dict(id="queue", title="保存并组成一轮", short="入队", place="Echo 服务端 / 数据库", headline="先保存你的消息并回执，后台再领取这一轮。",
             body="事务中按账号和客户端编号查重、保存输入并创建或合并待处理轮次。短时间连续发送可能合并；这轮实际只有 1 条输入。HTTP 202 的意思是已受理。",
             change="新增：服务端消息编号、会话编号、turn_id 和处理状态。",
             conclusion="‘已发送’和‘Echo 已生成回复’是两个时间点。", refs=["store", "batch", "worker", "router"],
             checks=["同一编号、同一内容返回已有受理结果；同号换内容会冲突。", "同一用户的生成有并发保护；任务有状态与租约。", "去重不等于重试免费；入口的频率和配额检查仍会发生。"], packet="accepted"),
        dict(id="materials", title="按来源拿材料", short="取材", place="Echo 服务端 / Context Builder", headline="服务端开始收材料：固定配置、数据库记录、本轮计算。",
             body="不是让模型自己翻数据库。Context Builder 根据当前账号和会话，调用各业务入口拿数据，再决定哪些材料进入本轮。点一张材料卡查看‘在哪里、怎么取、为什么要取’。",
             change="新增：上下文材料。旧轮次的偏好、关系、摘要和召回结果没有完整快照，页面不会猜。",
             conclusion="来源回答‘内容从哪来’，装配顺序回答‘它放在哪’。", refs=["context", "history", "renderer"],
             checks=["历史查询按账号、会话与当前消息之前的边界过滤。", "记忆、摘要、偏好按条件加入；读不到时有跳过或回退分支。", "六类是内容分类，实际还按 chat 等模式做选择；尚无完整的六类资产选择引擎。"], packet="materials"),
        dict(id="assembly", title="排成消息列表", short="拼接", place="Echo 服务端 / Renderer + Context Builder", headline="‘拼接’主要是在排列表，不是把所有内容糊成一个字符串。",
             body="共享 Renderer 先产出一组 system 消息；Context Builder 再追加本轮指引、时间、历史和本轮 user 消息。Agent 最后在列表最前面补执行和交付说明。这里直接看最终列表从头到尾如何放入。",
             change="结果：messages = [system 材料…, 历史 user/assistant…, 本轮 user]。",
             conclusion="六类内容不等于六个 role。普通闲聊当前不注入 Few-shot。", refs=["renderer", "context", "prefix"],
             checks=["历史保留 user / assistant 角色；本轮任务在末尾。", "记忆、摘要虽然装在 system 消息里，仍被文字边界标注为背景数据。", "这些文字标注不是程序级权限隔离，也不能保证模型永不受误导。"], packet="messages"),
        dict(id="model", title="附上工具说明书", short="模型请求", place="Echo 服务端 → 模型 Provider", headline="消息列表旁边，再放一份模型可选的工具说明书。",
             body="模型适配器接收 messages、tools 与生成参数。tools 来自注册表和参数模型，按渠道及白名单筛选；不是把工具源码贴进用户消息里。本轮实际没有工具调用。",
             change="新增：messages 之外的 tools 与生成参数；模型现在才拿到本轮上下文。",
             conclusion="工具描述是‘能申请做什么’，工具返回值才是‘实际做成了什么’。", refs=["registry", "catalog", "model", "loop"],
             checks=["真实记录：主生成 step_count=1，工具执行记录为 0。", "这不是总 Provider 请求次数：表情语义等辅助分类调用可能另算。", "步骤数、工具次数和整轮截止时间共同限制 Agent 回路。"], packet="model"),
        dict(id="reply", title="生成并检查回复", short="回复处理", place="模型 → Echo 服务端", headline="模型返回候选内容，服务端检查后才准备聊天气泡。",
             body="普通聊天要求输出自然文字。Agent 和回复用例处理交付格式、部分表达问题、失败重试或兜底，再按语义形成气泡段。这里展示的是服务器最终保存的真实气泡，不是未留存的模型原始响应。",
             change="新增：两段准备交付的回复。模型内部推理没有被抓取或展示。",
             conclusion="两个气泡不等于生成了两次；这轮主生成只有 1 步。", refs=["prepare", "delivery", "loop"],
             checks=["交付检查覆盖空段、重复段、超过段数和部分协议字段泄漏。", "表达检查和提示词不能验证所有事实，也不能保证语气永远自然。", "遇到工具申请会走执行与回填分支；这轮直接走文字回复。"], packet="reply"),
        dict(id="persist", title="保存后推送结果", short="落库推送", place="Echo 服务端 / 数据库 → 事件通道", headline="确认可交付后，先保存回复组，再通知手机取结果。",
             body="complete_turn 事务保存回复和轮次完成状态。后续执行摘要检查、记忆提取调度和关系信号记录，再发布 chat.delivery.created；typing.stopped 用于结束输入状态。",
             change="新增：reply_group_id、每条气泡的编号和顺序、对应输入编号。",
             conclusion="记忆是单独业务流程；不是模型在回复后自动永久记住一切。", refs=["worker", "delivery", "events"],
             checks=["保存前再次校验交付段；完成轮次避免重复写同组回复。", "摘要可后台调度，记忆提取有门控；不是每条消息都必定写记忆。", "保存成功后处理失败会记录日志；不能把已保存的回复当作未发生。"], packet="event"),
        dict(id="screen", title="手机显示两条气泡", short="显示", place="手机", headline="手机收到事件、合并编号，把两条文字画成气泡。",
             body="客户端订阅 GET /chat/events 的 SSE 事件，按编号合并消息并按展示节奏呈现。断线重连时使用已有最大编号补齐历史。当前文字聊天的事件交付不能等同于逐 token 转发。",
             change="最终可见：你发出的那句话，和 Echo 保存下来的两条回答。",
             conclusion="手机负责展示；上下文的读取、装配与工具执行发生在服务端。", refs=["api", "events", "ui"],
             checks=["同一条服务端消息再次收到时合并，而不是多画一条。", "SSE 负责事件传输，持久化历史负责断线补齐。", "上下文、工具参数和内部 system 消息不作为普通聊天气泡下发。"], packet="event"),
    ]
    from pydantic import BaseModel, Field
    tool_tree = ast.parse(read("Echo-backend/features/agent/infrastructure/tools/time_tools.py"))
    arguments = next(n for n in tool_tree.body if isinstance(n, ast.ClassDef) and n.name == "GetCurrentTimeArguments")
    tool_scope = {"BaseModel": BaseModel, "Field": Field}
    exec(compile(ast.Module(body=[arguments], type_ignores=[]), "isolated-tool-schema", "exec"), tool_scope)
    specification = next(n for n in ast.walk(tool_tree) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name) and n.func.id == "ToolSpecification")
    tool_description = ast.literal_eval(next(k.value for k in specification.keywords if k.arg == "description"))
    tool_schema = {"type": "function", "function": {
        "name": "get_current_time", "description": tool_description,
        "parameters": tool_scope["GetCurrentTimeArguments"].model_json_schema(),
    }}
    graph = {"id": "turn-flow", "type": "flowchart", "layout": {"direction": "LR", "rankSpacing": "normal", "edgeRouting": "curved"},
             "groups": [], "nodes": [{"id": s["id"], "label": s["short"], "kind": "process"} for s in steps],
             "edges": [{"id": "edge-" + str(i), "from": steps[i]["id"], "to": steps[i + 1]["id"], "kind": "flow"} for i in range(len(steps) - 1)],
             "notes": ["主流程从左到右，由本地 Dagre 自动布局；当前步骤高亮，节点可以点击。"]}
    case.pop("server_revision", None)  # Use the local source revision; historical prompt revision is unknown.
    data = dict(case=case, steps=steps, materials=materials, blocks=blocks, refs=refs, graph=graph,
                toolSchema=tool_schema, generated="2026-10-23", selectedId=current["id"],
                evidence="聊天原文、保存的回复、轮次和主生成步数来自数据库。中间请求按当前源码复原，含明确占位；不是当时抓包。")
    assert all(reference in refs for s in steps for reference in s["refs"])
    assert len(graph["nodes"]) <= 12
    dagre = read("docs/chat-flow-page/vendor/dagre.min.js")
    license_text = read("docs/chat-flow-page/vendor/DAGRE-LICENSE.txt")
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    page = read("docs/chat-turn-walkthrough/template.html").replace("__CASE_DATA__", payload)
    page = page.replace("__DAGRE_BUNDLE__", dagre).replace("__DAGRE_LICENSE__", license_text.replace("--", "—"))
    assert not re.search(r"(?:src|href)\s*=\s*['\"]https?://", page, re.I)
    assert "__CASE_DATA__" not in page and "__DAGRE_BUNDLE__" not in page
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print(f"Built offline private page: {output}")
    print(f"Verified {len(refs)} source anchors, {len(steps)} steps, {len(blocks)} message-position entries")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=PRIVATE / "case.json")
    parser.add_argument("--output", type=Path, default=PRIVATE / "index.html")
    args = parser.parse_args()
    build(args.snapshot.resolve(), args.output.resolve())

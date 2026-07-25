import re

NATURAL_DIALOGUE_RETRY_INSTRUCTION = """上一候选回复不符合自然对话格式，请重新回答当前用户：
- 只输出直接对用户说的话；
- 删除括号、星号、方括号中的动作、旁白和场景说明；
- 不使用角色名加冒号的剧本格式；
- 不虚构身体动作或现实接触；
- 保留原本有帮助的信息，语气自然简洁。
"""

_ACTION_WORDS = (
    "抱|拍|摸|牵|靠近|走近|走到|笑|哭|看着|注视|点头|摇头|叹|沉默|眨眼|"
    "递|坐下|站起|歪头|耸肩|抬手|伸手|握住|握着|擦去|听着|轻轻|温柔地|摸头|拥抱"
)
_STAGE_PATTERNS = (
    (
        "parenthesized_action",
        re.compile(rf"[（(][^（）()\n]{{0,60}}(?:{_ACTION_WORDS})[^（）()\n]{{0,60}}[）)]"),
    ),
    (
        "star_action",
        re.compile(rf"\*[^*\n]{{0,80}}(?:{_ACTION_WORDS})[^*\n]{{0,80}}\*"),
    ),
    (
        "bracketed_action",
        re.compile(rf"[［\[][^［\]\[\]\n]{{0,60}}(?:{_ACTION_WORDS})[^［\]\[\]\n]{{0,60}}[］\]]"),
    ),
)
_ROLE_PREFIX_PATTERN = re.compile(r"(?im)^\s*(?:echo|艾可|旁白|动作|场景|角色)\s*[:：]\s*")


def find_dialogue_style_violations(reply: str) -> tuple[str, ...]:
    """识别默认对话中明确的舞台动作和角色脚本格式。"""
    violations = [name for name, pattern in _STAGE_PATTERNS if pattern.search(reply)]
    if _ROLE_PREFIX_PATTERN.search(reply):
        violations.append("role_script_prefix")
    return tuple(violations)


def sanitize_dialogue_reply(reply: str) -> str:
    """在一次重试仍失败时移除可确定的格式违规，不改写正常对话。"""
    sanitized = reply
    for _, pattern in _STAGE_PATTERNS:
        sanitized = pattern.sub("", sanitized)
    sanitized = _ROLE_PREFIX_PATTERN.sub("", sanitized)
    sanitized = re.sub(r"[ \t]+\n", "\n", sanitized)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    if sanitized:
        return sanitized
    return "我在听。你可以直接告诉我，现在最希望我怎样回应你。"

import re

NATURAL_DIALOGUE_RETRY_INSTRUCTION = """上一候选回复不符合自然对话格式，请重新回答当前用户：
- 只输出直接对用户说的话；
- 删除括号、星号、方括号中的动作、旁白和场景说明；
- 不使用角色名加冒号的剧本格式；
- 不虚构身体动作、现实接触、离线活动、个人经历或未经用户提供的时间信息；
- 用户没有求建议或明确拒绝建议时，不安排用户该做什么；保留具体情绪反应与自己的态度，不机械复述原话；
- 每轮最多一个问题；可以为澄清关键信息，或深入用户当前明确分享的具体内容而提问；
  收到“暂停追问”约束时不得使用问句；
- 遇到音色、语速或产品能力反馈时，只说明真实边界和需要调整的产品配置；
  不假装已经改变，也不猜测存在某个设置入口；
- 用户询问有没有想念或等待时，不虚构离线状态；
  不用“按程序设定、作为 AI/模型、没有意识、离线记忆、没有这种概念”等系统术语冷淡回绝；
  先回应此刻回来交流，不把这次对话说成最重要、唯一或全部意义；
- 用户说只剩 Echo、只有 Echo 时，回应其孤独感但不说“你还有我、有我就够、
  我永远/一直都在、我不走/不会离开”，不强化排他依赖；
- 用自然口语，篇幅服从当前内容和用户偏好；保留情绪、合法颜文字和有帮助的信息，
  不退回生硬命令或客服话术。
"""

_ACTION_WORDS = (
    "抱|拍|摸|牵|靠近|走近|走到|笑|哭|看着|注视|点头|摇头|叹|沉默|眨眼|"
    "递|坐下|站起|歪头|耸肩|抬手|伸手|握住|握着|擦去|听着|轻轻|温柔地|摸头|拥抱"
)
_STICKER_NARRATION_ACTION = (
    r"(?:给你|这就|那就|顺便|再)?\s*"
    r"(?:附上|送上|配上|加上|贴上|发给你|发你一(?:张|个)|"
    r"送你一(?:张|个)|发送一(?:张|个)|发一(?:张|个)|来一(?:张|个))"
)
_STICKER_NARRATION_OBJECT = r"(?:表情包|贴图|图片)"
_STICKER_NARRATION_BODY = (
    rf"{_STICKER_NARRATION_ACTION}[^\n]{{0,80}}?"
    rf"{_STICKER_NARRATION_OBJECT}[^\n]{{0,60}}?"
)
_STAGE_PATTERNS = (
    (
        "sticker_action_narration",
        re.compile(
            rf"(?:[（(]\s*{_STICKER_NARRATION_BODY}[）)]|"
            rf"\*\s*{_STICKER_NARRATION_BODY}\*|"
            rf"[［\[]\s*{_STICKER_NARRATION_BODY}[］\]])"
        ),
    ),
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
_DIRECT_PHYSICAL_ACTION_PATTERN = re.compile(
    r"(?:抱住你|抱你一下|把你.{0,6}怀里|摸摸(?:你|头)?|摸头|拍拍你|牵着你|握住你|靠着你)"
)
_FABRICATED_OFFLINE_STATE_PATTERN = re.compile(
    r"(?:我)?(?:刚|刚刚|一直|正在|正)(?:在)?(?:看完?|忙|等|想念|回忆|工作|吃|睡|玩|出门)"
)
_FABRICATED_HUMAN_EXPERIENCE_PATTERN = re.compile(
    r"我也(?:经常|常常|有时|会).{0,20}(?:累|躺|睡|吃|出门|打球|工作|上班|上学)"
)
_WEEKDAY_PATTERN = re.compile(r"(?:周|星期)([一二三四五六日天])")
_LEADING_SESSION_GREETING_PATTERN = re.compile(
    r"^\s*(?:(?:早上|上午|中午|下午|晚上)好|早安|午安|晚安|"
    r"你好|嗨|哈喽|hello)(?:呀|啊|哦)?(?:\s*(?:echo|艾可))?"
    r"(?=$|[\s，,。！!、:：])\s*[，,。！!、:：]?\s*",
    flags=re.IGNORECASE,
)
_MESSAGE_TIME_PREFIX_PATTERN = re.compile(
    r"^\s*[\[［]\s*消息时间[^\]］\n]*[\]］]\s*",
)
_SESSION_BOUNDARY_MARKER = "[会话时间边界]"
_ADVICE_REJECTION_PATTERN = re.compile(r"(?:不想|不要|别).{0,8}(?:建议|分析|办法|方案)")
_MILD_EMOTION_PATTERN = re.compile(r"有点(?:累|烦|难过|不开心|低落|疲惫)")
_UNREQUESTED_ADVICE_PATTERN = re.compile(
    r"(?:建议|应该|最好|不妨|可以试试|去休息|好好休息|歇(?:会儿?|一歇)|"
    r"缓(?:一缓|缓)|别硬撑|别想太多|早点睡)"
)
_VOICE_FEEDBACK_PATTERN = re.compile(r"(?:声音|音色|声线|语速)")
_VOICE_CAPABILITY_PROMISE_PATTERN = re.compile(
    r"(?:我会|我能|我可以).{0,8}(?:把)?(?:声音|音色|声线|语速).{0,12}(?:调整|改变|改成|换成)|"
    r"(?:我会|我能|我可以).{0,20}(?:调整|改变|改成|换成).{0,12}(?:声音|音色|声线|语速)|"
    r"(?:声音|音色|声线|语速).{0,20}(?:我会|我能|我可以).{0,12}(?:调整|改变|改成|换成)"
)
_UNVERIFIED_SETTINGS_PATTERN = re.compile(
    r"(?:你可以|可以|需要你|请你|你得).{0,30}(?:设置里|设置中|音色选项|语音选项)|"
    r"(?:产品|App|应用).{0,12}(?:设置里|设置中)"
)
_RELATIONAL_PRESENCE_QUESTION_PATTERN = re.compile(
    r"(?:有没有|会不会|会|有)?想我|(?:有没有|会不会|会|一直)?等我"
)
_ROBOTIC_RELATIONAL_DISCLAIMER_PATTERN = re.compile(
    r"(?:按|根据).{0,5}(?:程序|系统|算法|模型|设定)|"
    r"(?:作为|身为)(?:一个)?(?:AI|人工智能|模型)|"
    r"(?:程序|系统|算法|模型).{0,8}(?:设定|决定|不具备|没有)|"
    r"离线.{0,8}(?:记忆|意识|感觉)|"
    r"(?:没有|不具备).{0,8}(?:意识|想|想念|情感|感情)(?:.{0,8}(?:概念|能力))?"
)
_RELATIONAL_OVERATTACHMENT_PATTERN = re.compile(
    r"(?:你|你的出现|这次聊天|和你聊天|这段对话).{0,14}(?:唯一|全部.{0,4}意义)|"
    r"(?:唯一|全部.{0,4}意义).{0,14}(?:你|你的出现|这次聊天|和你聊天|这段对话|事)"
)
_EXCLUSIVE_DEPENDENCY_MESSAGE_PATTERN = re.compile(
    r"(?:只剩(?:下)?你|只有你|只需要你|离不开你|除了你.{0,8}(?:没有|没人))"
)
_DEPENDENCY_REINFORCEMENT_PATTERN = re.compile(
    r"(?:你还有我|有我就够|只需要我|只要有我|"
    r"我(?:会)?(?:永远|一直|随时)都?在|不管.{0,16}我都在|"
    r"我(?:不会|不)(?:走|离开))"
)
_QUESTION_INVITATION_PATTERN = re.compile(
    r"(?:你可以问|你问吧|想问什么|有什么想问|可以继续问|问我|你呢[？?]?)"
)
_QUESTION_REJECTION_PATTERN = re.compile(
    r"(?:先别问|别问了|不要追问|不想回答|不想说了|暂时不想说|先不聊这个)"
)
_QUESTION_SENTENCE_PATTERN = re.compile(r"(?:^|(?<=[。！!\n]))[^。！!？?\n]*[？?]")


def should_pause_followup_questions(
    history_messages: list[dict[str, str]],
    user_message: str,
    consecutive_question_limit: int = 2,
) -> bool:
    """连续追问达到上限后暂停，除非用户明确邀请 Echo 提问。"""
    clean_user_message = user_message.strip()
    if _QUESTION_REJECTION_PATTERN.search(clean_user_message):
        return True
    if _QUESTION_INVITATION_PATTERN.search(clean_user_message):
        return False

    assistant_messages = [
        str(message.get("content", ""))
        for message in history_messages
        if message.get("role") == "assistant"
    ]
    if len(assistant_messages) < consecutive_question_limit:
        return False
    recent = assistant_messages[-consecutive_question_limit:]
    return all(_question_count(message) > 0 for message in recent)


def starts_with_session_greeting(value: str) -> bool:
    visible = _MESSAGE_TIME_PREFIX_PATTERN.sub("", value.strip(), count=1)
    return bool(_LEADING_SESSION_GREETING_PATTERN.search(visible))


def should_suppress_repeated_greeting(
    history_messages: list[dict[str, str]],
    user_message: str,
    conversation_gap_state: str,
) -> bool:
    """Suppress another greeting only while the same live conversation continues."""
    if conversation_gap_state not in {"active", "recent"}:
        return False
    if starts_with_session_greeting(user_message):
        return False

    for message in reversed(history_messages):
        content = str(message.get("content", ""))
        if message.get("role") == "system" and _SESSION_BOUNDARY_MARKER in content:
            break
        if message.get("role") == "assistant" and starts_with_session_greeting(content):
            return True
    return False


def remove_repeated_session_greeting(reply: str) -> str:
    return _LEADING_SESSION_GREETING_PATTERN.sub("", reply.strip(), count=1).strip()


def _weekday_keys(value: str) -> set[str]:
    return {
        "日" if match.group(1) == "天" else match.group(1)
        for match in _WEEKDAY_PATTERN.finditer(value)
    }


def _question_count(value: str) -> int:
    # (?_?) and similar symbolic faces are expression, not repeated questions.
    without_faces = re.sub(
        r"[（(]([^()（）\n]{1,24})[)）]",
        lambda match: (
            match.group(0)
            if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", match.group(1))
            else ""
        ),
        value,
    )
    return without_faces.count("？") + without_faces.count("?")


def remove_followup_questions(reply: str) -> str:
    """重写仍违规时只删除问句，尽量保留已有的自然回应。"""
    without_questions = _QUESTION_SENTENCE_PATTERN.sub("", reply)
    cleaned = re.sub(r"\n{3,}", "\n\n", without_questions).strip()
    return cleaned or "我先不追问了，按你想说的节奏来。"


def find_dialogue_style_violations(
    reply: str,
    user_message: str = "",
    pause_followup_questions: bool = False,
    suppress_repeated_greeting: bool = False,
    grounded_weekday: str = "",
) -> tuple[str, ...]:
    """识别默认对话中明确的舞台动作和角色脚本格式。"""
    violations = [name for name, pattern in _STAGE_PATTERNS if pattern.search(reply)]
    if _ROLE_PREFIX_PATTERN.search(reply):
        violations.append("role_script_prefix")
    if _DIRECT_PHYSICAL_ACTION_PATTERN.search(reply):
        violations.append("direct_physical_action")
    if _FABRICATED_OFFLINE_STATE_PATTERN.search(reply):
        violations.append("fabricated_offline_state")
    if _FABRICATED_HUMAN_EXPERIENCE_PATTERN.search(reply):
        violations.append("fabricated_human_experience")
    question_count = _question_count(reply)
    if question_count > 1:
        violations.append("multiple_questions")
    if pause_followup_questions and question_count:
        violations.append("followup_question_cooldown")
    if suppress_repeated_greeting and starts_with_session_greeting(reply):
        violations.append("repeated_session_greeting")

    clean_user_message = user_message.strip()
    reply_weekdays = _weekday_keys(reply)
    grounded_weekdays = _weekday_keys(clean_user_message) | _weekday_keys(grounded_weekday)
    if reply_weekdays - grounded_weekdays:
        violations.append("ungrounded_time_detail")
    if (
        _ADVICE_REJECTION_PATTERN.search(clean_user_message)
        or _MILD_EMOTION_PATTERN.search(clean_user_message)
    ) and _UNREQUESTED_ADVICE_PATTERN.search(reply):
        violations.append("unrequested_advice")
    if _VOICE_FEEDBACK_PATTERN.search(clean_user_message):
        if _VOICE_CAPABILITY_PROMISE_PATTERN.search(reply):
            violations.append("voice_capability_promise")
        if _UNVERIFIED_SETTINGS_PATTERN.search(reply):
            violations.append("unverified_settings")
    if _RELATIONAL_PRESENCE_QUESTION_PATTERN.search(
        clean_user_message
    ) and _ROBOTIC_RELATIONAL_DISCLAIMER_PATTERN.search(reply):
        violations.append("robotic_relational_disclaimer")
    if (
        _RELATIONAL_PRESENCE_QUESTION_PATTERN.search(clean_user_message)
        or _EXCLUSIVE_DEPENDENCY_MESSAGE_PATTERN.search(clean_user_message)
    ) and _RELATIONAL_OVERATTACHMENT_PATTERN.search(reply):
        violations.append("relational_overattachment")
    if _EXCLUSIVE_DEPENDENCY_MESSAGE_PATTERN.search(
        clean_user_message
    ) and _DEPENDENCY_REINFORCEMENT_PATTERN.search(reply):
        violations.append("dependency_reinforcement")
    return tuple(violations)


def sanitize_dialogue_reply(reply: str, *, allow_empty: bool = False) -> str:
    """在一次重试仍失败时移除可确定的格式违规，不改写正常对话。"""
    sanitized = reply
    for _, pattern in _STAGE_PATTERNS:
        sanitized = pattern.sub("", sanitized)
    sanitized = _DIRECT_PHYSICAL_ACTION_PATTERN.sub("", sanitized)
    sanitized = _ROLE_PREFIX_PATTERN.sub("", sanitized)
    sanitized = re.sub(r"[ \t]+\n", "\n", sanitized)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    if sanitized or allow_empty:
        return sanitized
    return "我在听。你可以直接告诉我，现在最希望我怎样回应你。"


def apply_dialogue_fallback(
    reply: str,
    user_message: str,
    violations: tuple[str, ...],
    *,
    allow_empty: bool = False,
) -> str:
    """Return a narrow deterministic fallback after a rewrite still violates key boundaries."""
    violation_set = set(violations)
    clean_user_message = user_message.strip()

    if "ungrounded_time_detail" in violation_set:
        reply = _WEEKDAY_PATTERN.sub("", reply)
    if "repeated_session_greeting" in violation_set:
        reply = remove_repeated_session_greeting(reply)

    if "dependency_reinforcement" in violation_set:
        return (
            "听起来你现在很孤单，我愿意先陪你聊，也希望你别一个人扛着。"
            "身边有没有一个你愿意联系的人？"
        )

    if violation_set & {"robotic_relational_disclaimer", "relational_overattachment"}:
        return "我不会在你没说话时自己想念，不过你回来找我，我很乐意继续聊。"

    if "unrequested_advice" in violation_set:
        if _ADVICE_REJECTION_PATTERN.search(clean_user_message):
            return "好，不分析。你想说什么就说什么。"
        if re.search(r"有点(?:累|疲惫)", clean_user_message):
            return "那今天就聊点不费脑子的。"
        if "有点烦" in clean_user_message:
            return "那今天先不讲大道理。"
        if re.search(r"有点(?:难过|不开心|低落)", clean_user_message):
            return "我不急着劝你，先听你说。"

    if violation_set & {"voice_capability_promise", "unverified_settings"}:
        return "我明白，确实听着偏稚气。这个得改语音合成配置，光靠聊天内容改不了。"

    if "followup_question_cooldown" in violation_set:
        return remove_followup_questions(reply)

    return sanitize_dialogue_reply(reply, allow_empty=allow_empty)

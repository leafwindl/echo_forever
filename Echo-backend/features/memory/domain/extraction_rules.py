import json
from typing import Dict, List, Optional

from features.memory.domain.entities import Memory, MemoryGateResult

ALLOWED_MEMORY_TYPES = {
    "profile",
    "preference",
    "relationship",
    "goal",
    "event",
    "boundary",
}
MIN_MEMORY_CONFIDENCE = 0.65
MEMORY_TRIGGER_KEYWORDS = (
    "记住",
    "记一下",
    "帮我记",
    "你要记得",
    "以后",
    "以后叫我",
    "叫我",
    "称呼我",
    "我叫",
    "我的名字",
    "我是",
    "我喜欢",
    "我不喜欢",
    "我更喜欢",
    "我讨厌",
    "我希望你",
    "我想让你",
    "不要再",
    "别再",
    "不用记",
    "别记",
    "忘掉",
    "忘记",
    "删掉",
    "我最近在",
    "我正在",
    "我打算",
    "我计划",
    "我的目标",
    "我想要",
    "我在准备",
    "我男朋友",
    "我女朋友",
    "我妈妈",
    "我爸爸",
    "我姐姐",
    "我妹妹",
    "我哥哥",
    "我弟弟",
    "我朋友",
    "remember",
    "forget",
    "call me",
    "my name is",
    "i like",
    "i don't like",
    "i prefer",
    "i am",
    "i'm",
    "from now on",
)


def should_extract_memory(user_message: str) -> MemoryGateResult:
    text = user_message.strip()
    if not text:
        return MemoryGateResult(False, "empty_message")

    normalized_text = text.lower()
    for keyword in MEMORY_TRIGGER_KEYWORDS:
        if keyword in normalized_text:
            return MemoryGateResult(True, f"keyword:{keyword}")

    return MemoryGateResult(False, "no_memory_signal")


def normalize_memory_content(content: str) -> str:
    return "".join(content.strip().lower().split())


def coerce_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.8
    return max(0.0, min(1.0, confidence))


def coerce_importance(value: object) -> int:
    try:
        importance = int(value)
    except (TypeError, ValueError):
        importance = 3
    return max(1, min(5, importance))


def format_existing_memories(memories: List[Memory]) -> str:
    if not memories:
        return "无"

    lines = []
    for memory in memories:
        lines.append(
            "- "
            f"memory_id={memory.memory_id} | "
            f"type={memory.memory_type} | "
            f"importance={memory.importance.value} | "
            f"content={memory.content}"
        )
    return "\n".join(lines)


def build_extraction_messages(
    user_message: str,
    assistant_reply: str,
    existing_memories: List[Memory],
) -> list[dict]:
    prompt = f"""
请从当前这一轮对话中判断是否有值得长期记住的用户信息。

可以记住：
- 用户明确表达的稳定身份、称呼、偏好、目标、关系、重要事件、交互边界
- 用户明确说“记住”“以后”“我喜欢/不喜欢”“叫我”等长期倾向
- 用户纠正了之前的信息

不要记住：
- 一次性的普通情绪或闲聊
- 你的推测、安慰话术、诊断判断
- 敏感信息，除非用户明确要求长期记住
- 用户说“不用记”“忘掉”“别记住”的内容

已有长期记忆：
{format_existing_memories(existing_memories)}

当前用户消息：
{user_message}

当前 Echo 回复：
{assistant_reply}

请只输出 JSON，不要输出解释。格式如下：
{{
  "memories": [
    {{
      "action": "create | update | deactivate | ignore",
      "target_memory_id": "需要更新或失效的已有 memory_id，没有则为空字符串",
      "memory_type": "profile | preference | relationship | goal | event | boundary",
      "content": "用一句中文写成稳定、可复用的记忆",
      "confidence": 0.0,
      "importance": 1
    }}
  ]
}}
"""
    return [
        {"role": "system", "content": "你是 Echo 的结构化长期记忆抽取模块，只能输出合法 JSON。"},
        {"role": "user", "content": prompt.strip()},
    ]


def strip_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        return text[start : end + 1]
    return text


def parse_memory_extraction(raw_text: str) -> List[Dict[str, object]]:
    payload = json.loads(strip_json_text(raw_text))
    memories = payload.get("memories", [])
    if not isinstance(memories, list):
        return []
    return [memory for memory in memories if isinstance(memory, dict)]


def find_duplicate_memory(
    active_memories: List[Memory],
    memory_type: str,
    content: str,
) -> Optional[Memory]:
    normalized_content = normalize_memory_content(content)
    for memory in active_memories:
        if memory.memory_type != memory_type:
            continue
        if normalize_memory_content(memory.content) == normalized_content:
            return memory
    return None

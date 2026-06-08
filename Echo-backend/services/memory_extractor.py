import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from config import settings
from llm_client import request_llm
from services.memory import (
    add_user_memory,
    deactivate_user_memory,
    get_user_memory,
    list_user_memories,
    touch_user_memory,
    update_user_memory,
)
from services.vector_store import delete_memory_embedding, upsert_memory_embedding

logger = logging.getLogger(__name__)

ALLOWED_MEMORY_TYPES = {
    "profile",
    "preference",
    "relationship",
    "goal",
    "event",
    "boundary",
}
MIN_MEMORY_CONFIDENCE = 0.65
MAX_EXISTING_MEMORIES_FOR_EXTRACTION = 30
_BACKGROUND_MEMORY_TASKS: set[asyncio.Task] = set()
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


@dataclass
class MemoryGateResult:
    """规则门控结果：决定本轮是否值得进入 LLM 记忆抽取。"""

    should_extract: bool
    reason: str


@dataclass
class MemoryExtractionResult:
    """一次记忆抽取的落库结果，方便 Chat Service 做日志和后续观测。"""

    created: int = 0
    updated: int = 0
    deactivated: int = 0
    ignored: int = 0


def should_extract_memory(user_message: str) -> MemoryGateResult:
    """用低成本规则先筛一遍，避免普通闲聊每轮都调用抽取模型。"""
    text = user_message.strip()
    if not text:
        return MemoryGateResult(False, "empty_message")

    normalized_text = text.lower()
    for keyword in MEMORY_TRIGGER_KEYWORDS:
        if keyword in normalized_text:
            return MemoryGateResult(True, f"keyword:{keyword}")

    return MemoryGateResult(False, "no_memory_signal")


def _normalize_content(content: str) -> str:
    return "".join(content.strip().lower().split())


def _coerce_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.8
    return max(0.0, min(1.0, confidence))


def _coerce_importance(value: object) -> int:
    try:
        importance = int(value)
    except (TypeError, ValueError):
        importance = 3
    return max(1, min(5, importance))


def _format_existing_memories(memories: List[Dict[str, object]]) -> str:
    if not memories:
        return "无"

    lines = []
    for memory in memories:
        lines.append(
            "- "
            f"memory_id={memory['memory_id']} | "
            f"type={memory['memory_type']} | "
            f"importance={memory['importance']} | "
            f"content={memory['content']}"
        )
    return "\n".join(lines)


def _build_extraction_messages(
    user_message: str,
    assistant_reply: str,
    existing_memories: List[Dict[str, object]],
) -> list[dict]:
    """构建记忆抽取 prompt。

    这里要求 LLM 只输出 JSON，后端只信任可解析、类型合法、置信度足够的结果。
    """
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
{_format_existing_memories(existing_memories)}

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


def _strip_json_text(raw_text: str) -> str:
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
    """解析 LLM 的记忆抽取 JSON；解析失败时交给调用方决定是否记录日志。"""
    payload = json.loads(_strip_json_text(raw_text))
    memories = payload.get("memories", [])
    if not isinstance(memories, list):
        return []
    return [memory for memory in memories if isinstance(memory, dict)]


def _find_duplicate_memory(
    active_memories: List[Dict[str, object]],
    memory_type: str,
    content: str,
) -> Optional[Dict[str, object]]:
    normalized_content = _normalize_content(content)
    for memory in active_memories:
        if memory.get("memory_type") != memory_type:
            continue
        if _normalize_content(str(memory.get("content", ""))) == normalized_content:
            return memory
    return None


def _resolve_target_memory(
    user_id: str,
    target_memory_id: str,
) -> Optional[Dict[str, object]]:
    if not target_memory_id:
        return None
    return get_user_memory(user_id, target_memory_id)


async def _safe_upsert_memory_embedding(user_id: str, memory_id: str, content: str):
    """embedding 是检索增强能力，失败不应影响结构化记忆本身落库。"""
    try:
        await upsert_memory_embedding(user_id, memory_id, content)
    except ValueError as exc:
        logger.warning("Memory embedding skipped for user_id=%s memory_id=%s: %s", user_id, memory_id, exc)
    except Exception:
        logger.exception("Memory embedding upsert failed for user_id=%s memory_id=%s", user_id, memory_id)


def _safe_delete_memory_embedding(user_id: str, memory_id: str):
    """记忆失效时同步移除向量；失败只记录日志，检索时仍会按 active 记忆过滤。"""
    try:
        delete_memory_embedding(user_id, memory_id)
    except Exception:
        logger.exception("Memory embedding delete failed for user_id=%s memory_id=%s", user_id, memory_id)


async def extract_and_store_memories(
    user_id: str,
    user_message: str,
    assistant_reply: str,
    source_message_id: Optional[int] = None,
) -> MemoryExtractionResult:
    """从一轮对话中抽取结构化长期记忆并落库。

    当前阶段先做关系库内的结构化记忆，不做向量召回；下一阶段再给这些记忆补 embedding。
    """
    active_memories = list_user_memories(
        user_id,
        status="active",
        limit=MAX_EXISTING_MEMORIES_FOR_EXTRACTION,
    )
    messages = _build_extraction_messages(user_message, assistant_reply, active_memories)
    raw_result = await request_llm(
        messages,
        model=settings.memory_extraction_model or None,
        temperature=settings.memory_extraction_temperature,
        max_tokens=settings.memory_extraction_max_tokens,
    )

    try:
        extracted_memories = parse_memory_extraction(raw_result)
    except json.JSONDecodeError:
        logger.warning("Memory extraction returned invalid JSON for user_id=%s: %s", user_id, raw_result)
        return MemoryExtractionResult(ignored=1)

    result = MemoryExtractionResult()
    for item in extracted_memories:
        action = str(item.get("action", "ignore")).strip().lower()
        target_memory_id = str(item.get("target_memory_id") or item.get("memory_id") or "").strip()
        memory_type = str(item.get("memory_type", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        confidence = _coerce_confidence(item.get("confidence"))
        importance = _coerce_importance(item.get("importance"))

        if action in {"ignore", "none", ""}:
            result.ignored += 1
            continue

        if action in {"deactivate", "delete", "forget", "remove"}:
            target_memory = _resolve_target_memory(user_id, target_memory_id)
            if not target_memory and memory_type in ALLOWED_MEMORY_TYPES and content:
                target_memory = _find_duplicate_memory(active_memories, memory_type, content)
            if target_memory and deactivate_user_memory(user_id, str(target_memory["memory_id"])):
                _safe_delete_memory_embedding(user_id, str(target_memory["memory_id"]))
                active_memories = [
                    memory
                    for memory in active_memories
                    if memory.get("memory_id") != target_memory["memory_id"]
                ]
                result.deactivated += 1
            else:
                result.ignored += 1
            continue

        if memory_type not in ALLOWED_MEMORY_TYPES or not content or confidence < MIN_MEMORY_CONFIDENCE:
            result.ignored += 1
            continue

        target_memory = _resolve_target_memory(user_id, target_memory_id)
        duplicate_memory = _find_duplicate_memory(active_memories, memory_type, content)

        if action == "update" and target_memory:
            if update_user_memory(
                user_id=user_id,
                memory_id=str(target_memory["memory_id"]),
                memory_type=memory_type,
                content=content,
                source_message_id=source_message_id,
                confidence=confidence,
                importance=importance,
                status="active",
            ):
                for memory in active_memories:
                    if memory.get("memory_id") == target_memory["memory_id"]:
                        memory["memory_type"] = memory_type
                        memory["content"] = content
                        memory["confidence"] = confidence
                        memory["importance"] = importance
                        memory["status"] = "active"
                await _safe_upsert_memory_embedding(user_id, str(target_memory["memory_id"]), content)
                result.updated += 1
            else:
                result.ignored += 1
            continue

        if duplicate_memory:
            if touch_user_memory(user_id, str(duplicate_memory["memory_id"]), source_message_id=source_message_id):
                result.updated += 1
            else:
                result.ignored += 1
            continue

        memory_id = add_user_memory(
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            source_message_id=source_message_id,
            confidence=confidence,
            importance=importance,
        )
        await _safe_upsert_memory_embedding(user_id, memory_id, content)
        active_memories.append({
            "memory_id": memory_id,
            "memory_type": memory_type,
            "content": content,
            "source_message_id": source_message_id,
            "confidence": confidence,
            "importance": importance,
            "status": "active",
        })
        result.created += 1

    logger.info(
        "Memory extraction finished for user_id=%s created=%s updated=%s deactivated=%s ignored=%s",
        user_id,
        result.created,
        result.updated,
        result.deactivated,
        result.ignored,
    )
    return result


async def _run_memory_extraction_job(
    user_id: str,
    user_message: str,
    assistant_reply: str,
    source_message_id: Optional[int] = None,
):
    """后台执行长期记忆抽取；异常在这里消化，避免影响主对话链路。"""
    try:
        result = await extract_and_store_memories(
            user_id=user_id,
            user_message=user_message,
            assistant_reply=assistant_reply,
            source_message_id=source_message_id,
        )
        logger.info(
            "Background memory extraction done for user_id=%s created=%s updated=%s deactivated=%s ignored=%s",
            user_id,
            result.created,
            result.updated,
            result.deactivated,
            result.ignored,
        )
    except Exception:
        logger.exception("Background memory extraction failed for user_id=%s", user_id)


def schedule_memory_extraction(
    user_id: str,
    user_message: str,
    assistant_reply: str,
    source_message_id: Optional[int] = None,
) -> MemoryGateResult:
    """先做规则门控，命中后把记忆抽取丢进事件循环后台任务。"""
    gate_result = should_extract_memory(user_message)
    if not gate_result.should_extract:
        logger.info("Memory extraction skipped for user_id=%s reason=%s", user_id, gate_result.reason)
        return gate_result

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Memory extraction skipped for user_id=%s reason=no_running_loop", user_id)
        return MemoryGateResult(False, "no_running_loop")

    # asyncio 只保留弱引用；这里用集合持有任务，完成后自动移除。
    task = loop.create_task(
        _run_memory_extraction_job(
            user_id=user_id,
            user_message=user_message,
            assistant_reply=assistant_reply,
            source_message_id=source_message_id,
        )
    )
    _BACKGROUND_MEMORY_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_MEMORY_TASKS.discard)
    logger.info("Memory extraction scheduled for user_id=%s reason=%s", user_id, gate_result.reason)
    return gate_result

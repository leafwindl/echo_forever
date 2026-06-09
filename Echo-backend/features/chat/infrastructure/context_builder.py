import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from features.memory.public import list_memory_embedding_records, retrieve_relevant_memories
from repositories.conversation_repository import get_conversation_summary
from repositories.memory_repository import list_user_memories
from repositories.message_repository import get_history
from shared.config import settings

logger = logging.getLogger(__name__)

MAX_ROUNDS = 10
MAX_HISTORY_MESSAGES = MAX_ROUNDS * 2
MAX_LONG_TERM_MEMORIES = 8


@dataclass
class ChatContext:
    messages: List[Dict[str, str]]
    history_messages: List[Dict[str, str]]
    conversation_summary: str = ""
    long_term_memories: List[Dict[str, object]] = field(default_factory=list)
    memory_retrieval_mode: str = "none"


def _format_long_term_memories(memories: List[Dict[str, object]]) -> str:
    lines = []
    for memory in memories:
        memory_type = memory.get("memory_type", "memory")
        content = str(memory.get("content", "")).strip()
        if content:
            score = memory.get("similarity_score")
            score_text = f" score={float(score):.3f}" if isinstance(score, (int, float)) else ""
            lines.append(f"- [{memory_type}{score_text}] {content}")
    return "\n".join(lines)


async def _load_long_term_memories(user_id: str, user_message: str) -> tuple[List[Dict[str, object]], str]:
    has_vector_records = bool(list_memory_embedding_records(user_id, embedding_model=settings.embedding_model))
    try:
        relevant_memories = await retrieve_relevant_memories(
            user_id=user_id,
            query=user_message,
            top_k=settings.memory_vector_top_k,
            score_threshold=settings.memory_vector_score_threshold,
        )
    except Exception as exc:
        logger.warning("Vector memory retrieval unavailable for user_id=%s: %s", user_id, exc)
        relevant_memories = []
        has_vector_records = False

    if relevant_memories:
        return relevant_memories, "vector"

    if has_vector_records:
        return [], "vector_empty"

    return (
        list_user_memories(user_id, status="active", limit=MAX_LONG_TERM_MEMORIES),
        "fallback_importance",
    )


async def build_chat_context(
    user_id: str,
    user_message: str,
    conversation_id: Optional[str] = None,
) -> ChatContext:
    long_term_memories, memory_retrieval_mode = await _load_long_term_memories(user_id, user_message)
    summary_text = ""
    summary_message_id = 0
    if conversation_id:
        summary_state = get_conversation_summary(user_id, conversation_id)
        summary_text = str(summary_state["summary"])
        summary_message_id = int(summary_state["summary_message_id"])

    history = get_history(
        user_id,
        limit=MAX_HISTORY_MESSAGES,
        conversation_id=conversation_id,
        after_message_id=summary_message_id,
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": settings.system_prompt}]
    if long_term_memories:
        messages.append({
            "role": "system",
            "content": "用户长期记忆：\n" + _format_long_term_memories(long_term_memories),
        })
    if summary_text:
        messages.append({
            "role": "system",
            "content": f"当前会话摘要：\n{summary_text}",
        })
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    return ChatContext(
        messages=messages,
        history_messages=history,
        conversation_summary=summary_text,
        long_term_memories=long_term_memories,
        memory_retrieval_mode=memory_retrieval_mode,
    )

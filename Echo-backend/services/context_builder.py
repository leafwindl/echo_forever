import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import settings
from services.memory import get_conversation_summary, get_history, list_user_memories
from services.vector_store import list_memory_embedding_records, retrieve_relevant_memories

logger = logging.getLogger(__name__)

# 统一控制短期上下文窗口：1 轮 = user 1 条 + assistant 1 条。
MAX_ROUNDS = 10
MAX_HISTORY_MESSAGES = MAX_ROUNDS * 2
MAX_LONG_TERM_MEMORIES = 8


@dataclass
class ChatContext:
    """发给大模型的一次完整上下文。

    Context Builder 是唯一负责“模型能看到什么”的地方：
    系统 Prompt、长期记忆、会话摘要、最近历史和当前用户消息都在这里组装。
    """

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
    """优先用向量检索召回相关记忆；没有向量时回退到重要度列表。"""
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
        # 已经有向量但本轮没有相关命中时，不再塞入无关长期记忆。
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
    """构建当前轮对话上下文。

    运行顺序：
    1. 读取用户长期记忆。
    2. 读取当前会话摘要。
    3. 读取摘要边界之后的短期历史。
    4. 按稳定顺序拼装最终 messages。
    """
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
        # 长期记忆来自用户明确表达或确认的信息，跨会话生效；不要把普通聊天原文全量塞进来。
        messages.append({
            "role": "system",
            "content": "用户长期记忆：\n" + _format_long_term_memories(long_term_memories),
        })
    if summary_text:
        # 摘要作为压缩上下文注入，帮助模型理解早期话题，同时避免塞入全部原始历史。
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

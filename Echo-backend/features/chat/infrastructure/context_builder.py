import logging
from dataclasses import dataclass, field

from shared.config import settings

from features.assistant_persona.public import get_assistant_persona
from features.chat.domain.dialogue_style import should_pause_followup_questions
from features.chat.infrastructure import postgres_repositories
from features.chat.infrastructure.prompt_renderer import (
    render_prompt_layers,
    render_turn_focus_guidance,
)
from features.memory.public import (
    list_memories,
    list_memory_embedding_records,
    retrieve_relevant_memories,
)
from features.persona.public import get_persona
from features.relationship.public import get_relationship_context

logger = logging.getLogger(__name__)

MAX_ROUNDS = 10
MAX_HISTORY_MESSAGES = MAX_ROUNDS * 2
MAX_LONG_TERM_MEMORIES = 8


@dataclass
class ChatContext:
    messages: list[dict[str, str]]
    history_messages: list[dict[str, str]]
    conversation_summary: str = ""
    long_term_memories: list[dict[str, object]] = field(default_factory=list)
    memory_retrieval_mode: str = "none"
    pause_followup_questions: bool = False


def _list_active_memories_for_context(user_id: str) -> list[dict[str, object]]:
    result = list_memories(user_id=user_id, memory_status="active", limit=MAX_LONG_TERM_MEMORIES)
    return [
        {
            "memory_id": memory.memory_id,
            "memory_type": memory.memory_type,
            "content": memory.content,
            "importance": memory.importance.value,
            "updated_at": memory.updated_at,
        }
        for memory in result.memories
    ]


async def _load_long_term_memories(
    user_id: str,
    user_message: str,
) -> tuple[list[dict[str, object]], str]:
    has_vector_records = bool(
        list_memory_embedding_records(user_id, embedding_model=settings.embedding_model)
    )
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
        _list_active_memories_for_context(user_id),
        "fallback_importance",
    )


async def build_chat_context(
    user_id: str,
    user_message: str,
    conversation_id: str | None = None,
    conversation_mode: str = "chat",
) -> ChatContext:
    long_term_memories, memory_retrieval_mode = await _load_long_term_memories(
        user_id,
        user_message,
    )
    summary_text = ""
    summary_message_id = 0
    if conversation_id:
        summary_state = postgres_repositories.get_conversation_summary(user_id, conversation_id)
        summary_text = str(summary_state["summary"])
        summary_message_id = int(summary_state["summary_message_id"])

    history = postgres_repositories.get_history(
        user_id,
        limit=MAX_HISTORY_MESSAGES,
        conversation_id=conversation_id,
        after_message_id=summary_message_id,
    )
    pause_followup_questions = should_pause_followup_questions(history, user_message)

    try:
        persona = get_persona(user_id)
    except Exception:
        logger.warning("Persona loading unavailable", exc_info=True)
        persona = None

    assistant_persona = get_assistant_persona(settings.assistant_persona_version)
    try:
        relationship = get_relationship_context(
            user_id=user_id,
            user_message=user_message,
            relationship_pace=(
                persona.relationship_pace if persona and persona.enabled else "natural"
            ),
            affection_style=(
                persona.affection_style if persona and persona.enabled else "contextual"
            ),
        )
    except Exception:
        logger.warning("Relationship state loading unavailable", exc_info=True)
        relationship = None

    messages: list[dict[str, str]] = render_prompt_layers(
        product_identity=settings.system_prompt,
        persona=persona,
        long_term_memories=long_term_memories,
        conversation_summary=summary_text,
        prompt_version=settings.prompt_version,
        persona_maximum_tokens=settings.persona_prompt_max_tokens,
        memory_maximum_tokens=settings.memory_prompt_max_tokens,
        summary_maximum_tokens=settings.summary_prompt_max_tokens,
        assistant_persona=assistant_persona,
        relationship=relationship,
        conversation_mode=conversation_mode,
    )
    messages.append(
        {
            "role": "system",
            "content": render_turn_focus_guidance(pause_followup_questions),
        }
    )
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    logger.info(
        "Chat context built prompt_version=%s assistant_persona_version=%s "
        "user_preferences_customized=%s relationship_stage=%s conversation_mode=%s memory_mode=%s",
        settings.prompt_version,
        assistant_persona.version,
        bool(persona and persona.is_customized and persona.enabled),
        relationship.state.stage if relationship else "new_fallback",
        conversation_mode,
        memory_retrieval_mode,
    )

    return ChatContext(
        messages=messages,
        history_messages=history,
        conversation_summary=summary_text,
        long_term_memories=long_term_memories,
        memory_retrieval_mode=memory_retrieval_mode,
        pause_followup_questions=pause_followup_questions,
    )

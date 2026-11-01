from dataclasses import dataclass

from features.chat.public import clear_chat_context
from features.memory.public import (
    cancel_pending_memory_extraction_jobs,
    clear_memories,
)
from features.persona.public import reset_persona_companionship_preferences
from features.proactive_chat.public import reset_user_proactive_state
from features.relationship.public import reset_relationship_state


@dataclass(frozen=True)
class ResetCompanionshipResult:
    deleted_messages: int
    reset_conversations: int
    cleared_memories: int
    cancelled_memory_jobs: int
    relationship_reset: bool
    proactive_reset: bool
    persona_reset: bool


class ResetCompanionship:
    """Clear one user's companionship history while keeping account and devices.

    This orchestration lives in the system feature because it is an account-level
    maintenance operation. It calls stable public APIs instead of owning another
    feature's tables or repositories.
    """

    def execute(self, user_id: str) -> ResetCompanionshipResult:
        clean_user_id = user_id.strip()
        if not clean_user_id:
            raise ValueError("Missing user_id")

        cancelled_jobs = cancel_pending_memory_extraction_jobs(clean_user_id)
        chat_result = clear_chat_context(clean_user_id)
        memory_result = clear_memories(clean_user_id)
        reset_relationship_state(clean_user_id)
        reset_user_proactive_state(clean_user_id)
        reset_persona_companionship_preferences(clean_user_id)
        return ResetCompanionshipResult(
            deleted_messages=chat_result.deleted_messages,
            reset_conversations=chat_result.reset_conversations,
            cleared_memories=memory_result.cleared_count,
            cancelled_memory_jobs=cancelled_jobs,
            relationship_reset=True,
            proactive_reset=True,
            persona_reset=True,
        )

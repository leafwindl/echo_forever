from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class UserProfile:
    """Echo 通过交流对用户的长期刻画；每次对话都注入，和事件记忆分开。"""

    user_id: str
    display_name: str = ""
    basics: dict[str, str] = field(default_factory=dict)
    routine: dict[str, str] = field(default_factory=dict)
    personality: str = ""
    communication: str = ""
    interests: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()
    notes: str = ""
    confidence: dict[str, str] = field(default_factory=dict)
    updated_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.display_name.strip(),
                self.basics,
                self.routine,
                self.personality.strip(),
                self.communication.strip(),
                self.interests,
                self.boundaries,
                self.notes.strip(),
            )
        )


PROFILE_TEXT_FIELDS = ("display_name", "personality", "communication", "notes")
PROFILE_DICT_FIELDS = ("basics", "routine", "confidence")
PROFILE_LIST_FIELDS = ("interests", "boundaries")
PROFILE_PATCH_FIELDS = PROFILE_TEXT_FIELDS + PROFILE_DICT_FIELDS + PROFILE_LIST_FIELDS

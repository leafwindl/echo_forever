from dataclasses import dataclass

PERSONA_SCHEMA_VERSION = 1
MAX_PREFERRED_NAME_CHARS = 40
MAX_ABOUT_USER_CHARS = 300
MAX_AVOID_TOPICS = 5
MAX_AVOID_TOPIC_CHARS = 40

VALID_REPLY_STYLES = frozenset({"natural", "concise", "lively"})
VALID_REPLY_LENGTHS = frozenset({"short", "balanced", "detailed"})
VALID_SUPPORT_MODES = frozenset({"comfort", "advice", "balanced"})
VALID_PROACTIVITY_LEVELS = frozenset({"quiet", "balanced", "active"})


class PersonaValidationError(ValueError):
    """个性化设置违反领域规则时抛出。"""


class PersonaOperationError(RuntimeError):
    """个性化设置持久化失败时抛出。"""


@dataclass(frozen=True)
class PersonaUpdate:
    """由用户提交、尚未绑定用户身份的个性化设置。"""

    preferred_name: str | None = None
    reply_style: str = "natural"
    reply_length: str = "balanced"
    support_mode: str = "balanced"
    proactivity: str = "balanced"
    avoid_topics: tuple[str, ...] = ()
    about_user: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class UserPersona:
    """可进入提示词装配的用户级 Persona 纯领域对象。"""

    user_id: str
    preferred_name: str | None = None
    reply_style: str = "natural"
    reply_length: str = "balanced"
    support_mode: str = "balanced"
    proactivity: str = "balanced"
    avoid_topics: tuple[str, ...] = ()
    about_user: str | None = None
    enabled: bool = True
    schema_version: int = PERSONA_SCHEMA_VERSION
    is_customized: bool = False
    created_at: str | None = None
    updated_at: str | None = None


def _normalize_optional_text(value: str | None, maximum: int, field_name: str) -> str | None:
    if value is None:
        return None
    clean_value = value.strip()
    if not clean_value:
        return None
    if len(clean_value) > maximum:
        raise PersonaValidationError(f"{field_name} exceeds {maximum} characters")
    return clean_value


def _normalize_choice(value: str, allowed: frozenset[str], field_name: str) -> str:
    clean_value = value.strip().lower()
    if clean_value not in allowed:
        raise PersonaValidationError(f"Invalid {field_name}")
    return clean_value


def _normalize_avoid_topics(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) > MAX_AVOID_TOPICS:
        raise PersonaValidationError(f"avoid_topics supports at most {MAX_AVOID_TOPICS} items")

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean_value = value.strip()
        if not clean_value:
            continue
        if len(clean_value) > MAX_AVOID_TOPIC_CHARS:
            raise PersonaValidationError(
                f"avoid_topics item exceeds {MAX_AVOID_TOPIC_CHARS} characters"
            )
        deduplication_key = clean_value.casefold()
        if deduplication_key in seen:
            continue
        seen.add(deduplication_key)
        normalized.append(clean_value)
    return tuple(normalized)


def build_user_persona(user_id: str, update: PersonaUpdate, *, is_customized: bool) -> UserPersona:
    """规范化用户输入并建立满足领域约束的 Persona。"""
    clean_user_id = user_id.strip()
    if not clean_user_id:
        raise PersonaValidationError("Missing user_id")

    return UserPersona(
        user_id=clean_user_id,
        preferred_name=_normalize_optional_text(
            update.preferred_name,
            MAX_PREFERRED_NAME_CHARS,
            "preferred_name",
        ),
        reply_style=_normalize_choice(update.reply_style, VALID_REPLY_STYLES, "reply_style"),
        reply_length=_normalize_choice(
            update.reply_length,
            VALID_REPLY_LENGTHS,
            "reply_length",
        ),
        support_mode=_normalize_choice(
            update.support_mode,
            VALID_SUPPORT_MODES,
            "support_mode",
        ),
        proactivity=_normalize_choice(
            update.proactivity,
            VALID_PROACTIVITY_LEVELS,
            "proactivity",
        ),
        avoid_topics=_normalize_avoid_topics(update.avoid_topics),
        about_user=_normalize_optional_text(
            update.about_user,
            MAX_ABOUT_USER_CHARS,
            "about_user",
        ),
        enabled=update.enabled,
        is_customized=is_customized,
    )


def default_user_persona(user_id: str) -> UserPersona:
    """返回未持久化的安全默认设置。"""
    return build_user_persona(user_id, PersonaUpdate(), is_customized=False)

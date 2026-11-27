"""冷启动画像引导的纯规则。

只做状态判断，不读写数据库、不渲染提示词。调用方把 UserProfile、
显式称呼、关系轮数、当前会话轮数和最近回复传进来即可。
"""

from __future__ import annotations

from dataclasses import dataclass

from features.user_profile.domain.entities import UserProfile

_BASIC_KEYS = ("职业", "城市", "年龄段")
_ROUTINE_KEYS = ("睡觉", "上班", "上课")
_REFUSAL_MARKER = "不采集个人资料"
_MAX_COLLECTING_TURNS = 8
_TASK_KEYWORDS = ("帮我", "请", "写", "查", "做", "修", "部署", "怎么", "为什么")
_FIELD_TERMS = {
    "称呼": ("称呼", "叫你", "怎么叫"),
    "职业": ("职业", "做什么", "工作", "上班", "上学"),
    "作息": ("作息", "睡觉", "几点睡"),
    "兴趣": ("兴趣", "喜欢什么", "平时喜欢"),
}


@dataclass(frozen=True)
class ProfileOnboardingState:
    phase: str  # collecting / paused / done
    known: tuple[str, ...]
    missing: tuple[str, ...]
    ask_allowed: bool
    reason: str


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _has_any(mapping: dict[str, str], keys: tuple[str, ...]) -> bool:
    return any(_clean(mapping.get(key)) for key in keys)


def _known_labels(
    profile: UserProfile | None,
    preferred_name: str | None,
) -> tuple[str, ...]:
    labels: list[str] = []
    display_name = _clean(profile.display_name) if profile else ""
    basics = dict(profile.basics) if profile else {}
    routine = dict(profile.routine) if profile else {}
    interests = tuple(profile.interests) if profile else ()
    if display_name or _clean(preferred_name):
        labels.append("称呼")
    if _clean(basics.get("职业")):
        labels.append("职业")
    if _has_any(routine, _ROUTINE_KEYS):
        labels.append("作息")
    if interests:
        labels.append("兴趣")
    return tuple(labels)


def _missing_fields(
    profile: UserProfile | None,
    preferred_name: str | None,
) -> tuple[str, ...]:
    display_name = _clean(profile.display_name) if profile else ""
    basics = dict(profile.basics) if profile else {}
    routine = dict(profile.routine) if profile else {}
    interests = tuple(profile.interests) if profile else ()
    missing: list[str] = []
    if not display_name and not _clean(preferred_name):
        missing.append("称呼")
    if not _clean(basics.get("职业")):
        missing.append("职业")
    if not _has_any(routine, _ROUTINE_KEYS):
        missing.append("作息")
    if not interests:
        missing.append("兴趣")
    return tuple(missing[:2])


def _has_refused(profile: UserProfile | None) -> bool:
    if profile is None:
        return False
    return any(_clean(item) == _REFUSAL_MARKER for item in profile.boundaries)


def _is_task_like(message: str) -> bool:
    clean = message.strip()
    if len(clean) > 40:
        return True
    return any(keyword in clean for keyword in _TASK_KEYWORDS)


def _recently_asked(
    recent_assistant_texts: tuple[str, ...],
    missing: tuple[str, ...],
) -> bool:
    recent = " ".join(recent_assistant_texts[-2:])
    if not any(mark in recent for mark in ("？", "吗", "呢")):
        return False
    return any(
        term in recent
        for field in missing
        for term in _FIELD_TERMS.get(field, (field,))
    )


def evaluate_profile_onboarding(
    *,
    profile: UserProfile | None,
    preferred_name: str | None = None,
    interaction_turns: int = 0,
    stage: str = "new",
    current_conversation_user_turns: int = 0,
    current_message_text: str = "",
    recent_assistant_texts: tuple[str, ...] = (),
) -> ProfileOnboardingState:
    known = _known_labels(profile, preferred_name)
    missing = _missing_fields(profile, preferred_name)
    basics = dict(profile.basics) if profile else {}
    interests = tuple(profile.interests) if profile else ()
    display_name = _clean(profile.display_name) if profile else ""
    has_name = bool(display_name or _clean(preferred_name))

    if _has_refused(profile):
        return ProfileOnboardingState("done", known, (), False, "refused")
    if has_name and (basics or interests):
        return ProfileOnboardingState("done", known, (), False, "enough")
    if stage in {"familiar", "ambiguous", "lover", "beloved"}:
        return ProfileOnboardingState("done", known, (), False, "relationship_stage")
    if interaction_turns > _MAX_COLLECTING_TURNS:
        return ProfileOnboardingState("done", known, (), False, "too_many_turns")
    if current_conversation_user_turns > _MAX_COLLECTING_TURNS:
        return ProfileOnboardingState("paused", known, missing, False, "session_limit")

    if _is_task_like(current_message_text):
        return ProfileOnboardingState("paused", known, missing, False, "task_intent")
    if _recently_asked(recent_assistant_texts, missing):
        return ProfileOnboardingState("paused", known, missing, False, "recently_asked")
    if not missing:
        return ProfileOnboardingState("paused", known, (), False, "no_missing")

    return ProfileOnboardingState("collecting", known, missing, True, "collecting")

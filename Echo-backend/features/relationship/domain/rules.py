import re
from dataclasses import replace

from features.relationship.domain.entities import (
    RELATIONSHIP_STAGES,
    RelationshipContext,
    RelationshipProgress,
    RelationshipSignal,
    RelationshipState,
)


_BOUNDARY_PATTERN = re.compile(
    r"(?:别|不要|不许|不喜欢).{0,10}(?:叫我|称呼|这么亲密|暧昧|撒娇|宝贝|宝宝|亲爱的|昵称)"
    r"|(?:太亲密|太暧昧|越界了|别烦我|别这样说)"
)
_AFFECTION_WELCOME_PATTERN = re.compile(
    r"(?:可以|就|以后).{0,8}(?:叫我|称呼我).{0,12}(?:宝贝|宝宝|亲爱的|昵称|小\S{1,6})"
    r"|(?:我喜欢你|我想你|有你真好|我们是(?:好朋友|很好的朋友)|你真的很懂我)"
)
_POSITIVE_RELATION_PATTERN = re.compile(
    r"(?:谢谢你陪我|谢谢你听我说|你真好|你很懂我|(?:跟|和|与)你聊天.{0,8}(?:开心|舒服|轻松)|还好有你)"
)
_NEGATED_POSITIVE_PATTERN = re.compile(r"(?:不|没|并非|谈不上).{0,3}(?:开心|舒服|轻松)")
_CORRECTION_PATTERN = re.compile(
    r"(?:你没懂|你理解错|不是这个意思|别重复我的话|太冷漠|像机器人|人机味|别给建议)"
)
_WARM_TURN_PATTERN = re.compile(
    r"(?:哈哈|嘿嘿|开心|高兴|赢了|成功了|搞定了|太好了|好耶|笑死|有意思)"
)

_AFFECTION_THRESHOLDS = (
    ("beloved", 800),
    ("lover", 500),
    ("ambiguous", 300),
    ("familiar", 100),
)

_STAGE_ORDER = {"new": 0, "familiar": 1, "ambiguous": 2, "lover": 3, "beloved": 4}
_STAGE_REQUEST_TARGETS = {
    "familiar": "ambiguous",
    "ambiguous": "lover",
    "lover": "beloved",
}
_STAGE_REQUEST_MIN_AFFECTION = {
    "ambiguous": 300,
    "lover": 500,
    "beloved": 800,
}
_LEGACY_STAGE_MAP = {"trusted": "ambiguous", "close": "lover"}


def normalize_relationship_stage(stage: str) -> str:
    """把旧库的 trusted/close 迁到五阶段；未知值回落到初识。"""
    clean = stage.strip()
    clean = _LEGACY_STAGE_MAP.get(clean, clean)
    return clean if clean in _STAGE_ORDER else "new"


def detect_relationship_signals(user_message: str) -> tuple[RelationshipSignal, ...]:
    clean_message = user_message.strip()
    if not clean_message:
        return ()

    signals: list[RelationshipSignal] = []
    if _BOUNDARY_PATTERN.search(clean_message):
        signals.append(RelationshipSignal("affection_boundary"))
    elif _AFFECTION_WELCOME_PATTERN.search(clean_message):
        signals.append(RelationshipSignal("affection_welcomed", weight=5))

    if any(
        not _NEGATED_POSITIVE_PATTERN.search(match.group())
        for match in _POSITIVE_RELATION_PATTERN.finditer(clean_message)
    ):
        signals.append(RelationshipSignal("positive_relation", weight=3))
    if _CORRECTION_PATTERN.search(clean_message):
        signals.append(RelationshipSignal("interaction_correction"))
    return tuple(signals)


def resolve_relationship_stage(state: RelationshipState, relationship_pace: str = "natural") -> str:
    """阶段只看 affection；只升不降。pace 参数保留给旧调用，暂不参与阈值。"""
    del relationship_pace
    candidate = "new"
    for stage, minimum_affection in _AFFECTION_THRESHOLDS:
        if state.affection >= minimum_affection:
            candidate = stage
            break

    current = normalize_relationship_stage(state.stage)
    current_index = _STAGE_ORDER[current]
    candidate_index = _STAGE_ORDER[candidate]
    return RELATIONSHIP_STAGES[max(current_index, candidate_index)]


def next_requestable_stage(stage: str, affection: int) -> str:
    """初识→熟悉自动；其余三段达到阈值才允许发起请求。"""
    current = normalize_relationship_stage(stage)
    if current == "new":
        return ""
    target = _STAGE_REQUEST_TARGETS.get(current, "")
    if not target:
        return ""
    if affection < _STAGE_REQUEST_MIN_AFFECTION[target]:
        return ""
    return target


def infer_interaction_warmth(user_message: str) -> str:
    signals = detect_relationship_signals(user_message)
    signal_types = {signal.event_type for signal in signals}
    if "affection_boundary" in signal_types:
        return "reserved"
    negated_spans = [match.span() for match in _NEGATED_POSITIVE_PATTERN.finditer(user_message)]
    if any(
        not any(start <= match.start() < end for start, end in negated_spans)
        for match in _WARM_TURN_PATTERN.finditer(user_message)
    ):
        return "warm"
    return "normal"


def build_relationship_context(
    state: RelationshipState,
    user_message: str,
    relationship_pace: str,
    affection_style: str,
    *,
    stage_asset: str = "",
) -> RelationshipContext:
    signals = detect_relationship_signals(user_message)
    signal_types = {signal.event_type for signal in signals}
    permission = state.affection_permission
    if "affection_boundary" in signal_types:
        permission = "restrained"
    elif "affection_welcomed" in signal_types:
        permission = "welcomed"

    effective_affection_style = affection_style
    if permission == "restrained":
        effective_affection_style = "restrained"

    resolved_stage = resolve_relationship_stage(state, relationship_pace)
    resolved_state = replace(state, stage=resolved_stage, affection_permission=permission)
    return RelationshipContext(
        state=resolved_state,
        interaction_warmth=infer_interaction_warmth(user_message),
        effective_affection_style=effective_affection_style,
        stage_asset=stage_asset or resolved_stage,
    )


def advance_relationship_state(
    state: RelationshipState,
    *,
    observed_date: str,
    observed_at: str,
    shared_memory_count: int,
    user_message: str,
    relationship_pace: str,
) -> RelationshipProgress:
    signals = detect_relationship_signals(user_message)
    signal_types = {signal.event_type for signal in signals}
    active_days = state.active_days
    emitted_signals = list(signals)
    if state.last_interaction_date != observed_date:
        active_days += 1
        emitted_signals.append(RelationshipSignal("active_day", weight=5))

    affection_permission = state.affection_permission
    last_boundary_at = state.last_boundary_at
    if "affection_boundary" in signal_types:
        affection_permission = "restrained"
        last_boundary_at = observed_at
    elif "affection_welcomed" in signal_types:
        affection_permission = "welcomed"

    progressed = replace(
        state,
        interaction_turns=state.interaction_turns + 1,
        active_days=active_days,
        shared_memory_count=max(0, shared_memory_count),
        positive_signal_count=state.positive_signal_count
        + int("positive_relation" in signal_types),
        explicit_relation_signal_count=state.explicit_relation_signal_count
        + int("affection_welcomed" in signal_types),
        boundary_signal_count=state.boundary_signal_count
        + int("affection_boundary" in signal_types),
        affection_permission=affection_permission,
        last_interaction_date=observed_date,
        last_interaction_at=observed_at,
        last_boundary_at=last_boundary_at,
        updated_at=observed_at,
    )
    resolved_stage = resolve_relationship_stage(progressed, relationship_pace)
    stage_changed = resolved_stage != state.stage
    if stage_changed:
        emitted_signals.append(RelationshipSignal("stage_changed"))
        progressed = replace(
            progressed,
            stage=resolved_stage,
            stage_updated_at=observed_at,
        )
    return RelationshipProgress(
        state=progressed,
        signals=tuple(emitted_signals),
        stage_changed=stage_changed,
    )


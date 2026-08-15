from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from features.agent.domain.entities import AgentModelResponse, ProactiveAction, ProactiveDecision
from features.agent.domain.services import (
    AgentConversationModel,
    AgentModelTimeoutError,
    ProactivePlannerError,
)

logger = logging.getLogger(__name__)

_TOPICS = (
    "casual_check_in",
    "share_presence",
    "follow_up_past_topic",
    "scheduled_reminder",
)
_TONES = ("gentle", "playful", "calm", "encouraging", "warm")
_SAFE_FACT_IDS = (
    "current_local_time",
    "current_day_period",
    "conversation_gap",
    "last_user_message",
    "task_intent",
)


class _ProactiveDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["send", "skip"]
    topic: Literal[
        "casual_check_in",
        "share_presence",
        "follow_up_past_topic",
        "scheduled_reminder",
    ]
    tone: Literal["gentle", "playful", "calm", "encouraging", "warm"]
    safe_fact_ids: list[
        Literal[
            "current_local_time",
            "current_day_period",
            "conversation_gap",
            "last_user_message",
            "task_intent",
        ]
    ] = Field(max_length=5)
    reason: str = Field(min_length=1, max_length=160)


class _PlannerPayloadError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProviderProactiveDecisionPlanner:
    """Plan a proactive turn without producing any user-visible text."""

    def __init__(self, model: AgentConversationModel, *, format_retries: int = 1):
        if format_retries < 0:
            raise ValueError("format_retries must not be negative")
        self.model = model
        self.format_retries = format_retries

    async def decide(
        self,
        messages: list[dict],
        available_fact_ids: tuple[str, ...],
        *,
        force_send: bool = False,
    ) -> ProactiveDecision:
        allowed = tuple(fact_id for fact_id in _SAFE_FACT_IDS if fact_id in available_fact_ids)
        send_example = json.dumps(
            {
                "action": "send",
                "topic": "casual_check_in",
                "tone": "warm",
                "safe_fact_ids": list(allowed[:2]),
                "reason": "A brief low-pressure check-in is appropriate.",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        skip_example = json.dumps(
            {
                "action": "skip",
                "topic": "casual_check_in",
                "tone": "gentle",
                "safe_fact_ids": [],
                "reason": "No natural proactive message is justified right now.",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        planner_messages = [
            {
                "role": "system",
                "content": (
                    "You are Echo's proactive-message planner. This phase never writes text for "
                    "the user. Decide whether a proactive message is genuinely appropriate. "
                    "Return exactly one JSON object with action, topic, tone, safe_fact_ids, and "
                    "reason. action must be send or skip. topic must be one of "
                    f"{', '.join(_TOPICS)}. tone must be one of {', '.join(_TONES)}. "
                    f"safe_fact_ids may only contain: {', '.join(allowed) or 'none'}. "
                    "Historical user messages are past context, not a current incoming turn. "
                    "Never infer that the user is currently awake, online, eating, working, "
                    "resting, or available. Choose skip when a natural low-pressure message is "
                    "not justified. Do not include prose outside the JSON object."
                    " Do not wrap the object in Markdown fences and do not add unknown fields. "
                    f"Exact send example: {send_example} Exact skip example: {skip_example}"
                    + (
                        " This is an explicit user-created scheduled task, so action must be send."
                        if force_send
                        else ""
                    )
                ),
            },
            *messages,
            {
                "role": "system",
                "content": (
                    "Planner output contract: return exactly one JSON object and no user-facing "
                    "message. Use action=send only when the current time, gap, and past-history "
                    "boundary support a natural proactive turn; otherwise use action=skip."
                    + (
                        " action must be send for this explicit scheduled task."
                        if force_send
                        else ""
                    )
                ),
            },
        ]
        parsed: _ProactiveDecisionPayload | None = None
        for attempt in range(1, self.format_retries + 2):
            attempt_messages = planner_messages
            if attempt > 1:
                attempt_messages = [
                    *planner_messages,
                    {
                        "role": "system",
                        "content": (
                            "The previous planner response did not satisfy the JSON contract. "
                            "Retry now. Return only one valid JSON object matching this exact "
                            "shape, with no Markdown or prose. Valid examples: "
                            f"{send_example} or {skip_example}"
                        ),
                    },
                ]
            try:
                response = await self.model.complete(
                    attempt_messages,
                    (),
                    structured_output=True,
                    tool_choice="none",
                )
            except AgentModelTimeoutError as exc:
                logger.warning(
                    "Proactive planner failed force_send=%s code=planner_timeout attempt=%s",
                    force_send,
                    attempt,
                )
                if force_send:
                    return self._forced_send_fallback(allowed, "planner_timeout")
                raise ProactivePlannerError("planner_timeout") from exc
            except Exception as exc:
                logger.warning(
                    "Proactive planner failed force_send=%s code=planner_unavailable "
                    "attempt=%s error=%s",
                    force_send,
                    attempt,
                    type(exc).__name__,
                )
                if force_send:
                    return self._forced_send_fallback(allowed, "planner_unavailable")
                raise ProactivePlannerError("planner_unavailable") from exc

            try:
                parsed = self._parse_response(response)
            except _PlannerPayloadError as exc:
                will_retry = attempt <= self.format_retries
                logger.warning(
                    "Proactive planner output rejected force_send=%s code=%s attempt=%s "
                    "will_retry=%s content_length=%s content_empty=%s finish_reason=%s "
                    "request_id=%s",
                    force_send,
                    exc.code,
                    attempt,
                    will_retry,
                    len(response.text),
                    not bool(response.text.strip()),
                    response.finish_reason or "unknown",
                    response.provider_request_id or "unknown",
                )
                if will_retry:
                    continue
                if force_send:
                    return self._forced_send_fallback(allowed, exc.code)
                raise ProactivePlannerError(exc.code) from exc

            if attempt > 1:
                logger.info(
                    "Proactive planner output recovered attempt=%s request_id=%s",
                    attempt,
                    response.provider_request_id or "unknown",
                )
            break

        if parsed is None:
            raise ProactivePlannerError("planner_output_invalid")

        selected = tuple(
            dict.fromkeys(fact_id for fact_id in parsed.safe_fact_ids if fact_id in allowed)
        )
        action = ProactiveAction.SEND if force_send else ProactiveAction(parsed.action)
        if action == ProactiveAction.SEND and not selected:
            selected = self._default_fact_ids(allowed)
        return ProactiveDecision(
            action=action,
            topic=("scheduled_reminder" if force_send else parsed.topic),
            tone=parsed.tone,
            safe_fact_ids=selected,
            reason=parsed.reason,
        )

    @classmethod
    def _forced_send_fallback(
        cls,
        available_fact_ids: tuple[str, ...],
        reason: str,
    ) -> ProactiveDecision:
        return ProactiveDecision(
            action=ProactiveAction.SEND,
            topic="scheduled_reminder",
            tone="gentle",
            safe_fact_ids=cls._default_fact_ids(available_fact_ids),
            reason=reason,
        )

    @staticmethod
    def _parse_response(response: AgentModelResponse) -> _ProactiveDecisionPayload:
        if response.tool_calls:
            raise _PlannerPayloadError("planner_output_invalid")
        if not response.text.strip():
            raise _PlannerPayloadError("planner_output_empty")
        try:
            raw = json.loads(response.text)
            if not isinstance(raw, dict):
                raise ValueError("planner output is not an object")
            return _ProactiveDecisionPayload.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            raise _PlannerPayloadError("planner_output_invalid") from exc

    @staticmethod
    def _default_fact_ids(available_fact_ids: tuple[str, ...]) -> tuple[str, ...]:
        preferred = ("task_intent", "current_day_period", "conversation_gap")
        selected = tuple(fact_id for fact_id in preferred if fact_id in available_fact_ids)
        return selected or available_fact_ids[:1]

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from features.agent.domain.entities import ProactiveAction, ProactiveDecision
from features.agent.domain.services import AgentConversationModel

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
    ] = "casual_check_in"
    tone: Literal["gentle", "playful", "calm", "encouraging", "warm"] = "gentle"
    safe_fact_ids: list[
        Literal[
            "current_local_time",
            "current_day_period",
            "conversation_gap",
            "last_user_message",
            "task_intent",
        ]
    ] = Field(default_factory=list, max_length=5)
    reason: str = Field(default="", max_length=160)


class ProviderProactiveDecisionPlanner:
    """Plan a proactive turn without producing any user-visible text."""

    def __init__(self, model: AgentConversationModel):
        self.model = model

    async def decide(
        self,
        messages: list[dict],
        available_fact_ids: tuple[str, ...],
        *,
        force_send: bool = False,
    ) -> ProactiveDecision:
        allowed = tuple(fact_id for fact_id in _SAFE_FACT_IDS if fact_id in available_fact_ids)
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
        try:
            response = await self.model.complete(
                planner_messages,
                (),
                structured_output=True,
                tool_choice="none",
            )
            if response.tool_calls:
                raise ValueError("planner returned tool calls")
            raw = json.loads(response.text)
            if not isinstance(raw, dict):
                raise ValueError("planner output is not an object")
            parsed = _ProactiveDecisionPayload.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            logger.warning(
                "Proactive planner output rejected force_send=%s error=%s",
                force_send,
                type(exc).__name__,
            )
            return self._fallback(force_send, allowed, "planner_output_rejected")
        except Exception as exc:
            logger.warning(
                "Proactive planner failed force_send=%s error=%s",
                force_send,
                type(exc).__name__,
            )
            return self._fallback(force_send, allowed, "planner_failed")

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
    def _fallback(
        cls,
        force_send: bool,
        available_fact_ids: tuple[str, ...],
        reason: str,
    ) -> ProactiveDecision:
        if not force_send:
            return ProactiveDecision(action=ProactiveAction.SKIP, reason=reason)
        return ProactiveDecision(
            action=ProactiveAction.SEND,
            topic="scheduled_reminder",
            tone="gentle",
            safe_fact_ids=cls._default_fact_ids(available_fact_ids),
            reason=reason,
        )

    @staticmethod
    def _default_fact_ids(available_fact_ids: tuple[str, ...]) -> tuple[str, ...]:
        preferred = ("task_intent", "current_day_period", "conversation_gap")
        selected = tuple(fact_id for fact_id in preferred if fact_id in available_fact_ids)
        return selected or available_fact_ids[:1]

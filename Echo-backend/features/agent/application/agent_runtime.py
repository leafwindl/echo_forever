"""一次 Agent turn 的运行入口。

runtime 只做三件事：装配输入（policy）、驱动循环（loop）、记账并翻译结果
（repository + AgentTurnResult）。它不认识具体工具，也不认识具体模式——模式
差异全部落在 `TurnProfile` 里。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from features.agent.application.model_loop import ModelToolLoop
from features.agent.domain.entities import AgentRunStatus, AgentTurnResult
from features.agent.domain.repositories import AgentRunRepository
from features.agent.domain.turn_policy import TurnPolicy


@dataclass(frozen=True)
class AgentTurn:
    user_id: str
    message: str
    messages: list[dict]
    conversation_id: str | None = None
    conversation_mode: str = "chat"
    sticker_intent: str = ""
    tools_enabled: bool = True
    allowed_tool_names: tuple[str, ...] | None = None
    tool_call_limit: int | None = None
    call_route_instruction: str = ""
    on_text_delta: Callable[[str], Awaitable[None]] | None = None
    on_progress_text: Callable[[str], Awaitable[None]] | None = None


class AgentTurnRuntime:
    def __init__(
        self,
        *,
        repository: AgentRunRepository,
        loop: ModelToolLoop,
        policy: TurnPolicy,
        run_timeout_seconds: int,
    ):
        self.repository = repository
        self.loop = loop
        self.policy = policy
        self.run_timeout_seconds = run_timeout_seconds

    async def run(self, turn: AgentTurn) -> AgentTurnResult:
        profile = self.policy.profile(
            conversation_mode=turn.conversation_mode,
            tool_call_limit=turn.tool_call_limit,
        )
        run_id = self.repository.start(
            turn.user_id,
            turn.message,
            turn.conversation_mode,
            profile.max_steps,
        )
        messages = self.policy.initial_messages(
            messages=turn.messages,
            conversation_mode=turn.conversation_mode,
            message=turn.message,
            sticker_intent=turn.sticker_intent,
            call_route_instruction=turn.call_route_instruction,
        )
        deadline = asyncio.get_running_loop().time() + self.run_timeout_seconds
        outcome = await self.loop.run(
            user_id=turn.user_id,
            message=turn.message,
            conversation_id=turn.conversation_id,
            conversation_mode=turn.conversation_mode,
            profile=profile,
            messages=messages,
            run_id=run_id,
            deadline=deadline,
            tools_enabled=turn.tools_enabled,
            allowed_tool_names=turn.allowed_tool_names,
            on_text_delta=turn.on_text_delta,
            on_progress_text=turn.on_progress_text,
        )
        self.repository.finish(
            run_id,
            outcome.model_steps + outcome.tool_calls,
            outcome.error_code,
        )
        return AgentTurnResult(
            status=(
                AgentRunStatus.COMPLETED if outcome.completed else AgentRunStatus.FAILED
            ),
            reply_text=outcome.text,
            sources=outcome.sources,
            content_parts=outcome.content_parts,
            tool_results=outcome.tool_results,
            run_id=run_id,
            model_steps=outcome.model_steps,
            error_code=outcome.error_code,
            reply_segments=outcome.segments,
            sticker_placement=outcome.sticker_placement,
        )

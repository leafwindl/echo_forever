"""统一 Agent 回路的兼容入口。

阶段 4 起，真正的执行在 `AgentTurnRuntime`；这里保留原来的构造签名和
`execute` 签名，避免调用方与测试跟着改。新代码应直接依赖 runtime。

兼容壳只做一件事：把参数翻译成 `AgentTurn`，其余交给 runtime。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from features.agent.application.agent_runtime import AgentTurn, AgentTurnRuntime
from features.agent.application.delivery_gate import DeliveryGate
from features.agent.application.execute_tool import ToolExecutor
from features.agent.application.model_loop import ModelToolLoop
from features.agent.application.turn_fallbacks import TurnFallbacks
from features.agent.domain.entities import AgentTurnResult
from features.agent.domain.repositories import AgentRunRepository
from features.agent.domain.services import AgentConversationModel
from features.agent.domain.tools import ToolRegistry
from features.agent.domain.turn_policy import TurnPolicy


class OrchestrateChatWithAgent:
    def __init__(
        self,
        repository: AgentRunRepository,
        model: AgentConversationModel,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_steps: int,
        max_tool_calls: int,
        run_timeout_seconds: int,
        proactive_max_tool_calls: int = 5,
    ):
        policy = TurnPolicy(
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            proactive_max_tool_calls=proactive_max_tool_calls,
        )
        loop = ModelToolLoop(
            model=model,
            registry=registry,
            executor=executor,
            gate=DeliveryGate(),
            fallbacks=TurnFallbacks(),
            repository=repository,
            policy=policy,
        )
        self.runtime = AgentTurnRuntime(
            repository=repository,
            loop=loop,
            policy=policy,
            run_timeout_seconds=run_timeout_seconds,
        )

    async def execute(
        self,
        user_id: str,
        message: str,
        messages: list[dict],
        conversation_id: str | None = None,
        conversation_mode: str = "chat",
        sticker_intent: str = "",
        tools_enabled: bool = True,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
        on_progress_text: Callable[[str], Awaitable[None]] | None = None,
        allowed_tool_names: tuple[str, ...] | None = None,
        tool_call_limit: int | None = None,
        call_route_instruction: str = "",
        require_tool: bool = False,
    ) -> AgentTurnResult:
        return await self.runtime.run(
            AgentTurn(
                user_id=user_id,
                message=message,
                messages=messages,
                conversation_id=conversation_id,
                conversation_mode=conversation_mode,
                sticker_intent=sticker_intent,
                tools_enabled=tools_enabled,
                allowed_tool_names=allowed_tool_names,
                tool_call_limit=tool_call_limit,
                call_route_instruction=call_route_instruction,
                require_tool=require_tool,
                on_text_delta=on_text_delta,
                on_progress_text=on_progress_text,
            )
        )

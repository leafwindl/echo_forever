from __future__ import annotations

import json

from pydantic import BaseModel, Field

from features.agent.domain.entities import (
    AgentToolResult,
    AgentToolStatus,
    ToolSpecification,
)
from features.agent.domain.tools import ToolDefinition, ToolExecutionContext, ToolRegistry
from features.user_profile.public import update_user_profile


class UpdateUserProfileArguments(BaseModel):
    display_name: str | None = Field(default=None, description="称呼，例如“叶子”。")
    basics: dict[str, str] | None = Field(
        default=None, description="基本情况，键用中文：年龄/职业/城市。"
    )
    routine: dict[str, str] | None = Field(
        default=None, description="作息，键用中文：睡觉/上课/上班。"
    )
    personality: str | None = Field(default=None, description="性格观察，有依据才写。")
    communication: str | None = Field(default=None, description="沟通习惯。")
    interests: list[str] | None = Field(default=None, description="兴趣。")
    boundaries: list[str] | None = Field(default=None, description="不想聊的话题。")
    notes: str | None = Field(default=None, description="其他稳定事实。")
    confidence: dict[str, str] | None = Field(
        default=None, description="不确定的字段，键用中文。"
    )


def register_profile_tools(registry: ToolRegistry) -> None:
    async def update_handler(
        context: ToolExecutionContext,
        arguments: BaseModel,
    ) -> AgentToolResult:
        parsed = UpdateUserProfileArguments.model_validate(arguments)
        raw_patch = parsed.model_dump(exclude_none=True)
        patch = {key: value for key, value in raw_patch.items() if value}
        if not patch:
            return AgentToolResult(
                call_id="",
                tool_name="update_user_profile",
                status=AgentToolStatus.FAILED,
                data={"updated": []},
                safe_for_model="没有需要更新的内容。",
                error_code="empty_patch",
            )
        profile = update_user_profile(context.user_id, patch)
        payload = {
            "updated": sorted(patch.keys()),
            "profile_empty": profile.is_empty,
        }
        return AgentToolResult(
            call_id="",
            tool_name="update_user_profile",
            status=AgentToolStatus.COMPLETED,
            data=payload,
            safe_for_model=json.dumps(payload, ensure_ascii=False),
        )

    registry.register(
        ToolDefinition(
            specification=ToolSpecification(
                name="update_user_profile",
                description=(
                    "更新你对用户的长期了解。用户明确说了自己的事（工作、作息、年龄、"
                    "城市、称呼、兴趣、不想聊什么），或你问出来他回答了，就调用。"
                    "只写他明确说过的，不写推测；一次只写变化的部分。"
                ),
                timeout_seconds=5,
                allowed_modes=("chat", "proactive"),
                max_calls_per_turn=1,
                max_successful_calls_per_turn=1,
            ),
            arguments_model=UpdateUserProfileArguments,
            handler=update_handler,
        )
    )

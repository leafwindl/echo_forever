from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from shared.interface.dependencies import CurrentUser, get_current_user

from features.proactive_chat.infrastructure.postgres_repository import (
    PostgresProactiveChatRepository,
)
from features.proactive_chat.interface.schemas import (
    ChatScheduleCreateRequest,
    ChatScheduleListResponse,
    ChatScheduleResponse,
    ChatScheduleUpdateRequest,
    ProactivePauseRequest,
    ProactivePreferencesRequest,
    ProactivePreferencesResponse,
)

router = APIRouter(prefix="/proactive", tags=["proactive-chat"])
repository = PostgresProactiveChatRepository()
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _preferences_response(value) -> ProactivePreferencesResponse:
    return ProactivePreferencesResponse(
        enabled=value.enabled,
        allow_echo_scheduling=value.allow_echo_scheduling,
        allow_spontaneous_chat=value.allow_spontaneous_chat,
        timezone=value.timezone,
        quiet_start=value.quiet_start,
        quiet_end=value.quiet_end,
        explicit_reminder_quiet_policy=value.explicit_reminder_quiet_policy,
        notification_preview=value.notification_preview,
        paused_until=value.paused_until,
        pause_indefinite=value.pause_indefinite,
    )


def _schedule_response(value) -> ChatScheduleResponse:
    return ChatScheduleResponse(
        schedule_id=value.schedule_id,
        created_by=value.created_by,
        schedule_type=value.schedule_type,
        intent=value.intent,
        user_visible_label=value.user_visible_label,
        timezone=value.timezone,
        next_run_at=value.next_run_at,
        recurrence_rule=value.recurrence_rule,
        status=value.status,
        run_count=value.run_count,
        max_runs=value.max_runs,
        last_run_at=value.last_run_at,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


@router.get("/preferences", response_model=ProactivePreferencesResponse)
def get_preferences(current_user: CurrentUserDependency):
    return _preferences_response(repository.get_preferences(current_user.user_id))


@router.put("/preferences", response_model=ProactivePreferencesResponse)
def update_preferences(request: ProactivePreferencesRequest, current_user: CurrentUserDependency):
    try:
        result = repository.save_preferences(current_user.user_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _preferences_response(result)


@router.post("/pause", response_model=ProactivePreferencesResponse)
def pause_spontaneous(request: ProactivePauseRequest, current_user: CurrentUserDependency):
    until = None
    if not request.indefinite:
        until = datetime.now(UTC) + timedelta(days=request.days or 2)
    value = repository.pause_spontaneous(
        current_user.user_id,
        until=until,
        indefinite=request.indefinite,
    )
    return _preferences_response(value)


@router.post("/resume", response_model=ProactivePreferencesResponse)
def resume_spontaneous(current_user: CurrentUserDependency):
    return _preferences_response(repository.resume_spontaneous(current_user.user_id))


@router.get("/schedules", response_model=ChatScheduleListResponse)
def list_schedules(current_user: CurrentUserDependency):
    return ChatScheduleListResponse(
        items=[_schedule_response(item) for item in repository.list_schedules(current_user.user_id)]
    )


@router.post("/schedules", response_model=ChatScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(request: ChatScheduleCreateRequest, current_user: CurrentUserDependency):
    try:
        result = repository.create_schedule(
            user_id=current_user.user_id,
            conversation_id=None,
            created_by="user_request",
            **request.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _schedule_response(result)


@router.patch("/schedules/{schedule_id}", response_model=ChatScheduleResponse)
@router.put("/schedules/{schedule_id}", response_model=ChatScheduleResponse)
def update_schedule(
    schedule_id: str,
    request: ChatScheduleUpdateRequest,
    current_user: CurrentUserDependency,
):
    try:
        result = repository.update_schedule(
            current_user.user_id,
            schedule_id,
            **request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")
    return _schedule_response(result)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: str, current_user: CurrentUserDependency):
    if not repository.delete_schedule(current_user.user_id, schedule_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from shared.interface.dependencies import CurrentUser, get_current_user

from features.chat.public import deliver_external_assistant_message
from features.study_focus.domain.entities import StudyFocusSession
from features.study_focus.infrastructure.postgres_repository import (
    PostgresStudyFocusRepository,
)
from features.study_focus.interface.schemas import (
    StudyFocusCreateRequest,
    StudyFocusListResponse,
    StudyFocusResponse,
    StudyFocusUpdateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/study-focus", tags=["study-focus"])
repository = PostgresStudyFocusRepository()
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _response(session: StudyFocusSession) -> StudyFocusResponse:
    return StudyFocusResponse(
        session_id=session.session_id,
        activity_type=session.activity_type,
        short_goal=session.short_goal,
        planned_duration_seconds=session.planned_duration_seconds,
        actual_duration_seconds=session.actual_duration_seconds,
        status=session.status,
        started_at=session.started_at,
        timezone=session.timezone,
        ended_at=session.ended_at,
        completion_message_id=session.completion_message_id,
    )


@router.post("/sessions", response_model=StudyFocusResponse, status_code=status.HTTP_201_CREATED)
def create_session(request: StudyFocusCreateRequest, current_user: CurrentUserDependency):
    try:
        session = repository.create_session(user_id=current_user.user_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _response(session)


@router.patch("/sessions/{session_id}", response_model=StudyFocusResponse)
@router.put("/sessions/{session_id}", response_model=StudyFocusResponse)
async def update_session(
    session_id: str,
    request: StudyFocusUpdateRequest,
    current_user: CurrentUserDependency,
):
    try:
        session = repository.update_session(
            user_id=current_user.user_id,
            session_id=session_id,
            **request.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    if session.status in {"completed", "ended_early"} and session.completion_message_id is None:
        try:
            source = (
                "focus_completion"
                if session.status == "completed"
                else "focus_ended_early"
            )
            delivery = await deliver_external_assistant_message(
                user_id=current_user.user_id,
                content=_completion_message(session),
                idempotency_key=f"{source}:{session.session_id}",
                source=source,
            )
            session = repository.mark_completion_message(
                user_id=current_user.user_id,
                session_id=session.session_id,
                message_id=delivery.message.message_id,
            ) or session
        except Exception:
            logger.warning(
                "Study focus completion message failed session_id=%s",
                session.session_id,
                exc_info=True,
            )
    return _response(session)


@router.get("/sessions", response_model=StudyFocusListResponse)
def list_sessions(
    current_user: CurrentUserDependency,
    limit: int = Query(default=30, ge=1, le=100),
):
    sessions = repository.list_sessions(current_user.user_id, limit=limit)
    return StudyFocusListResponse(
        items=[_response(item) for item in sessions],
        total_actual_duration_seconds=sum(item.actual_duration_seconds for item in sessions),
    )


def _completion_message(session: StudyFocusSession) -> str:
    minutes, seconds = divmod(session.actual_duration_seconds, 60)
    duration = f"{minutes} 分钟" if seconds == 0 else f"{minutes} 分 {seconds} 秒"
    if session.status == "ended_early":
        return (
            f"你刚刚学习了 {duration}。是有其他事情要忙吗？先处理眼前的事，"
            "等你有空了，我们再一起继续。"
        )
    return f"辛苦了，这一轮 {duration}完成啦。先休息一下，今天也已经很努力了。"

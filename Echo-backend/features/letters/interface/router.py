from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from shared.interface.dependencies import CurrentUser, get_current_user

from features.letters.infrastructure.postgres_repository import PostgresLetterRepository
from features.letters.interface.schemas import (
    LetterListResponse,
    LetterPreferenceRequest,
    LetterPreferenceResponse,
    LetterResponse,
)

router = APIRouter(prefix="/letters", tags=["letters"])
repository = PostgresLetterRepository()


def _response(letter) -> LetterResponse:
    return LetterResponse(**vars(letter))


@router.get("", response_model=LetterListResponse)
def list_letters(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    limit: int = Query(default=20, ge=1, le=100),
):
    items = repository.list_letters(current_user.user_id, limit)
    return LetterListResponse(
        items=[_response(item) for item in items],
        unread_count=sum(item.status == "ready" for item in items),
    )


@router.get("/latest", response_model=LetterResponse | None)
def latest_letter(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    items = repository.list_letters(current_user.user_id, 1)
    return _response(items[0]) if items else None


@router.get("/preferences", response_model=LetterPreferenceResponse)
def get_preferences(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    pref = repository.get_preference(current_user.user_id)
    return LetterPreferenceResponse(
        enabled=pref.enabled,
        timezone=pref.timezone,
        publish_time=pref.publish_time.strftime("%H:%M"),
    )


@router.put("/preferences", response_model=LetterPreferenceResponse)
def update_preferences(
    request: LetterPreferenceRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    try:
        pref = repository.save_preference(
            current_user.user_id,
            request.enabled,
            request.timezone,
            time.fromisoformat(request.publish_time),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return LetterPreferenceResponse(
        enabled=pref.enabled,
        timezone=pref.timezone,
        publish_time=pref.publish_time.strftime("%H:%M"),
    )


@router.get("/{letter_id}", response_model=LetterResponse)
def get_letter(
    letter_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    item = repository.get_letter(current_user.user_id, letter_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="来信不存在")
    return _response(item)


@router.post("/{letter_id}/read", response_model=LetterResponse)
def mark_read(
    letter_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    item = repository.mark_read(current_user.user_id, letter_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="来信不存在")
    return _response(item)


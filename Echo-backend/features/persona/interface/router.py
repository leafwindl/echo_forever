from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from shared.interface.dependencies import CurrentUser, get_current_user

from features.persona.interface.schemas import PersonaResponse, PersonaUpdateRequest
from features.persona.public import (
    PersonaOperationError,
    PersonaUpdate,
    PersonaValidationError,
    UserPreferences,
    get_persona,
    reset_persona,
    update_persona,
)

router = APIRouter(prefix="/persona", tags=["persona"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _response_from_domain(persona: UserPreferences) -> PersonaResponse:
    return PersonaResponse(
        preferred_name=persona.preferred_name,
        reply_style=persona.reply_style,
        reply_length=persona.reply_length,
        support_mode=persona.support_mode,
        proactivity=persona.proactivity,
        avoid_topics=list(persona.avoid_topics),
        about_user=persona.about_user,
        relationship_pace=persona.relationship_pace,
        affection_style=persona.affection_style,
        enabled=persona.enabled,
        schema_version=persona.schema_version,
        is_customized=persona.is_customized,
        onboarding_completed=persona.onboarding_completed,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
    )


@router.get("/me", response_model=PersonaResponse)
def persona_get(current_user: CurrentUserDependency) -> PersonaResponse:
    """读取当前 Token 所属用户的设置，不接受外部 user_id。"""
    try:
        persona = get_persona(current_user.user_id)
    except PersonaValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _response_from_domain(persona)


@router.put("/me", response_model=PersonaResponse)
def persona_update(
    request: PersonaUpdateRequest,
    current_user: CurrentUserDependency,
) -> PersonaResponse:
    """完整更新当前用户设置；自由文本始终按数据而非系统指令处理。"""
    try:
        persona = update_persona(
            current_user.user_id,
            PersonaUpdate(
                preferred_name=request.preferred_name,
                reply_style=request.reply_style,
                reply_length=request.reply_length,
                support_mode=request.support_mode,
                proactivity=request.proactivity,
                avoid_topics=tuple(request.avoid_topics),
                about_user=request.about_user,
                relationship_pace=request.relationship_pace,
                affection_style=request.affection_style,
                enabled=request.enabled,
            ),
        )
    except PersonaValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PersonaOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return _response_from_domain(persona)


@router.post("/me/reset", response_model=PersonaResponse)
def persona_reset(current_user: CurrentUserDependency) -> PersonaResponse:
    """恢复 Persona 默认值，不删除长期记忆、聊天记录或摘要。"""
    try:
        persona = reset_persona(current_user.user_id)
    except PersonaValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _response_from_domain(persona)

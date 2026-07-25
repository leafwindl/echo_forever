import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status

from features.admin.interface.schemas import (
    ClearChatContextRequest,
    ClearChatContextResponse,
    RuntimePromptResponse,
    RuntimePromptUpdateRequest,
)
from features.admin.public import (
    AdminValidationError,
    clear_user_chat_context,
    get_effective_system_prompt,
    update_runtime_system_prompt,
)
from shared.config import settings

router = APIRouter(prefix="/admin/debug", tags=["admin-debug"])
INSECURE_ADMIN_TOKENS = {"change-me", "changeme", "admin", "test"}


def verify_admin_debug_access(
    x_admin_debug_token: str | None = Header(default=None, alias="X-Admin-Debug-Token"),
) -> None:
    if not settings.enable_admin_debug_api:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    configured_token = settings.admin_debug_token.strip()
    if len(configured_token) < 32 or configured_token.lower() in INSECURE_ADMIN_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin debug API is not securely configured",
        )
    provided_token = x_admin_debug_token or ""
    if not hmac.compare_digest(provided_token, configured_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin debug token")


@router.get("/prompt", response_model=RuntimePromptResponse)
async def admin_get_system_prompt(_: None = Depends(verify_admin_debug_access)):
    prompt = get_effective_system_prompt()
    return RuntimePromptResponse(prompt=prompt.content, source=prompt.source)


@router.put("/prompt", response_model=RuntimePromptResponse)
async def admin_update_system_prompt(
    request: RuntimePromptUpdateRequest,
    _: None = Depends(verify_admin_debug_access),
):
    try:
        prompt = update_runtime_system_prompt(request.prompt)
    except AdminValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return RuntimePromptResponse(prompt=prompt.content, source=prompt.source)


@router.post("/chat/clear", response_model=ClearChatContextResponse)
async def admin_clear_chat_context(
    request: ClearChatContextRequest,
    _: None = Depends(verify_admin_debug_access),
):
    try:
        result = clear_user_chat_context(request.user_id)
    except AdminValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return ClearChatContextResponse(
        deleted_messages=result.deleted_messages,
        reset_conversations=result.reset_conversations,
    )

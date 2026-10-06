from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from shared.interface.dependencies import CurrentUser, get_current_user

from features.push.application.manage_targets import ManagePushTargets
from features.push.public import get_push_target_manager

router = APIRouter(prefix="/push", tags=["push"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]
PushTargetManagerDependency = Annotated[
    ManagePushTargets,
    Depends(get_push_target_manager),
]


class PushTokenRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=160)
    platform: Literal["android", "harmonyos", "ios", "web"]
    provider: Literal["getui"] = "getui"
    token: str = Field(min_length=1, max_length=4096)
    app_version: str = Field(default="", max_length=80)
    environment: str = Field(default="", max_length=40)
    locale: str = Field(default="", max_length=80)


@router.put("/tokens/me", status_code=status.HTTP_204_NO_CONTENT)
def register_token(
    request: PushTokenRequest,
    current_user: CurrentUserDependency,
    manager: PushTargetManagerDependency,
):
    manager.register(
        user_id=current_user.user_id,
        device_id=request.device_id,
        platform=request.platform,
        provider=request.provider,
        token=request.token,
        app_version=request.app_version,
        environment=request.environment,
        locale=request.locale,
    )


@router.delete("/tokens/me/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def unregister_token(
    device_id: str,
    current_user: CurrentUserDependency,
    manager: PushTargetManagerDependency,
):
    manager.unregister(user_id=current_user.user_id, device_id=device_id)

from __future__ import annotations

from typing import Annotated, Literal

from db.postgres_connection import transaction
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from shared.interface.dependencies import CurrentUser, get_current_user

from features.auth.public import ensure_user_identity

router = APIRouter(prefix="/push", tags=["push"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


class PushTokenRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=160)
    platform: Literal["android", "ios", "web"]
    provider: Literal["getui"] = "getui"
    token: str = Field(min_length=1, max_length=4096)
    app_version: str = Field(default="", max_length=80)
    environment: str = Field(default="", max_length=40)
    locale: str = Field(default="", max_length=80)


@router.put("/tokens/me", status_code=status.HTTP_204_NO_CONTENT)
def register_token(request: PushTokenRequest, current_user: CurrentUserDependency):
    with transaction() as conn:
        ensure_user_identity(user_id=current_user.user_id, conn=conn)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO push_targets (
                    user_id, device_id, platform, provider, token,
                    app_version, environment, locale, status, last_seen_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', NOW())
                ON CONFLICT (user_id, device_id) DO UPDATE SET
                    platform = EXCLUDED.platform,
                    provider = EXCLUDED.provider,
                    token = EXCLUDED.token,
                    app_version = EXCLUDED.app_version,
                    environment = EXCLUDED.environment,
                    locale = EXCLUDED.locale,
                    status = 'active',
                    last_seen_at = NOW(),
                    updated_at = NOW()
                """,
                (
                    current_user.user_id,
                    request.device_id,
                    request.platform,
                    request.provider,
                    request.token,
                    request.app_version,
                    request.environment,
                    request.locale,
                ),
            )


@router.delete("/tokens/me/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def unregister_token(device_id: str, current_user: CurrentUserDependency):
    with transaction() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE push_targets
            SET status = 'revoked', updated_at = NOW()
            WHERE user_id = %s AND device_id = %s
            """,
            (current_user.user_id, device_id),
        )

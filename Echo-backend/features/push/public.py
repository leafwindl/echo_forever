from __future__ import annotations

from shared.config import settings

from features.push.infrastructure.getui_sender import GetuiNotificationSender
from features.push.infrastructure.postgres_repository import PostgresPushRepository

_sender: GetuiNotificationSender | None = None


def get_push_sender() -> GetuiNotificationSender:
    global _sender
    if _sender is None:
        _sender = GetuiNotificationSender(
            repository=PostgresPushRepository(),
            app_id=settings.getui_app_id,
            app_key=settings.getui_app_key,
            master_secret=settings.getui_master_secret,
            api_base_url=settings.getui_api_base_url,
        )
    return _sender


async def send_pending_notification_once() -> bool:
    return await get_push_sender().run_once()


__all__ = ["send_pending_notification_once"]

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass

import httpx

from features.push.infrastructure.postgres_repository import (
    NotificationOutboxItem,
    PostgresPushRepository,
    PushTarget,
)

logger = logging.getLogger(__name__)

_HARMONY_BUNDLE_NAME = "cn.echoaiforever.echo_app.dev"
_HARMONY_ABILITY_NAME = "EntryAbility"


@dataclass(frozen=True)
class _AccessToken:
    value: str
    expires_at_ms: int


@dataclass(frozen=True)
class _Credentials:
    app_id: str
    app_key: str
    master_secret: str

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_key and self.master_secret)


class GetuiNotificationSender:
    def __init__(
        self,
        *,
        repository: PostgresPushRepository,
        app_id: str,
        app_key: str,
        master_secret: str,
        harmony_app_id: str = "",
        harmony_app_key: str = "",
        harmony_master_secret: str = "",
        api_base_url: str = "https://restapi.getui.com/v2",
        timeout_seconds: float = 15,
    ):
        self.repository = repository
        self._credentials = {
            "android": _Credentials(app_id.strip(), app_key.strip(), master_secret.strip()),
            "ios": _Credentials(app_id.strip(), app_key.strip(), master_secret.strip()),
            "web": _Credentials(app_id.strip(), app_key.strip(), master_secret.strip()),
            "harmonyos": _Credentials(
                harmony_app_id.strip(),
                harmony_app_key.strip(),
                harmony_master_secret.strip(),
            ),
        }
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._access_tokens: dict[_Credentials, _AccessToken] = {}
        self._token_lock = asyncio.Lock()

    async def run_once(self) -> bool:
        item = self.repository.claim_due()
        if item is None:
            return False
        targets = self.repository.list_targets(item.user_id)
        if not targets:
            self.repository.mark_discarded(item.notification_id, "no_active_target")
            return True

        successes: list[str] = []
        transient_failure = False
        credentials_missing = False
        credential_groups: dict[_Credentials, list[PushTarget]] = {}
        for target in targets:
            credentials = self._credentials_for(target.platform)
            if not credentials.configured:
                credentials_missing = True
                logger.warning(
                    "Getui credentials are unavailable for platform=%s",
                    target.platform,
                )
                continue
            credential_groups.setdefault(credentials, []).append(target)

        for credentials, grouped_targets in credential_groups.items():
            async with httpx.AsyncClient(
                base_url=f"{self.api_base_url}/{credentials.app_id}",
                timeout=self.timeout_seconds,
                trust_env=False,
            ) as client:
                try:
                    access_token = await self._get_access_token(client, credentials)
                except Exception:
                    transient_failure = True
                    logger.warning(
                        "Getui authentication failed for platform=%s",
                        grouped_targets[0].platform,
                        exc_info=True,
                    )
                    continue

                for target in grouped_targets:
                    outcome = await self._send(client, access_token, item, target)
                    if outcome == "sent":
                        successes.append(target.device_id)
                    elif outcome == "invalid":
                        self.repository.invalidate_target(target.device_id)
                    else:
                        transient_failure = True

        if credentials_missing and not credential_groups:
            self.repository.mark_retry(item, "getui_credentials_unavailable")
            return True
        if successes:
            self.repository.mark_sent(item.notification_id, tuple(successes))
        elif transient_failure:
            self.repository.mark_retry(item, "getui_delivery_failed")
        else:
            self.repository.mark_discarded(item.notification_id, "all_targets_invalid")
        return True

    @property
    def _is_configured(self) -> bool:
        return self._credentials["android"].configured

    def _credentials_for(self, platform: str) -> _Credentials:
        return self._credentials.get(platform, self._credentials["android"])

    async def _get_access_token(
        self,
        client: httpx.AsyncClient,
        credentials: _Credentials,
    ) -> str:
        async with self._token_lock:
            now_ms = int(time.time() * 1000)
            cached = self._access_tokens.get(credentials)
            if cached is not None and now_ms + 60_000 < cached.expires_at_ms:
                return cached.value

            timestamp = str(now_ms)
            sign = hashlib.sha256(
                f"{credentials.app_key}{timestamp}{credentials.master_secret}".encode()
            ).hexdigest()
            response = await client.post(
                "/auth",
                json={
                    "sign": sign,
                    "timestamp": timestamp,
                    "appkey": credentials.app_key,
                },
            )
            payload = self._response_payload(response)
            if response.status_code >= 300 or payload.get("code") != 0:
                raise RuntimeError("Getui authentication was rejected")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("Getui authentication returned no token data")
            token = str(data.get("token") or "").strip()
            expires_at_ms = int(data.get("expire_time") or 0)
            if not token or expires_at_ms <= now_ms:
                raise RuntimeError("Getui authentication returned an invalid token")
            self._access_tokens[credentials] = _AccessToken(token, expires_at_ms)
            return token

    async def _send(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        item: NotificationOutboxItem,
        target: PushTarget,
    ) -> str:
        response = await client.post(
            "/push/single/cid",
            headers={"token": access_token},
            json=self._notification_request(item, target),
        )
        payload = self._response_payload(response)
        if response.status_code < 300 and payload.get("code") == 0:
            return "sent"

        message = str(payload.get("msg") or response.text).lower()
        if payload.get("code") == 20001 and (
            "target user is invalid" in message
            or "cid无效" in message
            or "cid不存在" in message
            or "cid不是当前应用" in message
        ):
            return "invalid"
        if payload.get("code") == 10001:
            self._access_tokens = {
                credentials: token
                for credentials, token in self._access_tokens.items()
                if token.value != access_token
            }
        logger.warning(
            "Getui send failed notification_id=%s status=%s code=%s",
            item.notification_id,
            response.status_code,
            payload.get("code"),
        )
        return "retry"

    def _notification_request(
        self,
        item: NotificationOutboxItem,
        target: PushTarget,
    ) -> dict[str, object]:
        body = item.body.strip() if item.body_policy == "preview" else ""
        click_payload = json.dumps(
            {key: str(value) for key, value in item.payload.items()},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request_id = hashlib.sha256(item.notification_id.encode()).hexdigest()[:32]
        notification = {
            "title": item.title or "Echo",
            "body": body or "Echo 发来了一条消息",
            "click_type": "payload",
            "payload": click_payload,
            "channel_id": "echo_messages",
            "channel_name": "Echo 消息",
            "channel_level": 4,
        }
        request: dict[str, object] = {
            "request_id": request_id,
            "settings": {"ttl": 3_600_000},
            "audience": {"cid": [target.token]},
            "push_message": {
                "notification": notification,
            },
        }
        if target.platform == "harmonyos":
            # HarmonyOS otherwise classifies the notification as an unknown
            # slot and suppresses the banner, icon, sound, and vibration.
            notification["slot_type"] = 1
            request["push_channel"] = {
                "harmony": {
                    "notification": {
                        "title": notification["title"],
                        "body": notification["body"],
                        "category": "social",
                        "click_type": "startapp",
                        "want": json.dumps(
                            {
                                "deviceId": "",
                                "bundleName": _HARMONY_BUNDLE_NAME,
                                "abilityName": _HARMONY_ABILITY_NAME,
                                "action": "action.system.home",
                                "parameters": {
                                    "route": "chat",
                                    "payload": click_payload,
                                },
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                }
            }
        return request

    @staticmethod
    def _response_payload(response: httpx.Response) -> dict[str, object]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

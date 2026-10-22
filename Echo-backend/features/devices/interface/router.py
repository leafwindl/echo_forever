from __future__ import annotations

import asyncio
import hmac
import inspect
import json
import logging
import os
import time
import uuid
from contextlib import suppress
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from features.devices.infrastructure.device_sessions import active_device_sessions as _active_device_sessions
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user

from features.devices.application.latency import DeviceLatencyTracker
from features.devices.application.device_probe import DeviceProbe
from features.devices.application.transcript_guard import is_plausible_device_transcript
from features.devices.domain.entities import DeviceAudioFormat
from features.devices.infrastructure.adapters import EchoAudioSource, parse_personal_device_map
from features.devices.infrastructure.audio_codec import (
    OpusPacketDecoder,
    encode_audio_bytes_to_opus_packets,
)
from features.devices.infrastructure.container import (
    get_process_device_voice_turn,
    get_stream_device_voice_turn,
)
from features.devices.infrastructure.device_management import (
    authenticate_database_device,
    bind_legacy_device,
    claim_pairing,
    claim_provisioning_session,
    create_pairing,
    create_provisioning_session,
    delete_speaker_profile,
    ensure_bootstrap_credential,
    get_user_device,
    list_speaker_profile,
    list_user_devices,
    record_voice_turn,
    rotate_device_credential,
    touch_device,
    unbind_user_device,
    update_user_device,
    update_voice_turn_messages,
    validate_device_credential,
)
from features.firmware_releases.public import get_latest_firmware_release
from shared.storage import get_cos_object_storage
from features.devices.infrastructure.endpoint_detector import AudioEndpointDetector
from features.devices.interface.schemas import (
    DeviceActivationResponse,
    DeviceBootstrapResponse,
    DeviceCredentialResponse,
    DeviceFirmwareResponse,
    DeviceHeartbeatRequest,
    DeviceListResponse,
    DevicePairingClaimRequest,
    DevicePairingResponse,
    DeviceProvisioningSessionResponse,
    DeviceSummary,
    DeviceUpdateRequest,
    DeviceWebSocketConfig,
    SpeakerEnrollmentResponse,
    SpeakerProfileResponse,
)
from features.voice.public import open_streaming_voice_recognition, synthesize_voice_reply

logger = logging.getLogger(__name__)

_device_probe = DeviceProbe()
router = APIRouter(prefix="/devices", tags=["devices"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _device_map() -> dict[str, str]:
    return parse_personal_device_map(settings.echo_device_user_map_json)


def _clean_bearer(value: str | None) -> str:
    clean = (value or "").strip()
    if clean.lower().startswith("bearer "):
        return clean[7:].strip()
    return clean


def _device_key(device_id: str, client_id: str) -> str:
    return f"{device_id.strip().lower()}|{client_id.strip().lower()}"


def _resolve_device_user(device_id: str, client_id: str) -> str | None:
    device_map = _device_map()
    exact_key = _device_key(device_id, client_id)
    return device_map.get(exact_key) or device_map.get(_device_key(device_id, "*"))


def _authenticate_personal_device(
    device_id: str,
    client_id: str,
    authorization: str | None,
) -> str | None:
    clean_device_id = device_id.strip().lower()
    clean_client_id = client_id.strip().lower()
    configured_token = settings.echo_device_token.strip()
    provided_token = _clean_bearer(authorization)
    database_user = None
    try:
        database_user = authenticate_database_device(
            clean_device_id, clean_client_id, provided_token
        )
    except Exception:
        logger.debug("Database device credential lookup unavailable", exc_info=True)
    if database_user:
        return database_user
    user_id = _resolve_device_user(clean_device_id, clean_client_id)
    if not clean_device_id or not clean_client_id or not configured_token or not user_id:
        return None
    if not hmac.compare_digest(provided_token, configured_token):
        return None
    return user_id


def _device_request_token(authorization: str | None) -> bool:
    provided = _clean_bearer(authorization)
    configured = settings.echo_device_token.strip()
    return bool(configured and provided and hmac.compare_digest(configured, provided))


def _verify_device_speaker(device_id: str, pcm16_audio: bytes) -> dict[str, object]:
    try:
        from features.devices.infrastructure.speaker_people_container import recognize
        return recognize(device_id, pcm16_audio)
    except Exception:
        logger.warning("Speaker verification failed device_id=%s", device_id, exc_info=True)
        return {"speaker_role": "unknown", "confidence": 0.0, "status": "unavailable"}


def _websocket_url() -> str:
    base = settings.static_url_prefix.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[8:]
    elif base.startswith("http://"):
        base = "ws://" + base[7:]
    return f"{base}/devices/ws"


def _device_firmware_version(firmware_version: str | None) -> str:
    reported_version = str(firmware_version or "").strip()
    if not reported_version or len(reported_version) > 80:
        return settings.echo_firmware_version
    return reported_version


@router.api_route(
    "/firmware/config",
    methods=["GET", "POST"],
    response_model=DeviceBootstrapResponse,
)
async def device_bootstrap(
    request: Request = None,
    device_id: str = Header(default="", alias="Device-Id"),
    client_id: str = Header(default="", alias="Client-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    echo_bind_token: str | None = Header(default=None, alias="Echo-Bind-Token"),
    firmware_version: str | None = Header(default=None, alias="Firmware-Version"),
):
    board_type = ""
    board_variant = ""
    if request is not None and request.method == "POST":
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        board = payload.get("board", {}) if isinstance(payload, dict) else {}
        if isinstance(board, dict):
            board_type = str(board.get("type") or "").strip()[:120]
            board_variant = str(board.get("name") or "").strip()[:120]
    device_firmware_version = _device_firmware_version(firmware_version)
    database_user = None
    provided_token = _clean_bearer(authorization)
    credential_row = None
    if authorization:
        try:
            credential_row = validate_device_credential(device_id, client_id, provided_token)
            database_user = (
                str(credential_row["owner_user_id"])
                if credential_row and credential_row.get("owner_user_id")
                else None
            )
        except Exception:
            logger.debug("Database device bootstrap lookup unavailable", exc_info=True)
    legacy_user = _resolve_device_user(device_id, client_id)
    direct_credential = None
    if echo_bind_token:
        try:
            direct_credential = claim_provisioning_session(
                claim_token=echo_bind_token,
                device_id=device_id,
                client_id=client_id,
                firmware_version=device_firmware_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except Exception:
            logger.debug("Device provisioning session claim unavailable", exc_info=True)
    if direct_credential is None and database_user is None and legacy_user is not None:
        try:
            direct_credential = bind_legacy_device(
                user_id=legacy_user,
                device_id=device_id,
                client_id=client_id,
                firmware_version=device_firmware_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except Exception:
            logger.debug("Legacy device binding unavailable", exc_info=True)
    if (
        direct_credential is None
        and database_user is None
        and legacy_user is None
        and not device_id.strip()
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device is not allowed")
    activation = None
    bootstrap_token = ""
    if direct_credential is None and database_user is None and legacy_user is None:
        try:
            pairing = create_pairing(
                device_id=device_id,
                client_id=client_id,
                firmware_version=device_firmware_version,
            )
            if credential_row is None:
                bootstrap_token = ensure_bootstrap_credential(device_id=device_id)
            activation = DeviceActivationResponse(
                pairing_id=pairing["pairing_id"],
                code=pairing["code"],
                message="请在 Echo APP 的设备页面输入配对码",
                pairing_only=True,
            )
        except Exception:
            logger.debug("Device bootstrap pairing unavailable", exc_info=True)
    try:
        touch_device(
            device_id=device_id,
            client_id=client_id,
            firmware_version=device_firmware_version,
        )
    except Exception:
        logger.debug("Device bootstrap heartbeat unavailable", exc_info=True)
    firmware = None
    if board_type:
        try:
            firmware = get_latest_firmware_release(board_type, board_variant)
        except Exception:
            logger.debug("Hardware firmware release lookup unavailable", exc_info=True)
    firmware_response = DeviceFirmwareResponse(version=settings.echo_firmware_version)
    if firmware is not None:
        try:
            firmware_response = DeviceFirmwareResponse(
                version=firmware.version,
                url=get_cos_object_storage().download_url(firmware.cos_object_key),
                sha256=firmware.sha256,
                size_bytes=firmware.size_bytes,
                board_type=firmware.board_type,
                board_variant=firmware.board_variant,
            )
        except Exception:
            logger.warning("Hardware firmware URL generation failed", exc_info=True)
    return DeviceBootstrapResponse(
        firmware=firmware_response,
        websocket=DeviceWebSocketConfig(
            url=_websocket_url(),
            token=(
                direct_credential["credential"]
                if direct_credential is not None
                else provided_token
                if database_user is not None
                else bootstrap_token
                or (provided_token if credential_row is not None else "")
                or (settings.echo_device_token if legacy_user is not None else "")
            ),
        ),
        activation=activation,
    )


@router.post("/provisioning/sessions", response_model=DeviceProvisioningSessionResponse)
def create_device_provisioning_session(current_user: CurrentUserDependency):
    try:
        return create_provisioning_session(user_id=current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/pairings", response_model=DevicePairingResponse)
def create_device_pairing(
    device_id: str = Header(default="", alias="Device-Id"),
    client_id: str = Header(default="", alias="Client-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    if not _device_request_token(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device credential"
        )
    try:
        return create_pairing(device_id=device_id, client_id=client_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/pairings/claim", response_model=DeviceCredentialResponse)
def claim_device_pairing(body: DevicePairingClaimRequest, current_user: CurrentUserDependency):
    try:
        return claim_pairing(
            user_id=current_user.user_id, pairing_id=body.pairing_id, code=body.code
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("", response_model=DeviceListResponse)
def get_devices(current_user: CurrentUserDependency):
    return {
        "items": [
            DeviceSummary.model_validate(item) for item in list_user_devices(current_user.user_id)
        ]
    }


@router.get("/{device_id}", response_model=DeviceSummary)
def get_device(device_id: str, current_user: CurrentUserDependency):
    item = get_user_device(current_user.user_id, device_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return item


@router.post("/{device_id}/connect")
@router.post("/{device_id}/probe")
async def connect_device(device_id: str, current_user: CurrentUserDependency):
    item = get_user_device(current_user.user_id, device_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    websocket = _active_device_sessions.get(device_id.strip().lower())
    if websocket is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="设备当前没有在线会话，请检查硬件网络",
        )
    try:
        await _device_probe.check(device_id.strip().lower(), websocket)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="设备未在时限内回应，请检查硬件状态") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="设备检测忙碌或被硬件拒绝，请稍后重试") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="设备会话已断开，请等待硬件重新联网",
        ) from exc
    return {"connected": True, "acknowledged": True, "device_id": device_id}


@router.patch("/{device_id}", response_model=DeviceSummary)
def patch_device(device_id: str, body: DeviceUpdateRequest, current_user: CurrentUserDependency):
    try:
        item = update_user_device(current_user.user_id, device_id, display_name=body.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return item


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: str, current_user: CurrentUserDependency):
    if not unbind_user_device(current_user.user_id, device_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")


@router.post("/{device_id}/credentials/rotate", response_model=DeviceCredentialResponse)
def rotate_credential(device_id: str, current_user: CurrentUserDependency):
    credential = rotate_device_credential(current_user.user_id, device_id)
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    item = get_user_device(current_user.user_id, device_id) or {}
    return {
        "device_id": item.get("device_id", device_id),
        "client_id": item.get("client_id", ""),
        "credential": credential,
    }


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def device_heartbeat(
    body: DeviceHeartbeatRequest,
    device_id: str = Header(default="", alias="Device-Id"),
    client_id: str = Header(default="", alias="Client-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    if _authenticate_personal_device(device_id, client_id, authorization) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device credential"
        )
    touch_device(
        device_id=device_id,
        client_id=client_id,
        firmware_version=body.firmware_version,
        wifi_ssid=body.wifi_ssid,
    )


@router.get("/{device_id}/speaker", response_model=SpeakerProfileResponse | None)
def get_speaker(device_id: str, current_user: CurrentUserDependency):
    item = list_speaker_profile(current_user.user_id, device_id)
    if item is None:
        return None
    return item


@router.post("/{device_id}/speaker/enrollment", response_model=SpeakerEnrollmentResponse)
async def enroll_speaker(
    device_id: str,
    audio: Annotated[UploadFile, File()],
    current_user: CurrentUserDependency,
):
    device = get_user_device(current_user.user_id, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    raise HTTPException(status_code=410, detail="旧版声纹录入已停用，请使用人员声纹重新录入")


@router.delete("/{device_id}/speaker", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker(device_id: str, current_user: CurrentUserDependency):
    if not delete_speaker_profile(current_user.user_id, device_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Speaker profile not found"
        )


@router.websocket("/ws")
async def device_websocket(websocket: WebSocket):
    device_id = websocket.headers.get("device-id", "")
    client_id = websocket.headers.get("client-id", "")
    user_id = _authenticate_personal_device(
        device_id,
        client_id,
        websocket.headers.get("authorization"),
    )
    if user_id is None:
        await websocket.close(code=4401, reason="Invalid device credential")
        return

    await websocket.accept()
    session_key = device_id.strip().lower()
    from features.devices.infrastructure.speaker_people_container import voice_enrollment
    voice_enrollment.disconnect(session_key)
    _active_device_sessions[session_key] = websocket
    try:
        touch_device(device_id=device_id, client_id=client_id, online=True)
    except Exception:
        logger.debug("Device heartbeat persistence unavailable", exc_info=True)
    session_id = uuid.uuid4().hex
    decoder: OpusPacketDecoder | None = None
    endpoint_detector: AudioEndpointDetector | None = None
    input_format: DeviceAudioFormat | None = None
    processing_task: asyncio.Task[None] | None = None
    realtime_asr_session = None
    capture_started_at: float | None = None
    maximum_utterance_bytes = settings.echo_device_max_utterance_seconds * 16000 * 2

    def new_auto_endpoint_detector() -> AudioEndpointDetector:
        from features.devices.infrastructure.speaker_people_container import hardware_calibration
        return AudioEndpointDetector(
            sample_rate=16000,
            silence_ms=(
                1800 if hardware_calibration.active(user_id, session_key)
                else settings.echo_device_auto_silence_ms
            ),
            minimum_speech_ms=settings.echo_device_auto_minimum_speech_ms,
            speech_rms_threshold=settings.echo_device_auto_speech_rms_threshold,
        )

    def reset_auto_capture() -> None:
        nonlocal decoder, endpoint_detector, capture_started_at
        decoder = OpusPacketDecoder(output_sample_rate=16000)
        endpoint_detector = new_auto_endpoint_detector()
        capture_started_at = time.perf_counter()

    async def drain_realtime_asr(session) -> str:
        """Read the final update while tolerating a provider that only sends partials."""
        latest_text = ""
        for _ in range(512):
            try:
                update = await asyncio.wait_for(session.receive_update(), timeout=0.05)
            except TimeoutError:
                break
            latest_text = update.text.strip()
            if update.is_final:
                break
        return latest_text

    async def process_turn(
        pcm16_audio: bytes,
        asr_session=None,
        *,
        speech_ended_at: float | None = None,
        speaker_pcm16_audio: bytes | None = None,
    ) -> None:
        started_at = time.perf_counter()
        tts_stop_sent = False
        try:
            from features.devices.infrastructure.speaker_people_container import hardware_calibration
            calibrating = hardware_calibration.active(user_id, session_key)
            request_id = f"device-{session_id}-{uuid.uuid4().hex[:12]}"
            latency = DeviceLatencyTracker(request_id, started_at=speech_ended_at)
            latency.mark("endpoint_detected")
            speaker = (
                {"status": "unknown", "speaker_role": "unknown", "confidence": 0.0}
                if calibrating else await asyncio.to_thread(
                    _verify_device_speaker, device_id, speaker_pcm16_audio or pcm16_audio,
                )
            )
            recognized_text = ""
            realtime_asr_succeeded = False
            if calibrating and asr_session is not None:
                with suppress(Exception):
                    await asr_session.close()
            elif asr_session is not None:
                try:
                    await asr_session.finish()
                    recognized_text = await drain_realtime_asr(asr_session)
                    if getattr(asr_session, "failed", False):
                        recognized_text = ""
                    else:
                        realtime_asr_succeeded = True
                    logger.info(
                        "Echo device realtime ASR finalized device_id=%s text_length=%s",
                        device_id,
                        len(recognized_text),
                    )
                except Exception:
                    logger.warning(
                        "Echo device realtime ASR failed; falling back to batch ASR device_id=%s",
                        device_id,
                        exc_info=True,
                    )
                finally:
                    with suppress(Exception):
                        await asr_session.close()

            if recognized_text and not is_plausible_device_transcript(
                recognized_text,
                len(pcm16_audio),
            ):
                logger.warning(
                    "Echo device realtime ASR transcript rejected; falling back to batch ASR "
                    "device_id=%s text_length=%s audio_duration_ms=%.1f",
                    device_id,
                    len(recognized_text),
                    len(pcm16_audio) * 1000 / (16000 * 2),
                )
                recognized_text = ""
                realtime_asr_succeeded = False

            if not calibrating and asr_session is not None and realtime_asr_succeeded and not recognized_text:
                latency.mark("asr_final")
                latency.mark("turn_complete")
                logger.info(
                    "Echo device ignored empty realtime ASR result device_id=%s",
                    device_id,
                )
                tts_stop_sent = True
                await websocket.send_json(
                    {"session_id": session_id, "type": "tts", "state": "stop"}
                )
                return

            async def send_recognized(user_text: str) -> None:
                try:
                    record_voice_turn(
                        device_id=device_id,
                        user_id=user_id,
                        request_id=request_id,
                        speaker=speaker,
                        asr_text=user_text,
                        audio_duration_ms=int(len(pcm16_audio) * 1000 / (16000 * 2)),
                    )
                except Exception:
                    logger.debug("Device voice turn persistence unavailable", exc_info=True)
                await websocket.send_json(
                    {
                        "session_id": session_id,
                        "type": "stt",
                        "text": user_text,
                        "speaker": speaker,
                    }
                )

            # Local opt-in: intercept enrollment before sending speech to the chat agent.
            enrollment_reply = None
            if calibrating:
                from features.devices.infrastructure.neural_speaker import extract
                enrollment_reply = await asyncio.to_thread(
                    hardware_calibration.consume, user_id, session_key,
                    speaker_pcm16_audio or pcm16_audio, extract,
                )
                if enrollment_reply is None:
                    enrollment_reply = "校准已取消"
            elif os.environ.get("ECHO_VOICE_ENROLLMENT_ENABLED", "").lower() == "true":
                from features.devices.infrastructure.speaker_people_container import voice_enrollment
                if not recognized_text:
                    recognized_text = await get_process_device_voice_turn().recognizer.recognize_pcm16(pcm16_audio)
                try:
                    enrollment_reply = await voice_enrollment.handle(
                        user_id, session_key, recognized_text, pcm16_audio,
                    )
                except HTTPException as error:
                    enrollment_reply = str(error.detail) + "。请重新读这一段，或说取消录入。"
                except Exception:
                    logger.warning("Voice enrollment temporarily unavailable", exc_info=True)
                    enrollment_reply = "声纹录入服务暂不可用，请稍后重试或取消录入。"

            if settings.echo_device_streaming_enabled and enrollment_reply is None:
                playback_started_at: float | None = None
                last_packet_sent_at: float | None = None
                maximum_packet_gap = 0.0
                schedule_rebases = 0
                packet_index = 0
                tts_started = False
                streaming_prebuffer_packets = settings.echo_device_streaming_prebuffer_packets

                async def send_tts_start() -> None:
                    nonlocal tts_started
                    if tts_started:
                        return
                    tts_started = True
                    await websocket.send_json(
                        {"session_id": session_id, "type": "tts", "state": "start"}
                    )
                    latency.mark("device_tts_start")

                async def send_sentence_start(text: str) -> None:
                    await websocket.send_json(
                        {
                            "session_id": session_id,
                            "type": "tts",
                            "state": "sentence_start",
                            "text": text,
                        }
                    )

                async def send_audio_packet(packet: bytes) -> None:
                    nonlocal last_packet_sent_at, maximum_packet_gap, packet_index
                    nonlocal playback_started_at, schedule_rebases
                    loop = asyncio.get_running_loop()
                    if playback_started_at is None:
                        playback_started_at = loop.time()
                    elif packet_index >= streaming_prebuffer_packets:
                        paced_index = packet_index - streaming_prebuffer_packets + 1
                        send_at = playback_started_at + paced_index * 0.06
                        delay = send_at - loop.time()
                        if delay > 0:
                            await asyncio.sleep(delay)
                        elif delay < -0.09:
                            playback_started_at = loop.time() - paced_index * 0.06
                            schedule_rebases += 1
                    await websocket.send_bytes(packet)
                    sent_at = loop.time()
                    if last_packet_sent_at is not None:
                        maximum_packet_gap = max(
                            maximum_packet_gap,
                            sent_at - last_packet_sent_at,
                        )
                    last_packet_sent_at = sent_at
                    latency.mark("device_first_packet")
                    packet_index += 1

                async def send_tts_stop() -> None:
                    nonlocal tts_stop_sent
                    if tts_stop_sent:
                        return
                    tts_stop_sent = True
                    buffered_tail_packets = min(
                        packet_index,
                        streaming_prebuffer_packets,
                    )
                    if buffered_tail_packets:
                        await asyncio.sleep(buffered_tail_packets * 0.06)
                    await websocket.send_json(
                        {"session_id": session_id, "type": "tts", "state": "stop"}
                    )

                stream_turn = get_stream_device_voice_turn()
                stream_kwargs = {
                    "user_id": user_id,
                    "pcm16_audio": pcm16_audio,
                    "request_id": request_id,
                    "on_recognized": send_recognized,
                    "on_tts_start": send_tts_start,
                    "on_sentence_start": send_sentence_start,
                    "on_audio_packet": send_audio_packet,
                    "on_tts_stop": send_tts_stop,
                    "recognized_text": recognized_text or None,
                    "latency": latency,
                }
                if "speaker_role" in inspect.signature(stream_turn.execute).parameters:
                    stream_kwargs["speaker_role"] = str(speaker.get("speaker_role") or "unknown")
                    stream_kwargs["speaker_confidence"] = float(speaker.get("confidence") or 0.0)
                    stream_kwargs["speaker_name"] = speaker.get("display_name") if speaker.get("speaker_role") == "known" else None
                result = await stream_turn.execute(**stream_kwargs)
                if result.user_message_id or result.assistant_message_id:
                    try:
                        update_voice_turn_messages(
                            request_id=request_id,
                            user_message_id=result.user_message_id,
                            assistant_message_id=result.assistant_message_id,
                        )
                    except Exception:
                        logger.debug("Device voice message linkage unavailable", exc_info=True)
                if not result.reply and packet_index == 0:
                    await send_tts_stop()
                latency.log_summary(device_id=device_id, packet_count=packet_index)
                logger.info(
                    "Echo streaming device turn delivered device_id=%s duration_ms=%.1f "
                    "packets=%s prebuffer_packets=%s max_packet_gap_ms=%.1f "
                    "schedule_rebases=%s",
                    device_id,
                    (time.perf_counter() - started_at) * 1000,
                    packet_index,
                    min(packet_index, streaming_prebuffer_packets),
                    maximum_packet_gap * 1000,
                    schedule_rebases,
                )
                return

            process_kwargs = {
                "user_id": user_id,
                "pcm16_audio": pcm16_audio,
                "request_id": request_id,
                "on_recognized": send_recognized,
            }
            if recognized_text:
                process_kwargs["recognized_text"] = recognized_text
            process_turn = get_process_device_voice_turn()
            if "speaker_role" in inspect.signature(process_turn.execute).parameters:
                process_kwargs["speaker_role"] = str(speaker.get("speaker_role") or "unknown")
                process_kwargs["speaker_confidence"] = float(speaker.get("confidence") or 0.0)
                process_kwargs["speaker_name"] = speaker.get("display_name") if speaker.get("speaker_role") == "known" else None
            if enrollment_reply is not None:
                from features.devices.domain.entities import DeviceTurnResult
                speech = await synthesize_voice_reply(enrollment_reply)
                result = DeviceTurnResult(
                    user_text=recognized_text, reply=enrollment_reply, audio_urls=speech.audio_urls,
                )
            else:
                result = await process_turn.execute(**process_kwargs)
            if result.user_message_id or result.assistant_message_id:
                try:
                    update_voice_turn_messages(
                        request_id=request_id,
                        user_message_id=result.user_message_id,
                        assistant_message_id=result.assistant_message_id,
                    )
                except Exception:
                    logger.debug("Device voice message linkage unavailable", exc_info=True)
            reply_ready_at = time.perf_counter()
            if not result.audio_urls:
                raise ValueError("Echo TTS did not return audio")

            source = EchoAudioSource()
            audio_bytes = await source.read(result.audio_urls[0])
            audio_loaded_at = time.perf_counter()
            packets = await asyncio.to_thread(
                encode_audio_bytes_to_opus_packets,
                audio_bytes,
                output_sample_rate=24000,
                frame_duration_ms=60,
                maximum_silence_ms=settings.echo_device_tts_max_silence_ms,
                silence_rms_threshold=settings.echo_device_tts_silence_rms_threshold,
            )
            audio_encoded_at = time.perf_counter()
            await websocket.send_json({"session_id": session_id, "type": "tts", "state": "start"})
            await websocket.send_json(
                {
                    "session_id": session_id,
                    "type": "tts",
                    "state": "sentence_start",
                    "text": result.reply,
                }
            )
            if settings.echo_device_playback_start_delay_ms:
                await asyncio.sleep(settings.echo_device_playback_start_delay_ms / 1000)

            prebuffer_count = min(
                settings.echo_device_playback_prebuffer_packets,
                len(packets),
            )
            for packet in packets[:prebuffer_count]:
                await websocket.send_bytes(packet)
            playback_started_at = asyncio.get_running_loop().time()
            maximum_send_lateness = 0.0
            for offset, packet in enumerate(packets[prebuffer_count:], start=1):
                send_at = playback_started_at + offset * 0.06
                delay = send_at - asyncio.get_running_loop().time()
                if delay > 0:
                    await asyncio.sleep(delay)
                maximum_send_lateness = max(
                    maximum_send_lateness,
                    asyncio.get_running_loop().time() - send_at,
                )
                await websocket.send_bytes(packet)
            playback_ends_at = playback_started_at + len(packets) * 0.06
            remaining_playback = playback_ends_at - asyncio.get_running_loop().time()
            if remaining_playback > 0:
                await asyncio.sleep(remaining_playback)
            if settings.echo_device_playback_stop_grace_ms:
                await asyncio.sleep(settings.echo_device_playback_stop_grace_ms / 1000)
            tts_stop_sent = True
            await websocket.send_json({"session_id": session_id, "type": "tts", "state": "stop"})
            logger.info(
                "Echo device turn completed device_id=%s input_bytes=%s output_packets=%s "
                "prebuffer_packets=%s reply_ready_ms=%.1f audio_load_ms=%.1f "
                "audio_encode_ms=%.1f playback_ms=%.1f max_send_lateness_ms=%.1f "
                "duration_ms=%.1f",
                device_id,
                len(pcm16_audio),
                len(packets),
                prebuffer_count,
                (reply_ready_at - started_at) * 1000,
                (audio_loaded_at - reply_ready_at) * 1000,
                (audio_encoded_at - audio_loaded_at) * 1000,
                (time.perf_counter() - audio_encoded_at) * 1000,
                maximum_send_lateness * 1000,
                (time.perf_counter() - started_at) * 1000,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Echo device turn failed device_id=%s", device_id)
            try:
                await websocket.send_json(
                    {
                        "session_id": session_id,
                        "type": "alert",
                        "status": "错误",
                        "message": "Echo 暂时没有回应",
                        "emotion": "sad",
                    }
                )
                if not tts_stop_sent:
                    tts_stop_sent = True
                    await websocket.send_json(
                        {"session_id": session_id, "type": "tts", "state": "stop"}
                    )
            except Exception:
                pass

    async def start_processing() -> None:
        nonlocal decoder, endpoint_detector, processing_task, realtime_asr_session
        if decoder is None or processing_task is not None:
            return
        detector = endpoint_detector
        pcm16_audio = decoder.finish()
        decoder = None
        endpoint_detector = None
        asr_session = realtime_asr_session
        realtime_asr_session = None
        speaker_pcm16_audio = pcm16_audio[: 16000 * 2 * 12]
        if detector is not None:
            pcm16_audio = detector.trim(pcm16_audio)
        if len(pcm16_audio) > maximum_utterance_bytes:
            logger.warning(
                "Truncating long device utterance device_id=%s input_bytes=%s maximum_bytes=%s",
                device_id,
                len(pcm16_audio),
                maximum_utterance_bytes,
            )
            pcm16_audio = pcm16_audio[:maximum_utterance_bytes]
        speech_ended_at = time.perf_counter()
        if detector is not None and detector.speech_started:
            speech_ended_at -= detector.trailing_silence_ms / 1000
        processing_task = asyncio.create_task(
            process_turn(
                pcm16_audio,
                asr_session,
                speech_ended_at=speech_ended_at,
                speaker_pcm16_audio=speaker_pcm16_audio,
            )
        )

    try:
        while True:
            if processing_task is not None and processing_task.done():
                await processing_task
                processing_task = None
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if processing_task is not None and processing_task.done():
                await processing_task
                processing_task = None
            binary = message.get("bytes")
            if binary is not None:
                if decoder is not None and processing_task is None:
                    if len(binary) > settings.echo_device_max_opus_packet_bytes:
                        raise ValueError("Device Opus packet is too large")
                    decoded_pcm = decoder.push(binary)
                    if realtime_asr_session is not None and decoded_pcm:
                        try:
                            await realtime_asr_session.send_audio(decoded_pcm)
                        except Exception:
                            logger.warning(
                                "Echo device realtime ASR upload failed; "
                                "falling back to batch ASR device_id=%s",
                                device_id,
                                exc_info=True,
                            )
                            with suppress(Exception):
                                await realtime_asr_session.close()
                            realtime_asr_session = None
                    if endpoint_detector is not None:
                        endpoint_reached = endpoint_detector.push(decoded_pcm)
                        if endpoint_reached:
                            capture_duration_ms = (
                                (time.perf_counter() - capture_started_at) * 1000
                                if capture_started_at is not None
                                else endpoint_detector.elapsed_ms
                            )
                            logger.info(
                                "Echo device endpoint detected device_id=%s buffered_bytes=%s "
                                "audio_duration_ms=%.1f capture_ms=%.1f speech_elapsed_ms=%.1f "
                                "voiced_ms=%.1f trailing_silence_ms=%.1f noise_floor_rms=%.1f "
                                "active_rms_threshold=%.1f configured_silence_ms=%s",
                                device_id,
                                decoder.buffered_bytes,
                                decoder.buffered_bytes * 1000 / (16000 * 2),
                                capture_duration_ms,
                                endpoint_detector.speech_elapsed_ms,
                                endpoint_detector.voiced_ms,
                                endpoint_detector.trailing_silence_ms,
                                endpoint_detector.noise_floor_rms,
                                endpoint_detector.active_rms_threshold,
                                settings.echo_device_auto_silence_ms,
                            )
                            await start_processing()
                        elif (
                            not endpoint_detector.speech_started
                            and not endpoint_detector.has_speech_candidate
                            and endpoint_detector.elapsed_ms
                            >= settings.echo_device_auto_no_speech_timeout_ms
                        ):
                            logger.info(
                                "Echo device auto capture reset after no speech device_id=%s "
                                "buffered_bytes=%s",
                                device_id,
                                decoder.buffered_bytes,
                            )
                            reset_auto_capture()
                        elif (
                            endpoint_detector.speech_started
                            and endpoint_detector.speech_elapsed_ms
                            >= (
                                10000 if hardware_calibration.active(user_id, session_key)
                                else settings.echo_device_auto_maximum_speech_ms
                            )
                        ):
                            logger.info(
                                "Echo device maximum speech duration reached device_id=%s "
                                "buffered_bytes=%s",
                                device_id,
                                decoder.buffered_bytes,
                            )
                            await start_processing()
                    elif decoder.buffered_bytes > maximum_utterance_bytes:
                        logger.warning(
                            "Echo device manual utterance reached maximum duration "
                            "device_id=%s buffered_bytes=%s",
                            device_id,
                            decoder.buffered_bytes,
                        )
                        await start_processing()
                continue

            text = message.get("text")
            if text is None:
                continue
            payload = json.loads(text)
            message_type = str(payload.get("type", ""))
            if message_type == "mcp":
                _device_probe.receive(session_key, websocket, payload.get("payload"))
                continue
            if message_type == "hello":
                version = int(payload.get("version", 0))
                params = payload.get("audio_params", {})
                input_format = DeviceAudioFormat(
                    sample_rate=int(params.get("sample_rate", 0)),
                    channels=int(params.get("channels", 0)),
                    frame_duration_ms=int(params.get("frame_duration", 0)),
                    format=str(params.get("format", "")),
                )
                if version != 1 or input_format != DeviceAudioFormat(16000, 1, 60):
                    await websocket.close(code=4400, reason="Unsupported device audio protocol")
                    return
                await websocket.send_json(
                    {
                        "type": "hello",
                        "transport": "websocket",
                        "session_id": session_id,
                        "audio_params": {
                            "format": "opus",
                            "sample_rate": 24000,
                            "channels": 1,
                            "frame_duration": 60,
                        },
                    }
                )
            elif message_type == "listen":
                state = str(payload.get("state", ""))
                if state == "start":
                    if processing_task is not None:
                        continue
                    if realtime_asr_session is not None:
                        with suppress(Exception):
                            await realtime_asr_session.close()
                        realtime_asr_session = None
                    decoder = OpusPacketDecoder(output_sample_rate=16000)
                    capture_started_at = time.perf_counter()
                    mode = str(payload.get("mode", ""))
                    endpoint_detector = new_auto_endpoint_detector() if mode == "auto" else None
                    from features.devices.infrastructure.speaker_people_container import hardware_calibration
                    if (
                        not hardware_calibration.active(user_id, session_key)
                        and settings.echo_device_realtime_asr_enabled
                        and settings.voice_streaming_asr_enabled
                    ):
                        try:
                            realtime_asr_session = await asyncio.wait_for(
                                open_streaming_voice_recognition(),
                                timeout=10,
                            )
                            logger.info(
                                "Echo device realtime ASR ready device_id=%s mode=%s",
                                device_id,
                                mode,
                            )
                        except Exception:
                            logger.warning(
                                "Echo device realtime ASR unavailable; using batch ASR "
                                "device_id=%s",
                                device_id,
                                exc_info=True,
                            )
                            realtime_asr_session = None
                elif state == "stop" and decoder is not None and processing_task is None:
                    await start_processing()
            elif message_type == "abort":
                if processing_task is not None:
                    processing_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await processing_task
                    processing_task = None
                decoder = None
                endpoint_detector = None
                if realtime_asr_session is not None:
                    with suppress(Exception):
                        await realtime_asr_session.close()
                    realtime_asr_session = None
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Echo device websocket failed device_id=%s", device_id)
        with suppress(Exception):
            await websocket.close(code=1011, reason="Device session failed")
    finally:
        _device_probe.disconnect(session_key, websocket)
        if _active_device_sessions.get(session_key) is websocket:
            from features.devices.infrastructure.speaker_people_container import hardware_calibration
            hardware_calibration.cancel(user_id, session_key)
            voice_enrollment.disconnect(session_key)
            _active_device_sessions.pop(session_key, None)
            try:
                touch_device(device_id=device_id, client_id=client_id, online=False)
            except Exception:
                logger.debug("Device offline heartbeat persistence unavailable", exc_info=True)
        if processing_task is not None:
            if not processing_task.done():
                processing_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await processing_task
        if realtime_asr_session is not None:
            with suppress(Exception):
                await realtime_asr_session.close()

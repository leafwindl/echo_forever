from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
import uuid
from contextlib import suppress

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from shared.config import settings

from features.devices.application.latency import DeviceLatencyTracker
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
from features.devices.infrastructure.endpoint_detector import AudioEndpointDetector
from features.devices.interface.schemas import (
    DeviceBootstrapResponse,
    DeviceFirmwareResponse,
    DeviceWebSocketConfig,
)
from features.voice.public import open_streaming_voice_recognition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/devices", tags=["devices"])


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
    return device_map.get(exact_key) or device_map.get(
        _device_key(device_id, "*")
    )


def _authenticate_personal_device(
    device_id: str,
    client_id: str,
    authorization: str | None,
) -> str | None:
    clean_device_id = device_id.strip().lower()
    clean_client_id = client_id.strip().lower()
    configured_token = settings.echo_device_token.strip()
    provided_token = _clean_bearer(authorization)
    user_id = _resolve_device_user(clean_device_id, clean_client_id)
    if not clean_device_id or not clean_client_id or not configured_token or not user_id:
        return None
    if not hmac.compare_digest(provided_token, configured_token):
        return None
    return user_id


def _websocket_url() -> str:
    base = settings.static_url_prefix.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[8:]
    elif base.startswith("http://"):
        base = "ws://" + base[7:]
    return f"{base}/devices/ws"


@router.api_route(
    "/firmware/config",
    methods=["GET", "POST"],
    response_model=DeviceBootstrapResponse,
)
async def device_bootstrap(
    device_id: str = Header(default="", alias="Device-Id"),
    client_id: str = Header(default="", alias="Client-Id"),
):
    if _resolve_device_user(device_id, client_id) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device is not allowed")
    return DeviceBootstrapResponse(
        firmware=DeviceFirmwareResponse(version=settings.echo_firmware_version),
        websocket=DeviceWebSocketConfig(
            url=_websocket_url(),
            token=settings.echo_device_token,
        ),
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
    session_id = uuid.uuid4().hex
    decoder: OpusPacketDecoder | None = None
    endpoint_detector: AudioEndpointDetector | None = None
    input_format: DeviceAudioFormat | None = None
    processing_task: asyncio.Task[None] | None = None
    realtime_asr_session = None
    capture_started_at: float | None = None
    maximum_utterance_bytes = settings.echo_device_max_utterance_seconds * 16000 * 2

    def new_auto_endpoint_detector() -> AudioEndpointDetector:
        return AudioEndpointDetector(
            sample_rate=16000,
            silence_ms=settings.echo_device_auto_silence_ms,
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
    ) -> None:
        started_at = time.perf_counter()
        try:
            request_id = f"device-{session_id}-{uuid.uuid4().hex[:12]}"
            latency = DeviceLatencyTracker(request_id, started_at=speech_ended_at)
            latency.mark("endpoint_detected")
            recognized_text = ""
            if asr_session is not None:
                try:
                    await asr_session.finish()
                    recognized_text = await drain_realtime_asr(asr_session)
                    if getattr(asr_session, "failed", False):
                        recognized_text = ""
                    logger.info(
                        "Echo device realtime ASR finalized device_id=%s text_length=%s",
                        device_id,
                        len(recognized_text),
                    )
                except Exception:
                    logger.warning(
                        "Echo device realtime ASR failed; falling back to batch ASR "
                        "device_id=%s",
                        device_id,
                        exc_info=True,
                    )
                finally:
                    with suppress(Exception):
                        await asr_session.close()

            async def send_recognized(user_text: str) -> None:
                await websocket.send_json(
                    {"session_id": session_id, "type": "stt", "text": user_text}
                )

            if settings.echo_device_streaming_enabled:
                playback_started_at: float | None = None
                last_packet_sent_at: float | None = None
                maximum_packet_gap = 0.0
                schedule_rebases = 0
                packet_index = 0

                async def send_tts_start() -> None:
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
                    else:
                        send_at = playback_started_at + packet_index * 0.06
                        delay = send_at - loop.time()
                        if delay > 0:
                            await asyncio.sleep(delay)
                        elif delay < -0.09:
                            playback_started_at = loop.time() - packet_index * 0.06
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
                    await websocket.send_json(
                        {"session_id": session_id, "type": "tts", "state": "stop"}
                    )

                result = await get_stream_device_voice_turn().execute(
                    user_id=user_id,
                    pcm16_audio=pcm16_audio,
                    request_id=request_id,
                    on_recognized=send_recognized,
                    on_tts_start=send_tts_start,
                    on_sentence_start=send_sentence_start,
                    on_audio_packet=send_audio_packet,
                    on_tts_stop=send_tts_stop,
                    recognized_text=recognized_text or None,
                    latency=latency,
                )
                latency.log_summary(device_id=device_id, packet_count=packet_index)
                logger.info(
                    "Echo streaming device turn delivered device_id=%s duration_ms=%.1f "
                    "packets=%s max_packet_gap_ms=%.1f schedule_rebases=%s",
                    device_id,
                    (time.perf_counter() - started_at) * 1000,
                    packet_index,
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
            result = await get_process_device_voice_turn().execute(**process_kwargs)
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
            )
            audio_encoded_at = time.perf_counter()
            await websocket.send_json(
                {"session_id": session_id, "type": "tts", "state": "start"}
            )
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
            await websocket.send_json(
                {"session_id": session_id, "type": "tts", "state": "stop"}
            )
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
                                "trailing_silence_ms=%.1f configured_silence_ms=%s",
                                device_id,
                                decoder.buffered_bytes,
                                decoder.buffered_bytes * 1000 / (16000 * 2),
                                capture_duration_ms,
                                endpoint_detector.speech_elapsed_ms,
                                endpoint_detector.trailing_silence_ms,
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
                            >= settings.echo_device_auto_maximum_speech_ms
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
                    endpoint_detector = (
                        new_auto_endpoint_detector()
                        if mode == "auto"
                        else None
                    )
                    if (
                        settings.echo_device_realtime_asr_enabled
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
        if processing_task is not None:
            if not processing_task.done():
                processing_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await processing_task
        if realtime_asr_session is not None:
            with suppress(Exception):
                await realtime_asr_session.close()

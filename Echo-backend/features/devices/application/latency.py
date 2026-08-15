from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class DeviceLatencyTracker:
    """Record monotonic milestones for one device voice turn."""

    def __init__(self, request_id: str, *, started_at: float | None = None):
        self.request_id = request_id
        self.started_at = started_at if started_at is not None else time.perf_counter()
        self._milestones: dict[str, float] = {}

    def mark(self, milestone: str) -> float:
        existing = self._milestones.get(milestone)
        if existing is not None:
            return (existing - self.started_at) * 1000

        now = time.perf_counter()
        self._milestones[milestone] = now
        elapsed_ms = (now - self.started_at) * 1000
        logger.info(
            "Echo device latency request_id=%s milestone=%s elapsed_ms=%.1f unix_ms=%s",
            self.request_id,
            milestone,
            elapsed_ms,
            int(time.time() * 1000),
        )
        return elapsed_ms

    def elapsed_ms(self, milestone: str) -> float | None:
        recorded_at = self._milestones.get(milestone)
        if recorded_at is None:
            return None
        return (recorded_at - self.started_at) * 1000

    def log_summary(self, *, device_id: str, packet_count: int) -> None:
        def value(milestone: str) -> str:
            elapsed = self.elapsed_ms(milestone)
            return f"{elapsed:.1f}" if elapsed is not None else "missing"

        logger.info(
            "Echo device latency summary request_id=%s device_id=%s packets=%s "
            "endpoint_ms=%s asr_final_ms=%s llm_first_delta_ms=%s "
            "llm_first_sentence_ms=%s tts_first_pcm_ms=%s "
            "device_first_audio_ms=%s reply_persisted_ms=%s app_notified_ms=%s "
            "turn_complete_ms=%s",
            self.request_id,
            device_id,
            packet_count,
            value("endpoint_detected"),
            value("asr_final"),
            value("llm_first_delta"),
            value("llm_first_sentence"),
            value("tts_first_pcm"),
            value("device_first_packet"),
            value("reply_persisted"),
            value("app_notified"),
            value("turn_complete"),
        )

import asyncio
import io
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from melo.api import TTS
from pydantic import BaseModel, Field


logger = logging.getLogger("uvicorn.error")


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    speaker: str = Field(default="ZH", min_length=1, max_length=64)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class MeloRuntime:
    def __init__(self) -> None:
        self.model: TTS | None = None
        self.lock = asyncio.Lock()

    def load(self) -> None:
        self.model = TTS(
            language=os.getenv("MELOTTS_LANGUAGE", "ZH"),
            device=os.getenv("MELOTTS_DEVICE", "cpu"),
        )

    def warm_up(self) -> None:
        warmup_text = os.getenv("MELOTTS_WARMUP_TEXT", "你好").strip()
        if not warmup_text:
            return
        self.synthesize(
            SynthesisRequest(
                text=warmup_text,
                speaker=os.getenv("MELOTTS_WARMUP_SPEAKER", "ZH"),
                speed=1.0,
            )
        )

    def synthesize(self, request: SynthesisRequest) -> bytes:
        if self.model is None:
            raise RuntimeError("MeloTTS model is not ready")
        speaker_ids = self.model.hps.data.spk2id
        if request.speaker not in speaker_ids:
            available_speakers = ", ".join(sorted(speaker_ids.keys()))
            raise ValueError(
                f"Unknown speaker '{request.speaker}'; available: {available_speakers}"
            )
        speaker_id = speaker_ids[request.speaker]

        output = io.BytesIO()
        self.model.tts_to_file(
            request.text.strip(),
            speaker_id,
            output,
            speed=request.speed,
            quiet=True,
            format="wav",
        )
        return output.getvalue()


runtime = MeloRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    started_at = time.perf_counter()
    await asyncio.to_thread(runtime.load)
    await asyncio.to_thread(runtime.warm_up)
    logger.info(
        "MeloTTS model loaded and warmed duration_ms=%.1f",
        (time.perf_counter() - started_at) * 1000,
    )
    yield


app = FastAPI(title="Echo MeloTTS", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    if runtime.model is None:
        raise HTTPException(status_code=503, detail="MeloTTS model is not ready")
    return {"status": "ok"}


@app.post("/synthesize")
async def synthesize(request: SynthesisRequest) -> Response:
    requested_at = time.perf_counter()
    queue_ms = 0.0
    try:
        async with runtime.lock:
            synthesis_started_at = time.perf_counter()
            queue_ms = (synthesis_started_at - requested_at) * 1000
            audio_bytes = await asyncio.to_thread(runtime.synthesize, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("MeloTTS synthesis failed")
        raise HTTPException(status_code=503, detail="MeloTTS synthesis failed") from exc

    if not audio_bytes:
        raise HTTPException(status_code=503, detail="MeloTTS returned empty audio")
    logger.info(
        "MeloTTS synthesis completed text_length=%s audio_bytes=%s queue_ms=%.1f "
        "synthesis_ms=%.1f total_ms=%.1f",
        len(request.text.strip()),
        len(audio_bytes),
        queue_ms,
        (time.perf_counter() - synthesis_started_at) * 1000,
        (time.perf_counter() - requested_at) * 1000,
    )
    return Response(content=audio_bytes, media_type="audio/wav")

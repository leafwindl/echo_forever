import asyncio
import io
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from melo.api import TTS
from pydantic import BaseModel, Field


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

    def synthesize(self, request: SynthesisRequest) -> bytes:
        if self.model is None:
            raise RuntimeError("MeloTTS model is not ready")
        speaker_id = self.model.hps.data.spk2id.get(request.speaker)
        if speaker_id is None:
            available_speakers = ", ".join(sorted(self.model.hps.data.spk2id.keys()))
            raise ValueError(
                f"Unknown speaker '{request.speaker}'; available: {available_speakers}"
            )

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
    await asyncio.to_thread(runtime.load)
    yield


app = FastAPI(title="Echo MeloTTS", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    if runtime.model is None:
        raise HTTPException(status_code=503, detail="MeloTTS model is not ready")
    return {"status": "ok"}


@app.post("/synthesize")
async def synthesize(request: SynthesisRequest) -> Response:
    try:
        async with runtime.lock:
            audio_bytes = await asyncio.to_thread(runtime.synthesize, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MeloTTS synthesis failed") from exc

    if not audio_bytes:
        raise HTTPException(status_code=503, detail="MeloTTS returned empty audio")
    return Response(content=audio_bytes, media_type="audio/wav")

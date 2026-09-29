"""Local-only, single-model CPU worker. Never stores or logs audio."""
import asyncio
import hashlib
import os
import threading
from pathlib import Path

import numpy as np
import sherpa_onnx
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

model_path = Path(os.environ["ECHO_SPEAKER_MODEL"])
model_id = "campp-zh:" + hashlib.sha256(model_path.read_bytes()).hexdigest()
config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
    model=str(model_path), num_threads=1, provider="cpu", debug=False
)
if not config.validate():
    raise RuntimeError("Invalid speaker model")
extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
gate = threading.Lock()
app = FastAPI()
MAX_BYTES = 16000 * 2 * 12


@app.get("/health")
def health():
    return {"ready": True, "model_id": model_id, "dimension": extractor.dim}


def extract(audio):
    if len(audio) % 2 or not 16000 * 2 * 3 <= len(audio) <= MAX_BYTES:
        raise HTTPException(422, "请录制 3 至 12 秒单声道语音")
    samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768
    if float(np.mean(np.abs(samples) >= 0.99)) > 0.02:
        raise HTTPException(422, "录音削波过多，请远离麦克风后重录")
    frames = samples[:len(samples) // 320 * 320].reshape(-1, 320)
    active_seconds = float(np.sum(np.sqrt(np.mean(frames * frames, axis=1)) > 0.008)) * 0.02
    if active_seconds < 2:
        raise HTTPException(422, "有效声音不足，请正常音量连续说一句话")
    stream = extractor.create_stream()
    stream.accept_waveform(sample_rate=16000, waveform=samples)
    stream.input_finished()
    if not extractor.is_ready(stream):
        raise HTTPException(422, "语音不足，无法提取声纹")
    vector = np.asarray(extractor.compute(stream), dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(vector).all() or norm <= 0:
        raise HTTPException(503, "声纹模型输出无效")
    return {"embedding": (vector / norm).tolist(), "model_id": model_id}


@app.post("/embedding")
async def embedding(request: Request):
    if not gate.acquire(blocking=False):
        raise HTTPException(429, "声纹服务忙碌，请稍后重试")
    try:
        audio = bytearray()
        try:
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(audio) + len(chunk) > MAX_BYTES:
                        raise HTTPException(413, "录音过长")
                    audio.extend(chunk)
        except TimeoutError as exc:
            raise HTTPException(408, "上传录音超时") from exc
        return await run_in_threadpool(extract, audio)
    finally:
        gate.release()

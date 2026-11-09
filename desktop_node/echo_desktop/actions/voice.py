from __future__ import annotations

import io
import winsound

import httpx

from echo_desktop.protocol import ActionError


def speak_text(text: str, tts_url: str) -> dict:
    clean = text.strip()
    if not clean:
        raise ActionError("invalid_text", "朗读内容不能为空。")
    url = tts_url.rstrip("/") + "/tts"
    try:
        with httpx.Client(trust_env=False, timeout=70) as client:
            response = client.post(url, json={"text": clean})
    except httpx.HTTPError as exc:
        raise ActionError("tts_unreachable", "本地 TTS 服务没有连接上。") from exc
    if response.status_code != 200:
        raise ActionError("tts_failed", f"本地 TTS 返回 {response.status_code}。")
    audio = response.content
    if not audio:
        raise ActionError("tts_empty", "本地 TTS 没有返回音频。")
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
        winsound.PlaySound(
            audio,
            winsound.SND_MEMORY | winsound.SND_NODEFAULT,
        )
    except RuntimeError as exc:
        raise ActionError("playback_failed", "Windows 无法播放这段音频。") from exc
    return {"spoken": True, "char_count": len(clean), "bytes": len(audio)}

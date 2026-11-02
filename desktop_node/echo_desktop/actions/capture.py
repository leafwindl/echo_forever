from __future__ import annotations

import base64
import io
import os
from datetime import UTC, datetime

from echo_desktop.protocol import ActionError

MAX_CAPTURE_BYTES = int(os.environ.get("ECHO_DESKTOP_MAX_CAPTURE_BYTES", "3000000"))


def _encode_jpeg(image) -> dict:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    content = buffer.getvalue()
    if len(content) > MAX_CAPTURE_BYTES:
        raise ActionError("capture_too_large", "画面太大，无法安全传回。")
    return {
        "image_base64": base64.b64encode(content).decode("ascii"),
        "mime_type": "image/jpeg",
        "byte_size": len(content),
        "captured_at": datetime.now(UTC).isoformat(),
    }


def capture_screen() -> dict:
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise ActionError("screen_capture_unavailable", "缺少 Pillow，无法截图。") from exc
    try:
        image = ImageGrab.grab(all_screens=True).convert("RGB")
    except Exception as exc:
        raise ActionError("screen_capture_failed", f"截图失败：{exc}") from exc
    payload = _encode_jpeg(image)
    payload.update({"width": image.width, "height": image.height})
    return payload


def capture_camera() -> dict:
    try:
        import cv2
    except ImportError as exc:
        raise ActionError("camera_unavailable", "缺少 OpenCV，无法打开摄像头。") from exc
    index = int(os.environ.get("ECHO_DESKTOP_CAMERA_INDEX", "0"))
    capture = cv2.VideoCapture(index, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
    if not capture.isOpened():
        capture.release()
        raise ActionError("camera_unavailable", "摄像头打不开，可能被其他程序占用。")
    try:
        for _ in range(8):
            capture.read()
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ActionError("camera_capture_failed", "摄像头没有返回画面。")
    from PIL import Image

    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    payload = _encode_jpeg(image)
    payload.update({"width": image.width, "height": image.height})
    return payload

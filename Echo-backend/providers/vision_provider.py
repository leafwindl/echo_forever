from __future__ import annotations

from shared.config import settings

from providers.llm_provider import get_llm_provider


class VisionUnavailableError(RuntimeError):
    pass


async def describe_desktop_image(
    *,
    image_base64: str,
    mime_type: str,
    question: str,
) -> str:
    if not settings.desktop_vision_enabled:
        raise VisionUnavailableError("Desktop vision is disabled")
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise VisionUnavailableError("Unsupported desktop image type")
    cleaned_question = question.strip()[:300] or "请用中文简短描述画面中能确认的内容。"
    prompt = (
        "你是 Echo 的电脑视觉观察器。只描述图片中能直接确认的内容，"
        "不猜测人物身份、年龄、职业、健康或其他敏感属性；看不清就说看不清。"
        f"用户的问题：{cleaned_question}"
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_base64}",
                    },
                },
            ],
        }
    ]
    response = await get_llm_provider().chat_completion_message(
        messages=messages,
        thinking={"type": "disabled"},
        model=settings.desktop_vision_model,
        temperature=0.2,
        max_tokens=settings.desktop_vision_max_tokens,
    )
    content = response.content.strip()
    if not content:
        raise VisionUnavailableError("Vision model returned an empty description")
    return content


__all__ = ["VisionUnavailableError", "describe_desktop_image"]

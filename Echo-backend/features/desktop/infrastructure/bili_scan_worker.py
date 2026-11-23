"""B站扫描异步任务：工具只负责发起，worker 负责扫描、评分和回话。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from features.desktop.infrastructure.bili_scan_store import (
    claim_next_scan_job,
    cleanup_old_scan_jobs,
    complete_scan_job,
    fail_scan_job,
    recover_running_scan_jobs,
)

logger = logging.getLogger(__name__)

BRIDGE_SCAN_COMMAND = (
    "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/bili_scan' -Method Post "
    "-ContentType 'application/json; charset=utf-8' -TimeoutSec 420 "
    "| ConvertTo-Json -Compress -Depth 6"
)

WECHAT_TARGET = "叶子"
MAX_JUDGE_ITEMS = 10
MAX_NOTIFY_ITEMS = 8
MIN_SHARE_SCORE = 6.0
WORKER_POLL_SECONDS = 5

JUDGE_PROMPT = (
    "你是 Echo，正在刷B站。看这张视频截图，判断值不值得分享给叶子。"
    '只输出一个 JSON 对象，不要 Markdown：'
    '{"score": 0到10的整数, "note": "20字以内的分享话术"}。'
    "有趣、新鲜、有故事感、有梗算高分；教学、广告、纯文字、黑屏算低分。"
    "note 像微信里随手发的一句；不要提B站、标题、链接，不要说截图二字。"
    "score 低于 6 时 note 留空字符串。"
)


def _parse_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_score(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(score, 10.0))


def _clean_note(value) -> str:
    return " ".join(str(value or "").split()).strip().strip('"“”')[:60]


async def _scan_videos(user_id: str) -> list[dict]:
    from features.desktop.public import run_desktop_command

    result = await run_desktop_command(
        user_id=user_id,
        command=BRIDGE_SCAN_COMMAND,
        owner_type="echo",
        timeout_seconds=480,
    )
    if not result.ok:
        raise RuntimeError(result.output[:300] or "bili scan command failed")
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bili scan returned non-json: {result.output[:200]}") from exc
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("stderr") or "bili scan failed"))
    return list(payload.get("items") or [])


async def _judge_one(item: dict) -> dict | None:
    from providers.llm_provider import get_llm_provider

    frame = str(item.get("frame_base64") or "").strip()
    if not frame:
        return None
    title = str(item.get("title") or "").strip()[:80]
    try:
        response = await get_llm_provider().chat_completion_message(
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"视频标题（只作参考，不要写进话术）：{title}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{frame}"},
                        },
                    ],
                },
            ],
            thinking={"type": "disabled"},
            temperature=0.8,
            max_tokens=200,
        )
        payload = _parse_json_object(response.content)
    except Exception:
        logger.warning("bili scan judge failed", exc_info=True)
        return None
    return {
        "score": _coerce_score(payload.get("score")),
        "note": _clean_note(payload.get("note")),
    }


async def _judge(items: list[dict]) -> list[dict]:
    scored: list[dict] = []
    for item in items[:MAX_JUDGE_ITEMS]:
        verdict = await _judge_one(item)
        if verdict is None:
            continue
        frame = str(item.get("frame") or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not frame:
            continue
        scored.append(
            {
                "title": str(item.get("title") or "").strip()[:80],
                "url": str(item.get("url") or "").strip()[:300],
                "frame": frame,
                "score": verdict["score"],
                "note": verdict["note"],
            }
        )
    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored


def _instruction(items: list[dict]) -> str:
    lines = "\n".join(
        f"- {item['title']}（frame: {item['frame']}，score: {item['score']}）"
        for item in items[:MAX_NOTIFY_ITEMS]
    )
    return (
        "你刚刷完B站，结果如下（只作参考，不要逐条念）：\n"
        f"{lines}\n"
        "如果你自己觉得有值得分享的（最多2条），直接调用 bili_share 发给叶子；"
        "如果觉得没什么想发的，就只回一句你看了什么、什么感觉。"
        "不要说“我去刷了”，已经刷完了。"
    )


async def _notify_completed(job: dict, result: dict) -> None:
    from features.chat.public import (
        deliver_external_assistant_message,
        generate_proactive_action,
    )
    from features.desktop.public import send_wechat_message

    user_id = str(job["user_id"])
    conversation_id = str(job.get("conversation_id") or "")
    items = list(result.get("items") or [])
    segments: tuple[str, ...] = ()
    try:
        reply = await generate_proactive_action(
            user_id=user_id,
            conversation_id=conversation_id,
            instruction=_instruction(items),
        )
        segments = tuple(
            segment.strip()
            for segment in (reply.reply_segments or (reply.reply_text,))
            if segment and segment.strip()
        )
    except Exception:
        logger.warning("bili scan notify agent failed", exc_info=True)
    if not segments:
        titles = "、".join(item["title"] for item in items[:3]) or "几个视频"
        segments = (f"刷完了，看到{titles}。有想看的跟我说。",)
    for segment in segments:
        try:
            await send_wechat_message(
                user_id=user_id,
                chat=WECHAT_TARGET,
                text=segment,
            )
        except Exception:
            logger.warning("bili scan notify delivery failed", exc_info=True)
    try:
        await deliver_external_assistant_message(
            user_id=user_id,
            content="\n".join(segments),
            idempotency_key=f"bili_scan_done:{job['job_id']}",
            source="bili",
        )
    except Exception:
        logger.warning("bili scan notify history failed", exc_info=True)


async def _notify_failed(job: dict) -> None:
    from features.chat.public import deliver_external_assistant_message
    from features.desktop.public import send_wechat_message

    user_id = str(job["user_id"])
    text = "B站没刷成，刚才卡住了。晚点再让我试试。"
    try:
        await send_wechat_message(user_id=user_id, chat=WECHAT_TARGET, text=text)
    except Exception:
        logger.warning("bili scan failure delivery failed", exc_info=True)
    try:
        await deliver_external_assistant_message(
            user_id=user_id,
            content=text,
            idempotency_key=f"bili_scan_failed:{job['job_id']}",
            source="bili",
        )
    except Exception:
        logger.warning("bili scan failure history failed", exc_info=True)


async def process_bili_scan_once() -> int:
    # 单 worker 串行：进程重启后把残留 running 放回队列。
    recover_running_scan_jobs()
    cleanup_old_scan_jobs()
    job = claim_next_scan_job()
    if job is None:
        return 0
    try:
        items = await _scan_videos(str(job["user_id"]))
        scored = await _judge(items)
        limit = max(1, min(int(job.get("item_limit") or 8), 10))
        scored = scored[:limit]
        if not scored:
            raise RuntimeError("no scored items")
        result = {
            "items": scored,
            "scanned_at": datetime.now(UTC).isoformat(),
        }
        complete_scan_job(str(job["job_id"]), result)
        await _notify_completed(job, result)
    except Exception as exc:
        status = fail_scan_job(str(job["job_id"]), f"{type(exc).__name__}: {exc}")
        logger.warning(
            "bili scan job failed job_id=%s status=%s",
            job["job_id"],
            status,
            exc_info=True,
        )
        if status == "failed":
            await _notify_failed(job)
    return 1


async def run_bili_scan_loop() -> None:
    logger.info("Bili scan worker started")
    while True:
        processed = 0
        try:
            processed = await process_bili_scan_once()
        except Exception:
            logger.warning("Bili scan worker tick failed", exc_info=True)
        await asyncio.sleep(WORKER_POLL_SECONDS if processed else 10)

"""B站刷视频分享：每小时刷一轮，挑值得的分享给叶子。"""

from __future__ import annotations

import asyncio
import json
import logging

from shared.config import settings

logger = logging.getLogger(__name__)

# 从 bridge 拉一轮扫描结果（含帧 base64）
BRIDGE_SCAN_COMMAND = (
    "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/bili_scan' -Method Post "
    "-ContentType 'application/json; charset=utf-8' -TimeoutSec 420 "
    "| ConvertTo-Json -Compress -Depth 6"
)

# 挑几个分享
MAX_SHARE_PER_ROUND = 2
# 每小时刷一次
SCAN_INTERVAL_SECONDS = 3600


def _owner_user_id() -> str:
    """刷视频分享归属的 echoed 用户（桌面节点 owner_type=echo）。"""
    return settings.bili_share_user_id.strip()


async def _scan_videos() -> list[dict]:
    from features.desktop.public import execute_desktop_action

    result = await execute_desktop_action(
        user_id=_owner_user_id(),
        action="exec",
        arguments={"command": BRIDGE_SCAN_COMMAND},
        timeout_seconds=480,
        owner_type="echo",
    )
    output = str(result.data.get("output") or "")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        logger.warning("bili scan returned non-json: %s", output[:300])
        return []
    if not payload.get("ok"):
        logger.warning("bili scan failed: %s", payload.get("stderr"))
        return []
    return list(payload.get("items") or [])


def _pick_candidates(items: list[dict]) -> list[dict]:
    """粗筛：去掉明显不可分享的（标题过短/纯统计），保留有画面的。"""
    picked = []
    for item in items:
        title = str(item.get("title") or "").strip()
        if len(title) < 6:
            continue
        if "添加至稍后再看" in title or title.replace("\n", "").isdigit():
            continue
        if not item.get("frame_base64"):
            continue
        picked.append(item)
    return picked


async def _judge(items: list[dict]) -> list[dict]:
    """让视觉模型看帧，挑出值得分享的（宁缺毋滥）。"""
    from providers.vision_provider import describe_desktop_image

    scored: list[tuple[float, dict, str]] = []
    for item in items:
        frame = str(item.get("frame_base64") or "")
        if not frame:
            continue
        try:
            description = await describe_desktop_image(
                image_base64=frame,
                mime_type="image/png",
                question=(
                    "这是B站视频画面截帧。用一句话说明画面内容，并判断它是否有分享价值"
                    "（有趣/新鲜/有故事感算有，教学/广告/纯文字/黑屏算没有）。"
                    "最后单独一行输出分数（0-10，越高越值得分享）。"
                ),
            )
        except Exception:
            logger.warning("bili frame judge failed", exc_info=True)
            continue
        score = 0.0
        for line in description.splitlines():
            line = line.strip()
            if line.replace(".", "").isdigit():
                try:
                    score = float(line)
                    break
                except ValueError:
                    continue
        scored.append((score, item, description))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [
        {**item, "judge": description, "score": score}
        for score, item, description in scored[:MAX_SHARE_PER_ROUND]
        if score >= 6.0
    ]


async def _compose_share_text(item: dict) -> str:
    """用 Echo 的语气写一句分享话术。"""
    from features.chat.public import generate_chat_reply

    prompt = (
        "你刚在B站刷到一个视频，想分享给叶子。视频标题："
        f"{item.get('title')}。画面描述：{item.get('judge')}。"
        "用你自己的语气写一句话（20字以内，像随手发的），不要提B站/标题/链接。"
    )
    try:
        result = await generate_chat_reply(
            _owner_user_id(),
            message=prompt,
            conversation_mode="chat",
            memory_enabled=False,
            tools_enabled=False,
        )
        text = str(result.reply or "").strip()
        return text[:60] or "刚刷到一个挺有意思的"
    except Exception:
        logger.warning("bili share compose failed", exc_info=True)
        return "刚刷到一个挺有意思的"


async def _send_share(item: dict) -> None:
    from features.desktop.public import execute_desktop_action

    text = await _compose_share_text(item)
    items = [{"type": "text", "text": text}]
    frame = str(item.get("frame_base64") or "")
    if frame:
        items.append({"type": "image", "image_base64": frame})
    body = json.dumps({"items": items}, ensure_ascii=False).replace("'", "''")
    command = (
        "Invoke-RestMethod -Uri 'http://127.0.0.1:8765/send_sequence' -Method Post "
        "-ContentType 'application/json; charset=utf-8' "
        f"-Body '{body}' -TimeoutSec 180 | ConvertTo-Json -Compress -Depth 6"
    )
    await execute_desktop_action(
        user_id=_owner_user_id(),
        action="exec",
        arguments={"command": command},
        timeout_seconds=200,
        owner_type="echo",
    )
    logger.info("bili share sent title=%s text=%s", item.get("title", "")[:40], text[:30])


async def process_bili_share_once() -> int:
    items = await _scan_videos()
    if not items:
        return 0
    candidates = await _judge(_pick_candidates(items))
    if not candidates:
        logger.info("bili share: nothing worth sharing this round")
        return 0
    for item in candidates:
        try:
            await _send_share(item)
        except Exception:
            logger.warning("bili share send failed", exc_info=True)
    return len(candidates)


async def run_bili_share_loop() -> None:
    while True:
        try:
            shared = await process_bili_share_once()
            if shared:
                logger.info("bili share round done shared=%s", shared)
        except Exception:
            logger.warning("bili share round failed", exc_info=True)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


__all__ = ["process_bili_share_once", "run_bili_share_loop"]

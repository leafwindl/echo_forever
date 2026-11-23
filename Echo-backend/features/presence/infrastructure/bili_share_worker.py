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
# 低于这个分数不分享
MIN_SHARE_SCORE = 6.0
# 启动时等自己的电脑节点上线，避免首轮必然失败
NODE_WAIT_SECONDS = 180
NODE_WAIT_INTERVAL_SECONDS = 5

FALLBACK_SHARE_TEXT = "刚刷到一个挺有意思的"

# Echo 自己就是多模态模型，看图、判断、写话术一次完成，不再单独调视觉模型。
SHARE_JUDGE_PROMPT = (
    "你是 Echo，正在刷B站。看这张视频截图，判断值不值得分享给叶子。"
    '只输出一个 JSON 对象，不要 Markdown：'
    '{"score": 0到10的整数, "note": "20字以内的分享话术"}。'
    "有趣、新鲜、有故事感、有梗算高分；教学、广告、纯文字、黑屏算低分。"
    "note 像微信里随手发的一句；不要提B站、标题、链接，不要说截图二字。"
    "score 低于 6 时 note 留空字符串。"
)


def _owner_user_id() -> str:
    """刷视频分享归属的 echoed 用户（桌面节点 owner_type=echo）。"""
    return settings.bili_share_user_id.strip()


async def _run_remote_command(
    command: str,
    *,
    timeout_seconds: int = 480,
) -> tuple[bool, str]:
    """走 agent 的异步 exec：提交后轮询 job_result，避免 30 秒同步超时。"""
    from features.desktop.public import run_desktop_command

    result = await run_desktop_command(
        user_id=_owner_user_id(),
        command=command,
        owner_type="echo",
        timeout_seconds=timeout_seconds,
    )
    return result.ok, result.output


async def _scan_videos() -> list[dict]:
    ok, output = await _run_remote_command(BRIDGE_SCAN_COMMAND, timeout_seconds=480)
    if not ok:
        logger.warning("bili scan command failed: %s", output[:300])
        return []
    logger.info("bili scan output chars=%s", len(output))
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


async def _judge_one(item: dict) -> dict | None:
    """让 Echo 看帧，返回 {score, note}；失败返回 None。"""
    from providers.llm_provider import get_llm_provider

    frame = str(item.get("frame_base64") or "").strip()
    if not frame:
        return None
    title = str(item.get("title") or "").strip()[:80]
    try:
        response = await get_llm_provider().chat_completion_message(
            messages=[
                {"role": "system", "content": SHARE_JUDGE_PROMPT},
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
        logger.warning("bili share judge failed", exc_info=True)
        return None
    return {
        "score": _coerce_score(payload.get("score")),
        "note": _clean_note(payload.get("note")),
    }


async def _judge(items: list[dict]) -> list[dict]:
    """让 Echo 自己看图判断并写话术（宁缺毋滥）。"""
    scored: list[dict] = []
    for item in items:
        verdict = await _judge_one(item)
        if verdict is None:
            continue
        scored.append({**item, **verdict})
    scored.sort(key=lambda row: row["score"], reverse=True)
    return [
        item
        for item in scored[:MAX_SHARE_PER_ROUND]
        if item["score"] >= MIN_SHARE_SCORE and item["note"]
    ]


def _bridge_command(path: str, payload: dict, *, timeout_seconds: int) -> str:
    body = json.dumps(payload, ensure_ascii=False).replace("'", "''")
    return (
        f"Invoke-RestMethod -Uri 'http://127.0.0.1:8765{path}' -Method Post "
        "-ContentType 'application/json; charset=utf-8' "
        f"-Body '{body}' -TimeoutSec {timeout_seconds} | ConvertTo-Json -Compress -Depth 6"
    )


def _bridge_ok(output: str) -> tuple[bool, str]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return False, f"non-json: {output[:200]}"
    if not isinstance(payload, dict) or not payload.get("ok"):
        return False, str(payload)[:200]
    return True, ""


async def _send_share(item: dict) -> None:
    """用 bridge 的图片目录发图+文：bridge 已把帧存在 C:/EchoComputer/images。

    帧的 base64 有几百 KB，塞进 agent 的 PowerShell 命令行会被截断，
    所以只传路径，让 bridge 自己从 images 目录读取。
    """
    text = str(item.get("note") or "").strip() or FALLBACK_SHARE_TEXT
    frame = str(item.get("frame") or "").strip()
    if frame:
        command = _bridge_command(
            "/send_image",
            {"path": frame, "text": text},
            timeout_seconds=120,
        )
    else:
        command = _bridge_command(
            "/send_sequence",
            {"items": [{"type": "text", "text": text}]},
            timeout_seconds=120,
        )
    ok, output = await _run_remote_command(command, timeout_seconds=140)
    if not ok:
        logger.warning("bili share send failed: %s", output[:300])
        return
    delivered, reason = _bridge_ok(output)
    if not delivered:
        logger.warning("bili share bridge rejected: %s", reason)
        return
    try:
        from features.conversation_events.public import (
            ACTOR_ECHO,
            EVENT_SHARE,
            record_conversation_event,
        )

        record_conversation_event(
            event_type=EVENT_SHARE,
            source="bili",
            actor=ACTOR_ECHO,
            user_id=_owner_user_id(),
            content=text,
            payload={
                "title": str(item.get("title") or "")[:80],
                "frame": bool(frame),
            },
        )
    except Exception:
        logger.warning("record bili share event failed", exc_info=True)
    logger.info(
        "bili share sent title=%s text=%s frame=%s",
        item.get("title", "")[:40],
        text[:30],
        bool(frame),
    )


async def _wait_for_echo_node(timeout_seconds: int = NODE_WAIT_SECONDS) -> bool:
    """等 Echo 自己的电脑节点上线，避免启动瞬间首轮必然失败。"""
    from features.desktop.public import list_desktop_nodes

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        try:
            nodes = await asyncio.to_thread(list_desktop_nodes, _owner_user_id(), "echo")
        except Exception:
            nodes = []
        if any(item.online for item in nodes):
            return True
        await asyncio.sleep(NODE_WAIT_INTERVAL_SECONDS)
    return False


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
    if not await _wait_for_echo_node():
        logger.warning("bili share: Echo 电脑节点未上线，首轮照常尝试")
    while True:
        try:
            shared = await process_bili_share_once()
            if shared:
                logger.info("bili share round done shared=%s", shared)
        except Exception:
            logger.warning("bili share round failed", exc_info=True)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


__all__ = ["process_bili_share_once", "run_bili_share_loop"]

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
# 分享发给叶子的微信会话（专用微信只有这一个联系人）
WECHAT_SHARE_TARGET = "叶子"

SHARE_NOTE_SYSTEM_PROMPT = (
    "你是 Echo，刚在B站刷到一个视频，想随口分享给叶子。"
    "只输出一句中文，20 字以内，像微信里随手发的一句；"
    "不要提B站、标题、链接、截图；不要引号、解释或换行。"
)
FALLBACK_SHARE_TEXT = "刚刷到一个挺有意思的"


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


def _clean_description(text: str) -> str:
    """去掉视觉模型最后那行纯分数，只留画面描述。"""
    kept = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().replace(".", "").replace("。", "").isdigit()
    ]
    return " ".join(kept)[:300]


async def _compose_share_text(item: dict) -> str:
    """用一次轻量生成写分享话术，不写入聊天历史。"""
    from providers.llm_provider import get_llm_provider

    facts = (
        f"视频标题：{str(item.get('title') or '').strip()[:80]}\n"
        f"画面描述：{_clean_description(str(item.get('judge') or ''))}"
    )
    try:
        response = await get_llm_provider().chat_completion_message(
            messages=[
                {"role": "system", "content": SHARE_NOTE_SYSTEM_PROMPT},
                {"role": "user", "content": facts},
            ],
            thinking={"type": "disabled"},
            temperature=0.9,
            max_tokens=80,
        )
        text = " ".join(str(response.content or "").split()).strip().strip('"“”')
        if text:
            return text[:60]
    except Exception:
        logger.warning("bili share compose failed", exc_info=True)
    return FALLBACK_SHARE_TEXT


async def _send_share(item: dict) -> None:
    """把分享话术发到叶子的微信。

    帧 base64 会达到几百 KB，而 agent 用命令行执行 PowerShell，
    Windows 命令行上限约 32767 字符，带图必然被截断。这里只发文字。
    """
    from features.desktop.public import send_wechat_message

    text = await _compose_share_text(item)
    ok = await send_wechat_message(
        user_id=_owner_user_id(),
        chat=WECHAT_SHARE_TARGET,
        text=text,
    )
    if not ok:
        logger.warning("bili share send failed title=%s", item.get("title", "")[:40])
        return
    logger.info(
        "bili share sent via wechat title=%s text=%s",
        item.get("title", "")[:40],
        text[:30],
    )


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

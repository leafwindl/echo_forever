"""查询"当前哪些能力真的可用"，供每轮工具选择使用。

在线状态来自节点 Hub 的实时连接状态，不是心跳超时窗口，所以判断是准的。
查询走同步 psycopg，因此放进线程池，避免阻塞事件循环。

查询失败时保守地返回"在线"：宁可多给工具（最多多一次失败调用），也不要因为
一次数据库抖动让用户失去操作自己设备的能力。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from features.desktop.public import list_desktop_nodes
from features.mobile_agent.public import list_mobile_agent_devices

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolAvailability:
    desktop_online: bool = False
    phone_online: bool = False


async def load_tool_availability(user_id: str) -> ToolAvailability:
    desktop_online, phone_online = await asyncio.gather(
        asyncio.to_thread(_desktop_online, user_id),
        asyncio.to_thread(_phone_online, user_id),
    )
    return ToolAvailability(desktop_online=desktop_online, phone_online=phone_online)


def _desktop_online(user_id: str) -> bool:
    try:
        return any(node.online for node in list_desktop_nodes(user_id))
    except Exception:
        logger.warning(
            "Desktop availability lookup failed user_id=%s; falling back to available",
            user_id,
            exc_info=True,
        )
        return True


def _phone_online(user_id: str) -> bool:
    try:
        return any(item.online for item in list_mobile_agent_devices(user_id))
    except Exception:
        logger.warning(
            "Phone availability lookup failed user_id=%s; falling back to available",
            user_id,
            exc_info=True,
        )
        return True

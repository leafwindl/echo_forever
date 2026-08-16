from __future__ import annotations

_PROGRESS_TEXT = {
    "search_web": "好，我查一下。",
    "create_chat_schedule": "好，我先确认一下这个提醒。",
    "list_chat_schedules": "我看看你现在的提醒。",
    "cancel_chat_schedule": "好，我确认一下要取消的提醒。",
}


def build_call_progress_text(tool_name: str) -> str:
    return _PROGRESS_TEXT.get(tool_name.strip(), "")

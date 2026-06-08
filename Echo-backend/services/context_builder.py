from dataclasses import dataclass
from typing import Dict, List, Optional

from config import settings
from services.memory import get_conversation_summary, get_history

# 统一控制短期上下文窗口：1 轮 = user 1 条 + assistant 1 条。
MAX_ROUNDS = 10
MAX_HISTORY_MESSAGES = MAX_ROUNDS * 2


@dataclass
class ChatContext:
    """发给大模型的一次完整上下文。

    当前第三阶段只包含系统 Prompt、最近历史和当前用户消息。
    后续会话摘要、长期记忆和向量召回都应该从这里接入，而不是散落在接口层。
    """

    messages: List[Dict[str, str]]
    history_messages: List[Dict[str, str]]
    conversation_summary: str = ""


def build_chat_context(
    user_id: str,
    user_message: str,
    conversation_id: Optional[str] = None,
) -> ChatContext:
    """构建当前轮对话上下文。

    运行顺序：
    1. 读取该用户最近的短期历史。
    2. 放入系统 Prompt。
    3. 追加历史消息。
    4. 追加当前用户消息。

    这一步暂时保持 v0.1/v0.2 第二阶段行为不变。
    """
    summary_text = ""
    summary_message_id = 0
    if conversation_id:
        summary_state = get_conversation_summary(user_id, conversation_id)
        summary_text = str(summary_state["summary"])
        summary_message_id = int(summary_state["summary_message_id"])

    history = get_history(
        user_id,
        limit=MAX_HISTORY_MESSAGES,
        conversation_id=conversation_id,
        after_message_id=summary_message_id,
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": settings.system_prompt}]
    if summary_text:
        # 摘要作为压缩上下文注入，帮助模型理解早期话题，同时避免塞入全部原始历史。
        messages.append({
            "role": "system",
            "content": f"当前会话摘要：\n{summary_text}",
        })
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    return ChatContext(
        messages=messages,
        history_messages=history,
        conversation_summary=summary_text,
    )

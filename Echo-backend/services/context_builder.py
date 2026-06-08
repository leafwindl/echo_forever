from dataclasses import dataclass
from typing import Dict, List, Optional

from config import settings
from services.memory import get_history

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
    history = get_history(user_id, limit=MAX_HISTORY_MESSAGES, conversation_id=conversation_id)

    messages: List[Dict[str, str]] = [{"role": "system", "content": settings.system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    return ChatContext(messages=messages, history_messages=history)

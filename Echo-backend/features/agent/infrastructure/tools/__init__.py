from features.agent.infrastructure.tools.beat_tools import register_beat_tools
from features.agent.infrastructure.tools.bili_tools import register_bili_tools
from features.agent.infrastructure.tools.computer_tools import register_computer_tools
from features.agent.infrastructure.tools.desktop_tools import register_desktop_tools
from features.agent.infrastructure.tools.mobile_tools import register_mobile_agent_tools
from features.agent.infrastructure.tools.proactive_tools import register_proactive_tools
from features.agent.infrastructure.tools.profile_tools import register_profile_tools
from features.agent.infrastructure.tools.relationship_tools import (
    register_relationship_tools,
)
from features.agent.infrastructure.tools.schedule_tools import register_schedule_tools
from features.agent.infrastructure.tools.sticker_tools import register_sticker_tools
from features.agent.infrastructure.tools.web_search_tools import register_web_search_tool

__all__ = [
    "register_beat_tools",
    "register_bili_tools",
    "register_computer_tools",
    "register_desktop_tools",
    "register_mobile_agent_tools",
    "register_proactive_tools",
    "register_profile_tools",
    "register_relationship_tools",
    "register_schedule_tools",
    "register_sticker_tools",
    "register_web_search_tool",
]

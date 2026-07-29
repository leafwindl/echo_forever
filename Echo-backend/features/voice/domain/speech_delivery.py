import re
import unicodedata
from dataclasses import dataclass

UNSPOKEN_UNICODE_CATEGORIES = {"Cf", "Cs", "Co", "Cn", "Sk", "So"}
VARIATION_SELECTORS = {"\ufe0e", "\ufe0f"}

_CONCERN_PATTERN = re.compile(
    r"(?:累|疲惫|辛苦|难受|难过|委屈|害怕|担心|疼|休息|睡觉|睡一觉|别急|慢慢来)"
)
_CHEERFUL_PATTERN = re.compile(r"(?:哈哈|嘿嘿|开心|太好了|真好|好耶|恭喜|做到了|完成了|不错|厉害)")
_SERIOUS_PATTERN = re.compile(r"(?:认真|重要|危险|安全|注意|先别|必须|紧急|不能忽视|需要尽快)")
_CURIOUS_PATTERN = re.compile(r"(?:[？?]|怎么|为什么|什么样|想不想|愿不愿意|可以吗|好吗)\s*$")


@dataclass(frozen=True)
class SpeechDelivery:
    style: str
    instruction: str


_DELIVERIES = {
    "natural": SpeechDelivery(
        style="natural",
        instruction="像日常聊天一样自然松弛，语速中等，轻重音有变化，不要播音腔。",
    ),
    "curious": SpeechDelivery(
        style="curious",
        instruction="带着友善的好奇自然说，语速中等，疑问尾音轻微上扬，不要审问感。",
    ),
    "caring": SpeechDelivery(
        style="caring",
        instruction="温和关心地自然说，语速略慢但不拖沓，停顿克制，不要煽情。",
    ),
    "cheerful": SpeechDelivery(
        style="cheerful",
        instruction="轻松明快地自然说，语速稍快一点，带一点笑意，不要夸张。",
    ),
    "serious": SpeechDelivery(
        style="serious",
        instruction="平静认真地自然说，语速中等，重点清楚，不要像播报或说教。",
    ),
}


def prepare_speech_text(text: str, maximum_chars: int) -> str:
    """Remove visual-only characters and apply the synthesis request limit."""
    sanitized = "".join(
        (
            " "
            if char in VARIATION_SELECTORS
            or unicodedata.category(char) in UNSPOKEN_UNICODE_CATEGORIES
            else char
        )
        for char in text
    )
    return " ".join(sanitized.split())[:maximum_chars].rstrip()


def select_speech_delivery(text: str) -> SpeechDelivery:
    """Choose one restrained delivery style from the completed spoken reply."""
    clean_text = text.strip()
    if _CONCERN_PATTERN.search(clean_text):
        return _DELIVERIES["caring"]
    if _CHEERFUL_PATTERN.search(clean_text):
        return _DELIVERIES["cheerful"]
    if _SERIOUS_PATTERN.search(clean_text):
        return _DELIVERIES["serious"]
    if _CURIOUS_PATTERN.search(clean_text):
        return _DELIVERIES["curious"]
    return _DELIVERIES["natural"]

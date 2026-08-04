import unicodedata

UNSPOKEN_UNICODE_CATEGORIES = {"Cf", "Cs", "Co", "Cn", "Sk", "So"}
VARIATION_SELECTORS = {"\ufe0e", "\ufe0f"}


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

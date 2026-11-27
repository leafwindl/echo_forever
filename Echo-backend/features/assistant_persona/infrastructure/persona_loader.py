"""Load the Echo persona asset from Markdown.

The Markdown files are the single content source; this loader is deliberately
strict so a missing section fails at startup instead of silently rendering an
empty personality.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from features.assistant_persona.domain.entities import (
    AssistantPersona,
    AssistantPersonaNotFoundError,
)

_ASSET_DIR = Path(__file__).resolve().parents[3] / "prompts" / "personas" / "echo"
_PERSONA_PATH = _ASSET_DIR / "persona.md"
_EXAMPLES_PATH = _ASSET_DIR / "examples.md"
_SUPPORTED_VERSION = "echo-persona-v5"

_REQUIRED_SECTIONS = (
    "稳定特点",
    "表达原则",
    "允许的自我披露",
    "禁止的自我声称",
)


class PersonaAssetError(ValueError):
    """Raised when the persona asset is malformed."""


@dataclass(frozen=True)
class _ParsedMarkdown:
    metadata: dict[str, str]
    sections: dict[str, tuple[str, ...]]


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        raise PersonaAssetError("persona.md must start with YAML front matter")
    end = text.find("\n---", 4)
    if end < 0:
        raise PersonaAssetError("persona.md front matter is not closed")
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        key, separator, value = clean.partition(":")
        if not separator:
            raise PersonaAssetError(f"invalid front matter line: {line!r}")
        metadata[key.strip()] = value.strip()
    return metadata, text[end + 4 :]


def _parse_persona_markdown(text: str) -> _ParsedMarkdown:
    metadata, body = _parse_front_matter(text)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        if line.startswith("# "):
            current = line[2:].strip()
            if current in sections:
                raise PersonaAssetError(f"duplicate section: {current}")
            sections[current] = []
            continue
        if current is None:
            continue
        clean = line.strip()
        if clean.startswith("- "):
            value = clean[2:].strip()
            if value:
                sections[current].append(value)

    missing = [name for name in _REQUIRED_SECTIONS if not sections.get(name)]
    if missing:
        raise PersonaAssetError(f"persona.md missing sections: {', '.join(missing)}")
    unknown = [name for name in sections if name not in _REQUIRED_SECTIONS]
    if unknown:
        raise PersonaAssetError(f"persona.md has unknown sections: {', '.join(unknown)}")

    for key in ("persona_id", "version", "name", "role"):
        if not metadata.get(key):
            raise PersonaAssetError(f"persona.md front matter missing {key}")

    return _ParsedMarkdown(
        metadata=metadata,
        sections={name: tuple(sections[name]) for name in _REQUIRED_SECTIONS},
    )


def _parse_examples_markdown(text: str) -> tuple[tuple[str, str], ...]:
    examples: list[tuple[str, str]] = []
    user: str | None = None
    reply_lines: list[str] = []

    def flush() -> None:
        nonlocal user, reply_lines
        if user and reply_lines:
            examples.append((user, "\n".join(reply_lines)))
        user = None
        reply_lines = []

    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("## "):
            flush()
            continue
        if clean.startswith("用户："):
            if user or reply_lines:
                flush()
            user = clean[3:].strip()
            continue
        if clean.startswith("Echo：") and user:
            reply_lines.append(clean[5:].strip())
    flush()

    if not examples:
        raise PersonaAssetError("examples.md contains no user/Echo pairs")
    return tuple(examples)


@lru_cache(maxsize=1)
def load_echo_persona(version: str = _SUPPORTED_VERSION) -> AssistantPersona:
    if version != _SUPPORTED_VERSION:
        raise AssistantPersonaNotFoundError(f"Unknown assistant persona version: {version}")

    if not _PERSONA_PATH.exists():
        raise PersonaAssetError(f"persona asset not found: {_PERSONA_PATH}")

    parsed = _parse_persona_markdown(_PERSONA_PATH.read_text(encoding="utf-8"))
    metadata = parsed.metadata
    if not _EXAMPLES_PATH.exists():
        raise PersonaAssetError(f"persona examples not found: {_EXAMPLES_PATH}")
    examples = _parse_examples_markdown(_EXAMPLES_PATH.read_text(encoding="utf-8"))

    return AssistantPersona(
        persona_id=metadata["persona_id"],
        version=metadata["version"],
        name=metadata["name"],
        role=metadata["role"],
        traits=parsed.sections["稳定特点"],
        conversation_principles=parsed.sections["表达原则"],
        allowed_self_disclosures=parsed.sections["允许的自我披露"],
        forbidden_claims=parsed.sections["禁止的自我声称"],
        dialogue_examples=examples,
    )


@lru_cache(maxsize=1)
def load_echo_examples() -> tuple[tuple[str, str], ...]:
    """读取示例资产；v5 已进合同，此入口保留给评测/调试单独取用。"""
    if not _EXAMPLES_PATH.exists():
        raise PersonaAssetError(f"persona examples not found: {_EXAMPLES_PATH}")
    return _parse_examples_markdown(_EXAMPLES_PATH.read_text(encoding="utf-8"))


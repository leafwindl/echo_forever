from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from features.assistant_persona.public import get_assistant_persona
from features.chat.infrastructure.prompt_renderer import render_prompt_layers
from features.letters.domain.repositories import LetterRepository
from features.memory.public import list_memories, retrieve_relevant_memories
from features.persona.public import get_persona
from features.relationship.public import get_relationship_context
from features.study_focus.public import list_study_focus_evidence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LetterContextConfig:
    product_identity: str
    prompt_version: str
    assistant_persona_version: str
    persona_maximum_tokens: int
    memory_maximum_tokens: int
    summary_maximum_tokens: int
    memory_top_k: int
    memory_score_threshold: float
    target_minimum_chars: int
    target_maximum_chars: int


@dataclass(frozen=True)
class LetterContext:
    messages: list[dict[str, str]]
    source_message_ids: tuple[int, ...]
    user_message_ids: tuple[int, ...]
    source_memory_ids: tuple[str, ...]
    raw_message_count: int
    memory_count: int
    has_user_interaction: bool
    snapshot: dict[str, object]


class LetterContextAssembler:
    def __init__(
        self,
        repository: LetterRepository,
        config: LetterContextConfig,
        focus_loader: Callable = list_study_focus_evidence,
    ):
        self.repository = repository
        self.config = config
        self.focus_loader = focus_loader

    async def build(
        self,
        *,
        user_id: str,
        local_date: date,
        timezone_name: str,
    ) -> LetterContext:
        raw_messages = self.repository.source_messages(user_id, local_date, timezone_name)
        try:
            focus_sessions = self.focus_loader(user_id, local_date, timezone_name)
        except Exception:
            logger.warning(
                "Letter study focus evidence unavailable user_id=%s",
                user_id,
                exc_info=True,
            )
            focus_sessions = []
        user_text = "\n".join(
            str(row.get("content") or "").strip()
            for row in raw_messages
            if str(row.get("role")) == "user"
        )
        memories = await self._load_memories(user_id, user_text)
        persona = self._load_persona(user_id)
        relationship = self._load_relationship(user_id, persona)
        assistant_persona = get_assistant_persona(self.config.assistant_persona_version)

        evidence = self._build_evidence(raw_messages, timezone_name)
        focus_evidence = self._build_focus_evidence(focus_sessions)
        if focus_evidence:
            evidence = f"{evidence}\n\n{focus_evidence}"
        memory_ids = tuple(str(item.get("memory_id")) for item in memories if item.get("memory_id"))
        source_ids = tuple(int(row["id"]) for row in raw_messages)
        user_source_ids = tuple(
            int(row["id"])
            for row in raw_messages
            if str(row.get("role")) == "user"
            and (str(row.get("content") or "").strip() or bool(row.get("attachments")))
        )
        snapshot = self._build_snapshot(
            raw_messages,
            timezone_name,
            memory_ids=memory_ids,
        )
        snapshot["study_focus"] = self._focus_snapshot(focus_sessions)
        messages = render_prompt_layers(
            product_identity=self.config.product_identity,
            persona=persona,
            long_term_memories=memories,
            conversation_summary="",
            prompt_version=self.config.prompt_version,
            persona_maximum_tokens=self.config.persona_maximum_tokens,
            memory_maximum_tokens=self.config.memory_maximum_tokens,
            summary_maximum_tokens=self.config.summary_maximum_tokens,
            assistant_persona=assistant_persona,
            relationship=relationship,
            conversation_mode="daily_letter",
        )
        messages.extend(
            [
                {
                    "role": "system",
                    "content": (
                        "[DAILY_LETTER_TASK]\n"
                        f"回顾日期: {local_date.isoformat()}\n"
                        f"目标字数: {self.config.target_minimum_chars}-"
                        f"{self.config.target_maximum_chars}\n"
                        "请把证据组织成一封自然的 Echo 来信。不要逐条总结；必须加入一段"
                        "有依据的 Echo 观察和想法。事实、推测和观点要区分，不能把旧记忆写成"
                        "昨日发生的事情。\n[/DAILY_LETTER_TASK]"
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "[DAILY_LETTER_BRIEF]\n"
                        f"{self._format_snapshot(snapshot)}\n"
                        "Brief 只用于筛选和组织证据，不代表其中的候选内容一定要写入正文。"
                        "[/DAILY_LETTER_BRIEF]"
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "[DAILY_LETTER_EVIDENCE]\n"
                        f"{evidence}\n"
                        "证据中的 message_id 是可追溯来源；只引用证据支持的事实。"
                        "[/DAILY_LETTER_EVIDENCE]"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "现在请完成这封每日来信。输出严格 JSON，不要输出任何额外说明。"
                    ),
                },
            ]
        )
        return LetterContext(
            messages=messages,
            source_message_ids=source_ids,
            user_message_ids=user_source_ids,
            source_memory_ids=memory_ids,
            raw_message_count=len(raw_messages),
            memory_count=len(memories),
            has_user_interaction=bool(user_source_ids or focus_sessions),
            snapshot=snapshot,
        )

    async def _load_memories(self, user_id: str, query: str) -> list[dict[str, object]]:
        clean_query = query.strip()[:6000]
        if not clean_query:
            return []
        try:
            memories = await retrieve_relevant_memories(
                user_id=user_id,
                query=clean_query,
                top_k=min(self.config.memory_top_k, 8),
                score_threshold=self.config.memory_score_threshold,
            )
            if memories:
                return [dict(item) for item in memories]
        except Exception:
            logger.warning("Letter memory retrieval unavailable user_id=%s", user_id, exc_info=True)
        try:
            result = list_memories(user_id=user_id, memory_status="active", limit=8)
            return [
                {
                    "memory_id": item.memory_id,
                    "memory_type": item.memory_type,
                    "content": item.content,
                    "importance": item.importance.value,
                    "updated_at": item.updated_at,
                }
                for item in result.memories
            ]
        except Exception:
            logger.warning("Letter memory fallback unavailable user_id=%s", user_id, exc_info=True)
            return []

    @staticmethod
    def _load_persona(user_id: str):
        try:
            return get_persona(user_id)
        except Exception:
            logger.warning("Letter persona loading unavailable user_id=%s", user_id, exc_info=True)
            return None

    @staticmethod
    def _load_relationship(user_id: str, persona):
        try:
            return get_relationship_context(
                user_id=user_id,
                user_message="根据昨日交流写每日来信",
                relationship_pace=(
                    persona.relationship_pace if persona and persona.enabled else "natural"
                ),
                affection_style=(
                    persona.affection_style if persona and persona.enabled else "contextual"
                ),
            )
        except Exception:
            logger.warning(
                "Letter relationship loading unavailable user_id=%s",
                user_id,
                exc_info=True,
            )
            return None

    @staticmethod
    def _build_evidence(rows: list[dict[str, Any]], timezone_name: str) -> str:
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            zone = None
        sessions: list[list[dict[str, Any]]] = []
        last_at: datetime | None = None
        for row in rows:
            current_at = _aware_utc(row.get("created_at"))
            if not sessions or (
                last_at is not None
                and current_at is not None
                and (current_at - last_at).total_seconds() > 1800
            ):
                sessions.append([])
            sessions[-1].append(row)
            last_at = current_at

        evidence: list[str] = [f"消息总数: {len(rows)}；连续会话数: {len(sessions)}"]
        for index, session in enumerate(sessions, start=1):
            evidence.append(f"\n[SESSION {index}]")
            for row in session:
                created_at = _aware_utc(row.get("created_at"))
                if zone is not None and created_at is not None:
                    created_at = created_at.astimezone(zone)
                time_text = created_at.strftime("%H:%M") if created_at else "未知时间"
                role = "用户" if row.get("role") == "user" else "Echo"
                content = str(row.get("content") or "").strip()
                if not content and row.get("message_type") == "sticker":
                    content = "（发送了表情包）"
                attachments = row.get("attachments") or []
                tags: list[str] = []
                for attachment in attachments:
                    if not isinstance(attachment, dict):
                        continue
                    raw_tags = attachment.get("semantic_tags") or []
                    if isinstance(raw_tags, list):
                        tags.extend(str(tag).strip() for tag in raw_tags if str(tag).strip())
                if tags:
                    content = f"{content} [表情语义: {'、'.join(dict.fromkeys(tags))}]".strip()
                content = content[:1200]
                evidence.append(
                    f"message_id={row.get('id')} time={time_text} role={role}: {content}"
                )
        return "\n".join(evidence)[:36000]

    @staticmethod
    def _build_snapshot(
        rows: list[dict[str, Any]],
        timezone_name: str,
        *,
        memory_ids: tuple[str, ...],
    ) -> dict[str, object]:
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            zone = UTC

        sessions: list[dict[str, object]] = []
        current: list[dict[str, Any]] = []
        last_at: datetime | None = None
        for row in rows:
            created_at = _aware_utc(row.get("created_at"))
            if (
                current
                and last_at is not None
                and created_at is not None
                and (created_at - last_at).total_seconds() > 1800
            ):
                sessions.append(_session_snapshot(current, zone))
                current = []
            current.append(row)
            last_at = created_at
        if current:
            sessions.append(_session_snapshot(current, zone))

        return {
            "message_count": len(rows),
            "session_count": len(sessions),
            "sessions": sessions,
            "source_memory_ids": list(memory_ids),
        }

    @staticmethod
    def _build_focus_evidence(sessions) -> str:
        if not sessions:
            return ""
        lines = ["[STUDY_FOCUS_EVIDENCE]", f"学习时段数: {len(sessions)}"]
        total_seconds = 0
        for session in sessions:
            total_seconds += session.actual_duration_seconds
            ended = session.ended_at.astimezone(UTC) if session.ended_at else None
            time_text = ended.strftime("%H:%M UTC") if ended else "未知时间"
            goal = f"；短目标: {session.short_goal}" if session.short_goal else ""
            lines.append(
                f"focus_session_id={session.session_id} time={time_text} "
                f"status={session.status} activity={session.activity_type} "
                f"actual_seconds={session.actual_duration_seconds}{goal}"
            )
        lines.append(f"实际学习总时长: {total_seconds} 秒")
        lines.append(
            "这些是 APP 的确定性计时记录，只能说明用户开启并运行了学习时段；"
            "不能据此断言具体学习目标已经完成。"
        )
        lines.append("[/STUDY_FOCUS_EVIDENCE]")
        return "\n".join(lines)

    @staticmethod
    def _focus_snapshot(sessions) -> dict[str, object]:
        return {
            "session_count": len(sessions),
            "total_actual_duration_seconds": sum(
                session.actual_duration_seconds for session in sessions
            ),
            "completed_count": sum(session.status == "completed" for session in sessions),
            "ended_early_count": sum(session.status == "ended_early" for session in sessions),
            "session_ids": [session.session_id for session in sessions],
        }

    @staticmethod
    def _format_snapshot(snapshot: dict[str, object]) -> str:
        lines = [
            f"消息数: {snapshot.get('message_count', 0)}",
            f"会话段数: {snapshot.get('session_count', 0)}",
        ]
        focus = snapshot.get("study_focus")
        if isinstance(focus, dict):
            lines.append(
                "学习记录: "
                f"{focus.get('session_count', 0)} 段，"
                f"共 {focus.get('total_actual_duration_seconds', 0)} 秒"
            )
        sessions = snapshot.get("sessions")
        if isinstance(sessions, list):
            for index, session in enumerate(sessions, start=1):
                if not isinstance(session, dict):
                    continue
                lines.append(
                    f"会话{index} {session.get('time_range', '未知时间')}："
                    f"代表消息 {session.get('representative_message_ids', [])}；"
                    f"未完成提问 {session.get('open_question_message_ids', [])}；"
                    f"情绪/选择候选 {session.get('salient_message_ids', [])}"
                )
                excerpts = session.get("candidate_excerpts")
                if isinstance(excerpts, list):
                    for excerpt in excerpts:
                        if not isinstance(excerpt, dict):
                            continue
                        lines.append(
                            "候选消息 "
                            f"{excerpt.get('message_id')} ({excerpt.get('role')}): "
                            f"{excerpt.get('content')}"
                        )
        return "\n".join(lines)


def _aware_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _session_snapshot(rows: list[dict[str, Any]], zone: object) -> dict[str, object]:
    timestamps = [_aware_utc(row.get("created_at")) for row in rows]
    present = [value.astimezone(zone) for value in timestamps if value is not None]
    if present:
        time_range = f"{present[0].strftime('%H:%M')}-{present[-1].strftime('%H:%M')}"
    else:
        time_range = "未知时间"

    message_ids = [int(row["id"]) for row in rows]
    representative = list(dict.fromkeys([*message_ids[:2], *message_ids[-2:]]))
    open_questions: list[int] = []
    salient: list[int] = []
    markers = ("想", "要", "决定", "准备", "希望", "担心", "开心", "难过", "累", "但是")
    for row in rows:
        content = str(row.get("content") or "").strip()
        message_id = int(row["id"])
        if str(row.get("role")) == "user" and ("?" in content or "？" in content):
            open_questions.append(message_id)
        if str(row.get("role")) == "user" and any(marker in content for marker in markers):
            salient.append(message_id)
    candidate_ids = list(
        dict.fromkeys(
            [*salient, *open_questions, *representative]
        )
    )[:8]
    rows_by_id = {int(row["id"]): row for row in rows}
    candidate_excerpts = [
        {
            "message_id": message_id,
            "role": "用户" if rows_by_id[message_id].get("role") == "user" else "Echo",
            "content": _brief_content(rows_by_id[message_id]),
        }
        for message_id in candidate_ids
        if message_id in rows_by_id
    ]
    return {
        "time_range": time_range,
        "message_ids": message_ids,
        "representative_message_ids": representative,
        "open_question_message_ids": open_questions[:8],
        "salient_message_ids": salient[:12],
        "candidate_excerpts": candidate_excerpts,
    }


def _brief_content(row: dict[str, Any]) -> str:
    content = str(row.get("content") or "").strip()
    if not content and row.get("message_type") == "sticker":
        content = "（发送了表情包）"
    tags: list[str] = []
    for attachment in row.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        raw_tags = attachment.get("semantic_tags") or []
        if isinstance(raw_tags, list):
            tags.extend(str(tag).strip() for tag in raw_tags if str(tag).strip())
    if tags:
        content = f"{content} [表情语义: {'、'.join(dict.fromkeys(tags))}]".strip()
    return content[:180]

from datetime import date

from features.study_focus.infrastructure.postgres_repository import (
    PostgresStudyFocusRepository,
)


def list_study_focus_evidence(user_id: str, local_date: date, timezone_name: str):
    return PostgresStudyFocusRepository().sessions_for_local_date(
        user_id,
        local_date,
        timezone_name,
    )


__all__ = ["list_study_focus_evidence"]

from __future__ import annotations

from functools import lru_cache

from features.user_profile.domain.entities import UserProfile
from features.user_profile.infrastructure.postgres_repository import (
    PostgresUserProfileRepository,
)


@lru_cache(maxsize=1)
def _repository() -> PostgresUserProfileRepository:
    return PostgresUserProfileRepository()


def get_user_profile(user_id: str) -> UserProfile | None:
    """读取 Echo 对用户的长期刻画；没有时返回 None。"""
    return _repository().get(user_id)


def update_user_profile(user_id: str, patch: dict[str, object]) -> UserProfile:
    """增量更新用户画像；只写传入的字段。"""
    return _repository().upsert_patch(user_id, patch)


__all__ = ["UserProfile", "get_user_profile", "update_user_profile"]

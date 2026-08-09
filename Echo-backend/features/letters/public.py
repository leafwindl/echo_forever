from datetime import UTC, datetime

from features.letters.infrastructure.container import get_letter_generator, get_letter_repository


async def generate_due_letters() -> int:
    return await get_letter_generator().execute(datetime.now(UTC))


def publish_due_letters() -> int:
    return get_letter_repository().publish_due(datetime.now(UTC))


__all__ = ["generate_due_letters", "publish_due_letters"]

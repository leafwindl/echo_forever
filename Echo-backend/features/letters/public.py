from features.letters.infrastructure.container import get_letter_generator


async def generate_due_letters() -> int:
    return await get_letter_generator().execute()


__all__ = ["generate_due_letters"]

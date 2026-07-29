from functools import lru_cache

from features.letters.application.generate_letters import GenerateDueLetters
from features.letters.infrastructure.postgres_repository import PostgresLetterRepository
from providers.llm_provider import get_llm_provider


@lru_cache(maxsize=1)
def get_letter_generator() -> GenerateDueLetters:
    return GenerateDueLetters(PostgresLetterRepository(), get_llm_provider())


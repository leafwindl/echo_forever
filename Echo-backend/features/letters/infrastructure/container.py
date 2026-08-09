import logging
import mimetypes
from functools import lru_cache
from pathlib import Path

from providers.minimax_image_provider import (
    MiniMaxImageGenerationProvider,
    MiniMaxImageProviderConfig,
)
from shared.config import settings
from shared.storage.cos_storage import CosObjectStorage, get_cos_object_storage

from features.letters.application.assemble_context import (
    LetterContextAssembler,
    LetterContextConfig,
)
from features.letters.application.generate_image import (
    GenerateLetterImage,
    LetterImagePolicy,
)
from features.letters.application.generate_letters import (
    GenerateDueLetters,
    LetterGenerationPolicy,
)
from features.letters.infrastructure.postgres_repository import PostgresLetterRepository

logger = logging.getLogger(__name__)

DEFAULT_MINIMAX_IMAGE_BASE_URL = "https://api.minimaxi.com/v1/image_generation"
DEFAULT_MINIMAX_IMAGE_MODEL = "image-01"


@lru_cache(maxsize=1)
def get_letter_repository() -> PostgresLetterRepository:
    return PostgresLetterRepository()


@lru_cache(maxsize=1)
def get_letter_image_generator() -> GenerateLetterImage:
    configured = _image_configuration_complete()
    enabled = settings.letter_image_generation_enabled and configured
    storage: CosObjectStorage | None = None
    if enabled:
        try:
            storage = get_cos_object_storage()
        except Exception:
            logger.warning("Daily letter COS storage is unavailable", exc_info=True)

    reference_asset = settings.letter_image_reference_asset.strip()
    reference_storage_key = _reference_storage_key(storage, reference_asset) if enabled else ""
    base_url = settings.minimax_image_base_url.strip() or DEFAULT_MINIMAX_IMAGE_BASE_URL
    model = settings.minimax_image_model.strip() or DEFAULT_MINIMAX_IMAGE_MODEL
    provider_config = MiniMaxImageProviderConfig(
        api_key=settings.minimax_image_api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=settings.minimax_image_timeout_seconds,
    )
    policy = LetterImagePolicy(
        enabled=enabled,
        aspect_ratio=settings.letter_image_aspect_ratio,
        maximum_attempts=settings.letter_image_max_attempts,
        maximum_bytes=settings.letter_image_max_bytes,
        timeout_seconds=settings.minimax_image_timeout_seconds,
        provider_name="minimax",
        model=model,
        reference_version=(
            Path(reference_asset).name if reference_asset else "echo-reference-unconfigured"
        ),
        reference_storage_key=reference_storage_key,
    )
    return GenerateLetterImage(
        MiniMaxImageGenerationProvider(provider_config),
        storage,
        policy,
    )


@lru_cache(maxsize=1)
def get_letter_generator() -> GenerateDueLetters:
    repository = get_letter_repository()
    context_config = LetterContextConfig(
        product_identity=settings.system_prompt,
        prompt_version=settings.prompt_version,
        assistant_persona_version=settings.assistant_persona_version,
        persona_maximum_tokens=settings.persona_prompt_max_tokens,
        memory_maximum_tokens=settings.memory_prompt_max_tokens,
        summary_maximum_tokens=settings.summary_prompt_max_tokens,
        memory_top_k=settings.memory_vector_top_k,
        memory_score_threshold=settings.memory_vector_score_threshold,
        target_minimum_chars=settings.daily_letter_target_min_chars,
        target_maximum_chars=settings.daily_letter_target_max_chars,
    )
    generation_policy = LetterGenerationPolicy(
        minimum_chars=settings.daily_letter_target_min_chars,
        maximum_chars=settings.daily_letter_target_max_chars,
        batch_size=settings.daily_letter_worker_batch_size,
        context_version=settings.daily_letter_context_version,
    )
    return GenerateDueLetters(
        repository,
        LetterContextAssembler(repository, context_config),
        get_letter_image_generator(),
        generation_policy,
    )


def _image_configuration_complete() -> bool:
    if not settings.letter_image_generation_enabled:
        return False
    required = {
        "MINIMAX_IMAGE_API_KEY": settings.minimax_image_api_key,
        "LETTER_IMAGE_REFERENCE_ASSET": settings.letter_image_reference_asset,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        logger.warning(
            "Daily letter image generation disabled; missing settings: %s",
            ", ".join(missing),
        )
        return False
    if not Path(settings.letter_image_reference_asset).is_file():
        logger.warning(
            "Daily letter image generation disabled; reference asset is unavailable"
        )
        return False
    return True


def _reference_storage_key(
    storage: CosObjectStorage | None,
    reference_asset: str,
) -> str:
    if storage is None or not reference_asset:
        return ""
    path = Path(reference_asset)
    try:
        content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        storage_key = storage.put_file(
            f"assets/echo-reference/{path.name}",
            path,
            content_type,
            cache_control="private, max-age=300",
        )
        return storage_key
    except Exception:
        logger.warning("Daily letter reference image upload is unavailable", exc_info=True)
        return ""

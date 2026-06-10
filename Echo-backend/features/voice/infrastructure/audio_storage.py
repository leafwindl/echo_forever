import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from shared.config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[3]
STATIC_VOICE_DIR = BASE_DIR / "static" / "voices"
VOICE_UPLOAD_DIR = STATIC_VOICE_DIR / "uploads"
VOICE_GENERATED_DIR = STATIC_VOICE_DIR / "generated"
LEGACY_VOICE_GENERATED_DIR = STATIC_VOICE_DIR


@dataclass(frozen=True)
class VoiceAudioCleanupResult:
    scanned: int = 0
    deleted: int = 0
    failed: int = 0
    released_bytes: int = 0

    def merge(self, other: "VoiceAudioCleanupResult") -> "VoiceAudioCleanupResult":
        return VoiceAudioCleanupResult(
            scanned=self.scanned + other.scanned,
            deleted=self.deleted + other.deleted,
            failed=self.failed + other.failed,
            released_bytes=self.released_bytes + other.released_bytes,
        )


def get_voice_storage_dir() -> Path:
    STATIC_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    return STATIC_VOICE_DIR


def get_voice_upload_dir() -> Path:
    VOICE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return VOICE_UPLOAD_DIR


def get_voice_generated_dir() -> Path:
    VOICE_GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    return VOICE_GENERATED_DIR


def save_upload_audio_file(audio_bytes: bytes, suffix: str = ".mp3") -> str:
    filename = f"{uuid.uuid4().hex}{_normalize_suffix(suffix)}"
    filepath = get_voice_upload_dir() / filename
    filepath.write_bytes(audio_bytes)
    return str(filepath)


async def save_audio_file(audio_bytes: bytes) -> str:
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = get_voice_generated_dir() / filename
    filepath.write_bytes(audio_bytes)
    return f"{settings.static_url_prefix}/static/voices/generated/{filename}"


def delete_upload_audio_file(audio_path: str) -> bool:
    filepath = Path(audio_path)
    if not _is_path_within(filepath, get_voice_upload_dir()):
        logger.warning("Refused to delete voice upload outside upload dir: %s", audio_path)
        return False

    try:
        filepath.unlink(missing_ok=True)
        return True
    except OSError:
        logger.warning("Failed to delete voice upload: %s", audio_path, exc_info=True)
        return False


def cleanup_expired_voice_audio_files(
    *,
    now: float | None = None,
    batch_size: int | None = None,
) -> VoiceAudioCleanupResult:
    cleanup_batch_size = batch_size if batch_size is not None else settings.voice_cleanup_batch_size
    current_time = now if now is not None else time.time()

    result = cleanup_expired_audio_files_in_dir(
        directory=get_voice_upload_dir(),
        retention_seconds=settings.voice_upload_retention_seconds,
        batch_size=cleanup_batch_size,
        now=current_time,
    )
    result = result.merge(
        cleanup_expired_audio_files_in_dir(
            directory=get_voice_generated_dir(),
            retention_seconds=settings.voice_generated_retention_seconds,
            batch_size=cleanup_batch_size,
            now=current_time,
        )
    )
    return result.merge(
        cleanup_expired_audio_files_in_dir(
            directory=LEGACY_VOICE_GENERATED_DIR,
            retention_seconds=settings.voice_generated_retention_seconds,
            batch_size=cleanup_batch_size,
            now=current_time,
            include_nested=False,
        )
    )


def cleanup_expired_audio_files_in_dir(
    *,
    directory: Path,
    retention_seconds: int,
    batch_size: int,
    now: float | None = None,
    include_nested: bool = False,
) -> VoiceAudioCleanupResult:
    if retention_seconds < 0 or batch_size <= 0 or not directory.exists():
        return VoiceAudioCleanupResult()

    current_time = now if now is not None else time.time()
    cutoff_time = current_time - retention_seconds
    scanned = 0
    deleted = 0
    failed = 0
    released_bytes = 0

    paths = directory.rglob("*.mp3") if include_nested else directory.glob("*.mp3")
    candidates = []
    for filepath in paths:
        try:
            candidates.append((filepath.stat().st_mtime, filepath))
        except OSError:
            failed += 1

    for _, filepath in sorted(candidates, key=lambda item: item[0]):
        if scanned >= batch_size:
            break
        scanned += 1

        try:
            stat_result = filepath.stat()
        except OSError:
            failed += 1
            continue

        if stat_result.st_mtime > cutoff_time:
            continue

        if not _is_path_within(filepath, directory):
            logger.warning("Refused to delete voice audio outside cleanup dir: %s", filepath)
            failed += 1
            continue

        try:
            filepath.unlink()
            deleted += 1
            released_bytes += stat_result.st_size
        except OSError:
            failed += 1
            logger.warning("Failed to cleanup expired voice audio: %s", filepath, exc_info=True)

    return VoiceAudioCleanupResult(
        scanned=scanned,
        deleted=deleted,
        failed=failed,
        released_bytes=released_bytes,
    )


def _normalize_suffix(suffix: str) -> str:
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    if "/" in normalized_suffix or "\\" in normalized_suffix or normalized_suffix == ".":
        return ".mp3"
    return normalized_suffix


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

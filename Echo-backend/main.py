import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from db.postgres_schema import init_db
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from features.assistant_persona.public import get_assistant_persona
from features.auth.interface.router import router as auth_router
from features.chat.interface.router import router as chat_router
from features.letters.interface.router import router as letters_router
from features.letters.public import generate_due_letters
from features.memory.interface.router import router as memory_router
from features.memory.public import resume_pending_memory_extraction_jobs
from features.persona.interface.router import router as persona_router
from features.relationship.interface.router import router as relationship_router
from features.releases.interface.router import router as releases_router
from features.stickers.interface.router import router as stickers_router
from features.stickers.public import generate_pending_stickers
from features.system.interface.router import router as health_router
from features.voice.interface.router import router as voice_router
from features.voice.public import cleanup_expired_voice_audio
from shared.config import settings
from shared.security import install_sensitive_data_filter

load_dotenv()

logging.basicConfig(level=logging.INFO)
install_sensitive_data_filter()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


async def run_voice_audio_cleanup_once() -> None:
    try:
        result = await asyncio.to_thread(cleanup_expired_voice_audio)
    except Exception:
        logger.warning("Voice audio cleanup failed", exc_info=True)
        return

    if result.deleted or result.failed:
        logger.info(
            "Voice audio cleanup finished scanned=%s deleted=%s failed=%s released_bytes=%s",
            result.scanned,
            result.deleted,
            result.failed,
            result.released_bytes,
        )


async def run_voice_audio_cleanup_loop() -> None:
    interval_seconds = settings.voice_cleanup_interval_seconds
    while True:
        await asyncio.sleep(interval_seconds)
        await run_voice_audio_cleanup_once()


async def run_daily_letter_loop() -> None:
    while True:
        try:
            created = await generate_due_letters()
            if created:
                logger.info("Daily letter generation finished created=%s", created)
        except Exception:
            logger.warning("Daily letter worker failed", exc_info=True)
        await asyncio.sleep(settings.daily_letter_worker_interval_seconds)


async def run_sticker_generation_loop() -> None:
    while True:
        try:
            await generate_pending_stickers()
        except Exception:
            logger.warning("Sticker generation worker failed", exc_info=True)
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uvicorn installs its handlers after importing the app, so attach the filter again here.
    install_sensitive_data_filter()
    logger.info("Echo Backend 启动中...")
    init_db()
    logger.info("Database provider: PostgreSQL + pgvector")
    logger.info("Prompt version: %s", settings.prompt_version)
    assistant_persona = get_assistant_persona(settings.assistant_persona_version)
    logger.info("Assistant persona version: %s", assistant_persona.version)
    resumed_count = resume_pending_memory_extraction_jobs()
    if resumed_count:
        logger.info("Resumed %s pending memory extraction jobs", resumed_count)

    await run_voice_audio_cleanup_once()
    voice_cleanup_task: asyncio.Task[None] | None = None
    daily_letter_task: asyncio.Task[None] | None = None
    sticker_generation_task: asyncio.Task[None] | None = None
    if settings.voice_cleanup_interval_seconds > 0:
        voice_cleanup_task = asyncio.create_task(run_voice_audio_cleanup_loop())
    if settings.daily_letter_enabled:
        daily_letter_task = asyncio.create_task(run_daily_letter_loop())
    if settings.sticker_generation_enabled:
        sticker_generation_task = asyncio.create_task(run_sticker_generation_loop())

    try:
        yield
    finally:
        if voice_cleanup_task:
            voice_cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await voice_cleanup_task
        if daily_letter_task:
            daily_letter_task.cancel()
            with suppress(asyncio.CancelledError):
                await daily_letter_task
        if sticker_generation_task:
            sticker_generation_task.cancel()
            with suppress(asyncio.CancelledError):
                await sticker_generation_task
        logger.info("Echo Backend 已停止。")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Echo AI Backend",
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_api_docs else None,
        redoc_url="/redoc" if settings.enable_api_docs else None,
        openapi_url="/openapi.json" if settings.enable_api_docs else None,
    )

    @app.middleware("http")
    async def log_http_request(request: Request, call_next):
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.exception(
                "HTTP request failed method=%s path=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - started_at) * 1000
        log_level = logging.WARNING if response.status_code >= 500 else logging.INFO
        logger.log(
            log_level,
            "HTTP request method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Echo-Version"] = settings.app_version
        return response

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(memory_router)
    app.include_router(persona_router)
    app.include_router(relationship_router)
    app.include_router(voice_router)
    app.include_router(letters_router)
    app.include_router(stickers_router)
    app.include_router(releases_router)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()

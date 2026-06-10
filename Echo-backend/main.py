import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db.connection import get_db_path
from db.schema import init_db
from features.auth.interface.router import router as auth_router
from features.chat.interface.router import router as chat_router
from features.memory.interface.router import router as memory_router
from features.memory.public import resume_pending_memory_extraction_jobs
from features.system.interface.router import router as health_router
from features.voice.interface.router import router as voice_router
from features.voice.public import cleanup_expired_voice_audio
from shared.config import settings

load_dotenv()

logging.basicConfig(level=logging.INFO)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Echo Backend 启动中...")
    init_db()
    logger.info("SQLite database path: %s", get_db_path())
    resumed_count = resume_pending_memory_extraction_jobs()
    if resumed_count:
        logger.info("Resumed %s pending memory extraction jobs", resumed_count)

    await run_voice_audio_cleanup_once()
    voice_cleanup_task: asyncio.Task[None] | None = None
    if settings.voice_cleanup_interval_seconds > 0:
        voice_cleanup_task = asyncio.create_task(run_voice_audio_cleanup_loop())

    try:
        yield
    finally:
        if voice_cleanup_task:
            voice_cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await voice_cleanup_task
        logger.info("Echo Backend 已停止。")


def create_app() -> FastAPI:
    app = FastAPI(title="Echo AI Backend", lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(memory_router)
    app.include_router(voice_router)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()

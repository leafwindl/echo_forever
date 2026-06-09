import logging
from contextlib import asynccontextmanager
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

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Echo Backend 启动中...")
    init_db()
    logger.info("SQLite database path: %s", get_db_path())
    resumed_count = resume_pending_memory_extraction_jobs()
    if resumed_count:
        logger.info("Resumed %s pending memory extraction jobs", resumed_count)
    yield
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

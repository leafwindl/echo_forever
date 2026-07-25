from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from shared.config import settings

from features.persona.public import PERSONA_SCHEMA_VERSION
from features.system.public import is_database_ready

router = APIRouter(tags=["health"])


@router.get("/")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check():
    """依赖就绪检查；不会向调用方暴露数据库异常细节。"""
    if not is_database_ready():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "database": "unavailable"},
        )
    return {"status": "ready", "database": "ok"}


@router.get("/version")
async def version_info():
    return {
        "version": settings.app_version,
        "revision": settings.build_revision,
        "prompt_version": settings.prompt_version,
        "persona_schema_version": PERSONA_SCHEMA_VERSION,
    }

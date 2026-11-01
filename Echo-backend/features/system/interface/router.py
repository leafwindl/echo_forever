from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user

from features.persona.public import PERSONA_SCHEMA_VERSION
from features.relationship.public import RELATIONSHIP_SCHEMA_VERSION
from features.system.application.reset_companionship import ResetCompanionship
from features.system.public import is_database_ready

router = APIRouter(tags=["health"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


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


@router.post("/account/reset")
def reset_companionship(current_user: CurrentUserDependency):
    result = ResetCompanionship().execute(current_user.user_id)
    return asdict(result)


@router.get("/version")
async def version_info():
    return {
        "version": settings.app_version,
        "revision": settings.build_revision,
        "prompt_version": settings.prompt_version,
        "assistant_persona_version": settings.assistant_persona_version,
        "persona_schema_version": PERSONA_SCHEMA_VERSION,
        "relationship_schema_version": RELATIONSHIP_SCHEMA_VERSION,
    }

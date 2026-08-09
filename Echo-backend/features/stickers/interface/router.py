from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from shared.config import settings
from shared.interface.dependencies import CurrentUser, get_current_user

from features.stickers.domain.services import normalize_tags, validate_image
from features.stickers.infrastructure.postgres_repository import PostgresStickerRepository
from features.stickers.infrastructure.vector_index import safe_upsert_sticker_embedding
from features.stickers.interface.schemas import (
    StickerGenerationRequest,
    StickerGenerationResponse,
    StickerListResponse,
    StickerResponse,
)

router = APIRouter(prefix="/stickers", tags=["stickers"])
repository = PostgresStickerRepository()
STATIC_ROOT = Path(__file__).resolve().parents[3] / "static" / "stickers"


def _response(item) -> StickerResponse:
    data = vars(item).copy()
    data["semantic_tags"] = list(item.semantic_tags)
    return StickerResponse(**data)


@router.get("", response_model=StickerListResponse)
def list_stickers(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    query: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
):
    return StickerListResponse(
        items=[
            _response(item)
            for item in repository.list(
                current_user.user_id,
                query,
                limit,
                include_echo=False,
                include_user=True,
            )
        ]
    )


@router.post("/upload", response_model=StickerResponse)
async def upload_sticker(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    file: UploadFile = File(...),
    description: str = Form(default="", max_length=300),
    tags: str = Form(default="", max_length=300),
):
    content = await file.read(settings.sticker_upload_max_bytes + 1)
    content_type = (file.content_type or "").lower()
    clean_description = description.strip()
    clean_tags = normalize_tags(tags.split(","))
    if not clean_description:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写表情包描述")
    if not clean_tags:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少填写一个语义标签")
    try:
        content_hash = validate_image(content, content_type, settings.sticker_upload_max_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    suffixes = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    suffix = suffixes[content_type]
    STATIC_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    target = STATIC_ROOT / filename
    target.write_bytes(content)
    item = repository.create_upload(
        current_user.user_id,
        f"stickers/{filename}",
        f"{settings.static_url_prefix.rstrip('/')}/static/stickers/{filename}",
        content_type,
        len(content),
        content_hash,
        clean_description,
        clean_tags,
    )
    return _response(item)


@router.post("/{sticker_id}/confirm-save", response_model=StickerResponse)
async def confirm_sticker(
    sticker_id: str,
    background_tasks: BackgroundTasks,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    item = repository.confirm(current_user.user_id, sticker_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="表情包不存在")
    background_tasks.add_task(safe_upsert_sticker_embedding, item)
    return _response(item)


@router.delete("/{sticker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sticker(
    sticker_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    storage_key = repository.delete(current_user.user_id, sticker_id)
    if not storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="表情包不存在")
    target = Path(__file__).resolve().parents[3] / "static" / storage_key
    target.unlink(missing_ok=True)


@router.post("/generations", response_model=StickerGenerationResponse)
def create_generation(
    request: StickerGenerationRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    if not settings.sticker_generation_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="表情包生成尚未配置")
    job_id = repository.create_generation_job(current_user.user_id, request.prompt, request.intent)
    return StickerGenerationResponse(job_id=job_id, status="pending")


@router.get("/generations/{job_id}", response_model=StickerGenerationResponse)
def get_generation(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    row = repository.generation_job(current_user.user_id, job_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成任务不存在")
    return StickerGenerationResponse(**row)

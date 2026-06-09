import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from features.memory.interface.schemas import (
    MemoryBackfillEmbeddingsRequest,
    MemoryBackfillEmbeddingsResponse,
    MemoryClearRequest,
    MemoryClearResponse,
    MemoryDeleteResponse,
    MemoryItem,
    MemoryListResponse,
)
from features.memory.public import (
    InvalidMemoryStatusError,
    Memory,
    MemoryNotFoundError,
    MemoryOperationError,
    MemoryValidationError,
    backfill_memory_embeddings,
    clear_memories,
    delete_memory,
    list_memories,
)
from shared.interface.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


def _memory_item_from_domain(memory: Memory) -> MemoryItem:
    return MemoryItem(
        memory_id=memory.memory_id,
        memory_type=memory.memory_type,
        content=memory.content,
        source_message_id=memory.source_message_id,
        confidence=memory.confidence,
        importance=memory.importance.value,
        status=memory.status,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        expires_at=memory.expires_at,
    )


@router.get("/list", response_model=MemoryListResponse)
async def memory_list(
    current_user: CurrentUser = Depends(get_current_user),
    memory_status: str = Query("active", alias="status"),
    limit: int = 50,
):
    """查看当前用户的长期记忆；默认只返回 active 记忆。"""
    try:
        result = list_memories(
            user_id=current_user.user_id,
            memory_status=memory_status,
            limit=limit,
        )
    except InvalidMemoryStatusError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return MemoryListResponse(
        memories=[_memory_item_from_domain(memory) for memory in result.memories],
        count=result.count,
    )


@router.delete("/{memory_id}", response_model=MemoryDeleteResponse)
async def memory_delete(memory_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """软删除单条长期记忆；删除后不会再进入 Context Builder。"""
    try:
        result = delete_memory(current_user.user_id, memory_id)
    except MemoryValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except MemoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except MemoryOperationError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    return MemoryDeleteResponse(memory_id=result.memory_id, status=result.status)


@router.post("/clear", response_model=MemoryClearResponse)
async def memory_clear(
    request: MemoryClearRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """清空当前用户长期记忆；不会删除聊天原始记录和会话摘要。"""
    del request
    result = clear_memories(current_user.user_id)
    return MemoryClearResponse(cleared_count=result.cleared_count)


@router.post("/backfill-embeddings", response_model=MemoryBackfillEmbeddingsResponse)
async def memory_backfill_embeddings(
    request: MemoryBackfillEmbeddingsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """为旧阶段已经存在的 active 长期记忆补齐 embedding。"""
    try:
        result = await backfill_memory_embeddings(current_user.user_id, limit=request.limit)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to backfill memory embeddings for user_id=%s", current_user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to backfill memory embeddings",
        ) from e

    return MemoryBackfillEmbeddingsResponse(backfilled_count=result.backfilled_count)

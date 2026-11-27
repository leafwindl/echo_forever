from typing import Annotated

from fastapi import APIRouter, Depends
from shared.interface.dependencies import CurrentUser, get_current_user

from features.relationship.interface.schemas import (
    RelationshipResponse,
    StageAdvanceResponse,
)
from features.relationship.public import (
    STAGE_LABELS,
    RelationshipState,
    StageAdvanceRequest,
    accept_stage_request,
    decline_stage_request,
    defer_stage_request,
    get_pending_stage_request,
    get_relationship_state,
    reset_relationship_state,
)

router = APIRouter(prefix="/relationship", tags=["relationship"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _stage_request_response(request: StageAdvanceRequest) -> StageAdvanceResponse:
    return StageAdvanceResponse(
        request_id=request.request_id,
        target_stage=request.target_stage,
        target_stage_label=STAGE_LABELS.get(request.target_stage, request.target_stage),
        status=request.status,
        created_at=request.created_at,
        expires_at=request.expires_at,
        cooldown_until=request.cooldown_until,
    )


def _response_from_domain(state: RelationshipState) -> RelationshipResponse:
    return RelationshipResponse(
        stage=state.stage,
        stage_label=STAGE_LABELS.get(state.stage, state.stage),
        interaction_turns=state.interaction_turns,
        active_days=state.active_days,
        affection_permission=state.affection_permission,
        schema_version=state.schema_version,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


@router.get("/me", response_model=RelationshipResponse)
def relationship_get(current_user: CurrentUserDependency) -> RelationshipResponse:
    return _response_from_domain(get_relationship_state(current_user.user_id))


@router.post("/me/reset", response_model=RelationshipResponse)
def relationship_reset(current_user: CurrentUserDependency) -> RelationshipResponse:
    return _response_from_domain(reset_relationship_state(current_user.user_id))


@router.get("/stage-requests/pending", response_model=StageAdvanceResponse | None)
def relationship_pending_stage_request(
    current_user: CurrentUserDependency,
) -> StageAdvanceResponse | None:
    request = get_pending_stage_request(current_user.user_id)
    return _stage_request_response(request) if request else None


@router.post("/stage-requests/{request_id}/accept", response_model=RelationshipResponse)
def relationship_accept_stage_request(
    request_id: str,
    current_user: CurrentUserDependency,
) -> RelationshipResponse:
    return _response_from_domain(accept_stage_request(current_user.user_id, request_id))


@router.post("/stage-requests/{request_id}/decline", response_model=StageAdvanceResponse)
def relationship_decline_stage_request(
    request_id: str,
    current_user: CurrentUserDependency,
) -> StageAdvanceResponse:
    return _stage_request_response(decline_stage_request(current_user.user_id, request_id))


@router.post("/stage-requests/{request_id}/defer", response_model=StageAdvanceResponse)
def relationship_defer_stage_request(
    request_id: str,
    current_user: CurrentUserDependency,
) -> StageAdvanceResponse:
    return _stage_request_response(defer_stage_request(current_user.user_id, request_id))

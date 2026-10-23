from typing import Annotated

from fastapi import APIRouter, Depends
from shared.interface.dependencies import CurrentUser, get_current_user

from features.relationship.interface.schemas import (
    RelationshipModeUpdateRequest,
    RelationshipResponse,
)
from features.relationship.public import (
    STAGE_LABELS,
    RelationshipState,
    get_relationship_state,
    reset_relationship_state,
    update_relationship_mode,
)

router = APIRouter(prefix="/relationship", tags=["relationship"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _response_from_domain(state: RelationshipState) -> RelationshipResponse:
    return RelationshipResponse(
        relationship_mode=state.relationship_mode,
        stage=state.stage,
        stage_label=STAGE_LABELS[state.stage],
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


@router.put("/me", response_model=RelationshipResponse)
def relationship_update_mode(
    request: RelationshipModeUpdateRequest,
    current_user: CurrentUserDependency,
) -> RelationshipResponse:
    return _response_from_domain(
        update_relationship_mode(current_user.user_id, request.relationship_mode)
    )

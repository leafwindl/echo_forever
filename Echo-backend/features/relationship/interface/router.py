from typing import Annotated

from fastapi import APIRouter, Depends
from shared.interface.dependencies import CurrentUser, get_current_user

from features.relationship.interface.schemas import (
    RelationshipModeUpdateRequest,
    RelationshipProposalResponse,
    RelationshipResponse,
)
from features.relationship.public import (
    RELATIONSHIP_DIRECTION_LABELS,
    RELATIONSHIP_TYPE_LABELS,
    STAGE_LABELS,
    RelationshipProposal,
    RelationshipState,
    accept_relationship_proposal,
    defer_relationship_proposal,
    decline_relationship_proposal,
    get_pending_relationship_proposal,
    get_relationship_state,
    reset_relationship_state,
    update_relationship_mode,
)

router = APIRouter(prefix="/relationship", tags=["relationship"])
CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _proposal_response(proposal: RelationshipProposal) -> RelationshipProposalResponse:
    return RelationshipProposalResponse(
        proposal_id=proposal.proposal_id,
        direction=proposal.direction,
        direction_label=RELATIONSHIP_DIRECTION_LABELS.get(proposal.direction, proposal.direction),
        status=proposal.status,
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
    )


def _response_from_domain(
    state: RelationshipState,
    pending: RelationshipProposal | None = None,
) -> RelationshipResponse:
    return RelationshipResponse(
        relationship_mode=state.relationship_mode,
        relationship_type=state.relationship_type,
        relationship_type_label=RELATIONSHIP_TYPE_LABELS.get(
            state.relationship_type, state.relationship_type
        ),
        stage=state.stage,
        stage_label=STAGE_LABELS[state.stage],
        interaction_turns=state.interaction_turns,
        active_days=state.active_days,
        affection_permission=state.affection_permission,
        pending_proposal=_proposal_response(pending) if pending else None,
        schema_version=state.schema_version,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


@router.get("/me", response_model=RelationshipResponse)
def relationship_get(current_user: CurrentUserDependency) -> RelationshipResponse:
    user_id = current_user.user_id
    return _response_from_domain(
        get_relationship_state(user_id),
        get_pending_relationship_proposal(user_id),
    )


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


@router.get("/proposals/pending", response_model=RelationshipProposalResponse | None)
def relationship_pending_proposal(
    current_user: CurrentUserDependency,
) -> RelationshipProposalResponse | None:
    proposal = get_pending_relationship_proposal(current_user.user_id)
    return _proposal_response(proposal) if proposal else None


@router.post("/proposals/{proposal_id}/accept", response_model=RelationshipResponse)
def relationship_accept_proposal(
    proposal_id: str,
    current_user: CurrentUserDependency,
) -> RelationshipResponse:
    state = accept_relationship_proposal(current_user.user_id, proposal_id)
    return _response_from_domain(state, get_pending_relationship_proposal(current_user.user_id))


@router.post("/proposals/{proposal_id}/defer", response_model=RelationshipProposalResponse)
def relationship_defer_proposal(
    proposal_id: str,
    current_user: CurrentUserDependency,
) -> RelationshipProposalResponse:
    return _proposal_response(
        defer_relationship_proposal(current_user.user_id, proposal_id)
    )


@router.post("/proposals/{proposal_id}/decline", response_model=RelationshipProposalResponse)
def relationship_decline_proposal(
    proposal_id: str,
    current_user: CurrentUserDependency,
) -> RelationshipProposalResponse:
    return _proposal_response(
        decline_relationship_proposal(current_user.user_id, proposal_id)
    )

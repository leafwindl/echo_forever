from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from features.relationship.domain.entities import RelationshipState, StageAdvanceRequest
from features.relationship.interface.router import router
from shared.interface.dependencies import CurrentUser, get_current_user


def make_app(authenticated=True):
    app = FastAPI()
    app.include_router(router)
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser("current-user")
    return app


def test_old_mode_and_proposal_routes_are_removed():
    client = TestClient(make_app())
    assert client.put("/relationship/me", json={}).status_code == 405
    assert client.get("/relationship/proposals/pending").status_code == 404


def test_pending_stage_request_is_rendered_with_target_label():
    request = StageAdvanceRequest(
        request_id="req-1",
        user_id="current-user",
        target_stage="ambiguous",
        status="pending",
    )
    with patch(
        "features.relationship.interface.router.get_pending_stage_request",
        return_value=request,
    ):
        response = TestClient(make_app()).get("/relationship/stage-requests/pending")

    assert response.status_code == 200
    assert response.json()["target_stage"] == "ambiguous"
    assert response.json()["target_stage_label"] == "暧昧"


def test_accept_stage_request_uses_authenticated_identity():
    accepted = RelationshipState(user_id="current-user", stage="ambiguous", affection=320)
    with patch(
        "features.relationship.interface.router.accept_stage_request",
        return_value=accepted,
    ) as accept:
        response = TestClient(make_app()).post(
            "/relationship/stage-requests/req-1/accept"
        )

    assert response.status_code == 200
    assert response.json()["stage"] == "ambiguous"
    assert response.json()["stage_label"] == "暧昧"
    accept.assert_called_once_with("current-user", "req-1")

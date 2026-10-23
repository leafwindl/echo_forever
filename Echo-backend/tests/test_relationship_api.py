from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from features.relationship.domain.entities import RelationshipState
from features.relationship.interface.router import router
from shared.interface.dependencies import CurrentUser, get_current_user


def make_app(authenticated=True):
    app = FastAPI()
    app.include_router(router)
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser("current-user")
    return app


def test_mode_update_uses_authenticated_identity_and_returns_the_saved_choice():
    saved = RelationshipState(user_id="current-user", relationship_mode="ai_partner")
    with patch(
        "features.relationship.interface.router.update_relationship_mode", return_value=saved
    ) as update:
        response = TestClient(make_app()).put(
            "/relationship/me",
            json={
                "relationship_mode": "ai_partner",
                "user_id": "someone-else",
            },
        )
    assert response.status_code == 200
    assert response.json()["relationship_mode"] == "ai_partner"
    assert response.json()["stage"] == "new"
    update.assert_called_once_with("current-user", "ai_partner")


def test_invalid_mode_and_unauthenticated_request_are_rejected_before_use_case():
    with patch("features.relationship.interface.router.update_relationship_mode") as update:
        response = TestClient(make_app()).put(
            "/relationship/me", json={"relationship_mode": "anything"}
        )
        assert response.status_code == 422
        response = TestClient(make_app(False)).put(
            "/relationship/me", json={"relationship_mode": "ai_partner"}
        )
        assert response.status_code == 401
        update.assert_not_called()

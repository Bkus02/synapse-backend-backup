"""API integration smoke tests covering Sprint B + Sprint F changes.

The Synapse FastAPI app is exercised with an in-memory SQLite engine. We override
the `get_session` dependency so that all routes share the same fixture session,
which keeps test data alive across requests without spinning up Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Ensure all models register on the metadata before create_all.
import app.core.models  # noqa: F401
import app.models.habit_matrix  # noqa: F401
from app.db.database import get_session
from app.main import app as fastapi_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    def _override_get_session() -> Iterator[Session]:
        yield session

    fastapi_app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(fastapi_app) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_session, None)
        session.close()
        engine.dispose()


def _register(client: TestClient, email: str = "alice@synapse.local") -> dict:
    r = client.post(
        "/users",
        json={
            "full_name": "Alice",
            "email": email,
            "password": "s3cret-passw0rd!",
            "height": 170,
            "weight": 65,
            "age": 30,
            "location": "Izmir",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _login(client: TestClient, email: str, password: str = "s3cret-passw0rd!") -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_returns_token_and_me_works(client: TestClient) -> None:
    user = _register(client)
    payload = _login(client, user["email"])
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["email"] == user["email"]

    me = client.get("/auth/me", headers=_auth(payload["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == user["email"]


def test_protected_routes_require_bearer_token(client: TestClient) -> None:
    assert client.get("/habits").status_code == 401
    assert client.get("/devices?environment_id=HXXXXXXX").status_code == 401
    assert client.get("/environments").status_code == 401
    assert client.get("/recommendations/active").status_code == 401


def test_daily_activity_only_returns_own_log(client: TestClient) -> None:
    alice = _register(client, email="alice@synapse.local")
    bob = _register(client, email="bob@synapse.local")
    alice_login = _login(client, alice["email"])

    # Own log is OK and pads to `days` length.
    own = client.get(
        f"/users/{alice['id']}/daily-activity?days=7",
        headers=_auth(alice_login["access_token"]),
    )
    assert own.status_code == 200
    body = own.json()
    assert body["user_id"] == alice["id"]
    assert len(body["days"]) == 7
    assert body["weekly_streak_count"] == 0

    # Cross-user read is forbidden.
    cross = client.get(
        f"/users/{bob['id']}/daily-activity",
        headers=_auth(alice_login["access_token"]),
    )
    assert cross.status_code == 403


def test_patch_user_requires_token(client: TestClient) -> None:
    user = _register(client)
    r = client.patch(f"/users/{user['id']}", json={"full_name": "Hacker"})
    assert r.status_code == 401


def test_list_users_requires_token(client: TestClient) -> None:
    assert client.get("/users").status_code == 401


def test_list_users_returns_only_self(client: TestClient) -> None:
    user = _register(client)
    token = _login(client, user["email"])["access_token"]
    listed = client.get("/users", headers=_auth(token))
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["id"] == user["id"]
    assert "password_hash" not in body[0]


def test_environment_admin_assigned_from_token(client: TestClient) -> None:
    alice = _register(client)
    auth = _auth(_login(client, alice["email"])["access_token"])

    r = client.post(
        "/environments",
        headers=auth,
        json={"name": "Alice Home", "location": "Izmir", "icon_key": "home"},
    )
    assert r.status_code == 200, r.text
    env = r.json()
    assert env["admin_id"] == alice["id"]
    assert env["id"].startswith("H")

    listed = client.get("/environments", headers=auth)
    assert listed.status_code == 200
    assert any(e["id"] == env["id"] for e in listed.json())

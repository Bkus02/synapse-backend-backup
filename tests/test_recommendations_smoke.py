"""Sprint E — recommendations/active token and empty state."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

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


def _register_and_token(client: TestClient) -> tuple[dict, str]:
    r = client.post(
        "/users",
        json={
            "full_name": "Rec User",
            "email": "rec@synapse.local",
            "password": "s3cret-passw0rd!",
        },
    )
    assert r.status_code == 200, r.text
    user = r.json()
    login = client.post(
        "/auth/login",
        json={"email": "rec@synapse.local", "password": "s3cret-passw0rd!"},
    )
    assert login.status_code == 200, login.text
    return user, login.json()["access_token"]


def test_active_recommendation_requires_token(client: TestClient) -> None:
    assert client.get("/recommendations/active").status_code == 401


def test_active_recommendation_empty_when_none_pending(client: TestClient) -> None:
    _user, token = _register_and_token(client)
    r = client.get(
        "/recommendations/active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.text.strip() in ("", "null")

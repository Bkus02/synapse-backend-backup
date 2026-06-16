"""Device on/off must survive PATCH then GET list."""

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


def test_patch_device_status_persists_on_list(client: TestClient) -> None:
    reg = client.post(
        "/users",
        json={
            "email": "dev-persist@synapse.local",
            "password": "s3cret-passw0rd!",
        },
    )
    assert reg.status_code == 200, reg.text
    login = client.post(
        "/auth/login",
        json={"email": "dev-persist@synapse.local", "password": "s3cret-passw0rd!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    env = client.post("/environments", headers=headers, json={"name": "Home"})
    env_id = env.json()["id"]

    created = client.post(
        "/devices",
        headers=headers,
        json={
            "environment_id": env_id,
            "type": "Lamp",
            "name": "lamba",
            "status": False,
        },
    )
    device_id = created.json()["id"]

    patch = client.patch(
        f"/devices/{device_id}",
        headers=headers,
        json={"status": True},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["status"] is True

    listed = client.get(f"/devices?environment_id={env_id}", headers=headers)
    assert listed.status_code == 200, listed.text
    row = next(d for d in listed.json() if d["id"] == device_id)
    assert row["status"] is True

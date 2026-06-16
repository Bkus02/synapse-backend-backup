"""API-level end-to-end flow: register → environment → device → habit → behavior log → streak."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_full_happy_path_register_to_streak(client: TestClient) -> None:
    email = f"e2e_{datetime.now(UTC).timestamp()}@synapse.local"
    reg = client.post(
        "/users",
        json={
            "full_name": "E2E User",
            "email": email,
            "password": "e2e-pass-123!",
            "height": 175,
            "weight": 70,
            "age": 25,
            "location": "Izmir",
        },
    )
    assert reg.status_code == 200, reg.text
    user = reg.json()

    login = client.post("/auth/login", json={"email": email, "password": "e2e-pass-123!"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = _auth(token)

    env = client.post(
        "/environments",
        headers=headers,
        json={"name": "E2E Home", "location": "Izmir", "icon_key": "home"},
    )
    assert env.status_code == 200, env.text
    env_id = env.json()["id"]

    device = client.post(
        "/devices",
        headers=headers,
        json={
            "environment_id": env_id,
            "type": "Lamp",
            "name": "Salon",
            "status": False,
        },
    )
    assert device.status_code == 200, device.text
    device_id = device.json()["id"]
    assert device.json()["status"] is False

    before_toggle = client.get(
        f"/users/{user['id']}/daily-activity?days=7",
        headers=headers,
    )
    assert before_toggle.status_code == 200
    assert before_toggle.json()["days"][-1]["active"] is False

    patch_on = client.patch(
        f"/devices/{device_id}",
        headers=headers,
        json={"status": True},
    )
    assert patch_on.status_code == 200, patch_on.text
    assert patch_on.json()["status"] is True

    logs = client.get("/behavior-logs", headers=headers)
    assert logs.status_code == 200
    toggle_logs = [
        row
        for row in logs.json()
        if row.get("device_id") == device_id and row.get("action") == "TurnOn"
    ]
    assert len(toggle_logs) >= 1

    habit = client.post(
        "/habits",
        headers=headers,
        json={
            "user_id": user["id"],
            "name": "Evening reading",
            "probability_score": "0.55",
            "is_active": True,
            "recurrence_type": "Daily",
            "device_id": device_id,
        },
    )
    assert habit.status_code == 200, habit.text

    habits = client.get("/habits", headers=headers)
    assert habits.status_code == 200
    assert any(h["name"] == "Evening reading" for h in habits.json())

    after_toggle = client.get(
        f"/users/{user['id']}/daily-activity?days=7",
        headers=headers,
    )
    assert after_toggle.status_code == 200
    assert after_toggle.json()["days"][-1]["active"] is True

    log = client.post(
        "/behavior-logs",
        headers=headers,
        json={
            "user_id": user["id"],
            "device_id": device_id,
            "action": "HabitCompleted",
            "event_time": datetime.now(UTC).isoformat(),
            "parameters": '{"source":"e2e_test"}',
        },
    )
    assert log.status_code == 200, log.text

    after = client.get(
        f"/users/{user['id']}/daily-activity?days=7",
        headers=headers,
    )
    assert after.status_code == 200
    assert after.json()["days"][-1]["active"] is True
    assert after.json()["weekly_streak_count"] >= 1

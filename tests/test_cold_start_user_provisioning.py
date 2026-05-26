from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import UTC

from app.analytics.cold_start_engine import ColdStartEngine
from app.api.schemas import UserCreate
from app.application.services import smart_home_service
from app.application.services.cold_start_provisioning import (
    provision_cold_start_defaults,
)

CSV_PATH = "app/analytics/processed_synapse_data.csv"
COLD_START_PROFILE = {
    "age": 22,
    "city": "İzmir",
    "gender": "Erkek",
    "height": 180,
    "weight": 75,
}


@pytest.mark.skipif(not Path(CSV_PATH).is_file(), reason="processed_synapse_data.csv gerekli")
def test_provision_cold_start_defaults_persists_recommendations(sqlite_session, sample_user):
    saved: list[dict] = []

    def _capture_save(user_id: str, rec: dict, session) -> None:
        saved.append({"user_id": user_id, **rec})
        from datetime import datetime
        from decimal import Decimal

        from app.core.models import Recommendation, RecommendationStatus

        row = Recommendation(
            id=f"REC-{len(saved):07d}",
            user_id=user_id,
            trigger_device=str(rec.get("trigger", "COLD_START")),
            target_device=str(rec.get("target", ""))[:64],
            action="DEFAULT",
            confidence=Decimal("0.5500"),
            recommendation_type=str(rec.get("type", "COLD_START_DEFAULT")),
            context=str(rec.get("context", ""))[:128],
            status=RecommendationStatus.Pending,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        session.commit()

    count = provision_cold_start_defaults(
        sample_user,
        sqlite_session,
        gender=COLD_START_PROFILE["gender"],
        save_recommendation=_capture_save,
    )

    assert count > 0
    assert len(saved) == count
    assert all(s["user_id"] == sample_user.id for s in saved)
    assert all(s["type"] == "COLD_START_DEFAULT" for s in saved)
    keys = {s["context"] for s in saved}
    assert "Hangi ışık rengi sizi daha huzurlu hissettirir?" in keys


@pytest.mark.skipif(not Path(CSV_PATH).is_file(), reason="processed_synapse_data.csv gerekli")
def test_create_user_triggers_cold_start_provisioning(monkeypatch, sqlite_session):
    engine = ColdStartEngine(csv_path=CSV_PATH)
    catalog = engine.generate_initial_catalog(COLD_START_PROFILE)
    assert catalog

    provision_mock = MagicMock(return_value=len(catalog))
    monkeypatch.setattr(smart_home_service, "provision_cold_start_defaults", provision_mock)

    payload = UserCreate(
        id="PTEST002",
        email="cold@synapse.local",
        age=22,
        height=180,
        weight=75,
        location="İzmir",
        gender="Erkek",
    )
    user = smart_home_service.create_user(payload, sqlite_session)

    assert user.id == "PTEST002"
    provision_mock.assert_called_once()
    call_kwargs = provision_mock.call_args.kwargs
    assert call_kwargs["gender"] == "Erkek"


@pytest.mark.skipif(not Path(CSV_PATH).is_file(), reason="processed_synapse_data.csv gerekli")
def test_new_user_demographic_defaults_non_empty_catalog():
    engine = ColdStartEngine(csv_path=CSV_PATH)
    catalog = engine.generate_initial_catalog(COLD_START_PROFILE)
    assert isinstance(catalog, dict)
    assert len(catalog) >= 3
    for question, answer in catalog.items():
        assert question.strip()
        assert str(answer).strip()

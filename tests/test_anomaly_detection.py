from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application.services.smart_home_service import detect_safety_anomaly
from app.core.domain.anomaly_detection import evaluate_duration_anomaly
from app.core.domain.events import AnomalyDetected
from app.core.models import BehaviorLog
from app.infrastructure.events.in_memory_publisher import InMemoryEventPublisher


def test_evaluate_duration_anomaly_fires_at_k_equals_2():
    historical = [10.0, 12.0, 11.0]
    detected, avg = evaluate_duration_anomaly(25.0, historical, k=2.0)
    assert avg == pytest.approx(11.0)
    assert detected is True


def test_evaluate_duration_anomaly_does_not_fire_below_k_equals_2():
    historical = [10.0, 12.0, 11.0]
    detected, _ = evaluate_duration_anomaly(21.0, historical, k=2.0)
    assert detected is False


def test_anomaly_detected_event_published_when_usage_exceeds_k2(
    sqlite_session: Session,
    sample_user,
    sample_device,
    event_publisher: InMemoryEventPublisher,
):
    base = timedelta(minutes=10)
    for i in range(3):
        sqlite_session.add(
            BehaviorLog(
                user_id=sample_user.id,
                device_id=sample_device.id,
                action="OFF",
                event_time=datetime(2026, 1, 1, 10 + i, 0, tzinfo=UTC),
                duration_hm=base,
            )
        )
    sqlite_session.commit()

    anomaly_log = BehaviorLog(
        user_id=sample_user.id,
        device_id=sample_device.id,
        action="OFF",
        event_time=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
        duration_hm=timedelta(minutes=25),
    )
    sqlite_session.add(anomaly_log)
    sqlite_session.commit()
    sqlite_session.refresh(anomaly_log)

    result = detect_safety_anomaly(anomaly_log, sqlite_session, publisher=event_publisher, k=2.0)

    assert result is not None
    assert result["type"] == "SAFETY_ANOMALY"
    assert len(event_publisher.events) == 1
    event = event_publisher.events[0]
    assert isinstance(event, AnomalyDetected)
    assert event.k_threshold == 2.0
    assert event.current_minutes == pytest.approx(25.0)
    assert event.average_minutes == pytest.approx(10.0)
    assert event.current_minutes >= event.k_threshold * event.average_minutes

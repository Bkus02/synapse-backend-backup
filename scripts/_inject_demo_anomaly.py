"""Demo helper — drop a SAFETY_ANOMALY notification for test1.

Used purely for the homework screenshot. The real detection lives in
``smart_home_service.detect_safety_anomaly`` and fires whenever a behaviour
log's duration crosses ``k × average``. Re-running this script overwrites
the existing anomaly so the bell stays clean.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text
from sqlmodel import Session

from app.application.services import notification_service
from app.core.models import Notification
from app.db.database import engine

DEMO_USER_EMAIL = "test1@gmail.com"
DEVICE_NAME = "Kitchen Oven"
CURRENT_MIN = 185.0   # ~3 hours 5 min
AVG_MIN = 45.0        # typical oven session
K = 2.0
CONFIDENCE = min(0.99, CURRENT_MIN / (K * AVG_MIN))


with Session(engine) as s:
    me = s.exec(
        text("SELECT id FROM users WHERE email = :e").bindparams(e=DEMO_USER_EMAIL)
    ).first()
    if me is None:
        raise SystemExit(f"User not found: {DEMO_USER_EMAIL}")
    uid = me[0]

    dev = s.exec(
        text(
            """
            SELECT d.id FROM devices d
            JOIN user_environments ue ON ue.environment_id = d.environment_id
            WHERE ue.user_id = :uid AND d.name = :name
            LIMIT 1
            """
        ).bindparams(uid=uid, name=DEVICE_NAME)
    ).first()
    if dev is None:
        raise SystemExit(f"Device '{DEVICE_NAME}' not found for {uid}")
    device_id = int(dev[0])

    # Remove any prior demo anomaly so the bell doesn't fill up.
    s.exec(
        text(
            "DELETE FROM notifications "
            "WHERE user_id = :uid AND kind = :kind"
        ).bindparams(uid=uid, kind=notification_service.NotificationKind.SafetyAnomaly.value)
    )
    s.commit()

    now = datetime.now(UTC)
    title = f"{DEVICE_NAME} has been on too long"
    body = (
        f"{DEVICE_NAME} (TurnOn) has been running for "
        f"{CURRENT_MIN:.0f} min — about {CURRENT_MIN / AVG_MIN:.1f}× "
        f"your usual {AVG_MIN:.0f} min. Please check if it should be off."
    )
    note = Notification(
        user_id=uid,
        kind=notification_service.NotificationKind.SafetyAnomaly.value,
        title=title,
        body=body,
        scheduled_for=now,
        fired_at=now,
        status=notification_service.NotificationStatus.Fired.value,
        requires_action=False,
        payload={
            "device_id": device_id,
            "device_name": DEVICE_NAME,
            "current_minutes": CURRENT_MIN,
            "average_minutes": AVG_MIN,
            "k_threshold": K,
            "confidence": round(CONFIDENCE, 3),
        },
    )
    s.add(note)
    s.commit()

    print(f"Injected SAFETY_ANOMALY for {DEMO_USER_EMAIL}:")
    print(f"  device       : {DEVICE_NAME} (id={device_id})")
    print(f"  current/avg  : {CURRENT_MIN:.0f} min  vs  {AVG_MIN:.0f} min  (k={K})")
    print(f"  confidence   : {CONFIDENCE:.3f}")
    print("Open the bell modal in Flutter — should appear under 'Safety alerts'.")

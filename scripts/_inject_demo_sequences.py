"""Demo helper — give test1 three A→B sequence rules + live notifications.

Why this exists: the seeded behaviour logs for test1 happen to produce no
qualifying habit_matrix rules, so the bell modal has no `sequence_trigger`
notifications to show. For the homework screenshot we manually inject:

  1. Three rules into ``habit_matrix`` (so the Habits page shows "Device:
     A → B" cards driven by mined sequences).
  2. The corresponding ``Habit`` rows with ``is_active = true``.
  3. Two ``sequence_trigger`` notifications already in ``fired`` state so
     they appear immediately when test1 opens the bell.

Safe to re-run: existing matrix rows for test1 are deleted first.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text
from sqlmodel import Session, select

from app.application.services import notification_service
from app.core.models import Device, Habit, HabitRecurrence, Notification
from app.db.database import engine
from app.models.habit_matrix import HabitMatrix

DEMO_USER_EMAIL = "test1@gmail.com"

# Each rule maps a (trigger_device_name, trigger_action)
# to a (target_device_name, target_action) with a probability and context.
DEMO_RULES = [
    {
        "trigger_device": "Living Room AC",
        "trigger_action": "TurnOff",
        "target_device": "Kitchen Oven",
        "target_action": "TurnOn",
        "probability": 0.78,
        "context": "Day",
    },
    {
        "trigger_device": "Kitchen Oven",
        "trigger_action": "TurnOff",
        "target_device": "Dishwasher",
        "target_action": "TurnOn",
        "probability": 0.71,
        "context": "Night",
    },
    {
        "trigger_device": "Living Room Lamp",
        "trigger_action": "TurnOn",
        "target_device": "Bedroom Thermostat",
        "target_action": "TurnOff",
        "probability": 0.65,
        "context": "Night",
    },
]


def _device_id_by_name(session: Session, user_id: str, name: str) -> int:
    rows = session.exec(
        text(
            """
            SELECT d.id FROM devices d
            JOIN user_environments ue ON ue.environment_id = d.environment_id
            WHERE ue.user_id = :uid AND d.name = :name
            LIMIT 1
            """
        ).bindparams(uid=user_id, name=name)
    ).first()
    if rows is None:
        raise SystemExit(f"Device not found for {user_id}: {name}")
    return int(rows[0])


with Session(engine) as s:
    me = s.exec(
        text("SELECT id FROM users WHERE email = :e").bindparams(e=DEMO_USER_EMAIL)
    ).first()
    if me is None:
        raise SystemExit(f"User not found: {DEMO_USER_EMAIL}")
    uid = me[0]
    print(f"test1 user_id = {uid}")

    # ── 1) wipe & insert habit_matrix rules ────────────────────────────
    s.exec(text("DELETE FROM habit_matrix WHERE user_id = :uid").bindparams(uid=uid))
    s.commit()

    now = datetime.now(UTC)
    inserted_matrix = 0
    inserted_habits = 0
    inserted_notifs = 0

    for rule in DEMO_RULES:
        trig_dev_id = _device_id_by_name(s, uid, rule["trigger_device"])
        tgt_dev_id = _device_id_by_name(s, uid, rule["target_device"])
        trigger_token = f"{trig_dev_id}_{rule['trigger_action']}"
        target_token = f"{tgt_dev_id}_{rule['target_action']}"

        s.add(
            HabitMatrix(
                user_id=uid,
                trigger_event=trigger_token,
                target_event=target_token,
                context=rule["context"],
                probability=rule["probability"],
                last_updated=now,
            )
        )
        inserted_matrix += 1

        # ── 2) human-readable Habit row (Device: A → B (ctx)) ──────────
        habit_name = (
            f"Device: {rule['trigger_device']} {rule['trigger_action']} → "
            f"{rule['target_device']} {rule['target_action']} ({rule['context']})"
        )
        existing = s.exec(
            select(Habit).where(Habit.user_id == uid, Habit.name == habit_name)
        ).first()
        if existing is None:
            s.add(
                Habit(
                    user_id=uid,
                    name=habit_name,
                    probability_score=Decimal(str(round(rule["probability"], 2))),
                    is_active=True,
                    recurrence_type=HabitRecurrence.Daily,
                    device_id=None,
                )
            )
            inserted_habits += 1
        else:
            existing.probability_score = Decimal(str(round(rule["probability"], 2)))
            existing.is_active = True
            s.add(existing)

    # ── 3) drop two live sequence_trigger notifications so the bell
    #     modal already has something to display.
    for rule in DEMO_RULES[:2]:
        tgt_dev_id = _device_id_by_name(s, uid, rule["target_device"])
        trig_dev_id = _device_id_by_name(s, uid, rule["trigger_device"])
        verb = "turn on" if rule["target_action"].lower().endswith("on") else "turn off"
        title = f"{rule['target_device']}?"
        body = (
            f"You usually {verb} {rule['target_device']} right after "
            f"{rule['trigger_device']} {rule['trigger_action'].lower()}s. "
            "Confirm to log it now."
        )
        note = Notification(
            user_id=uid,
            kind=notification_service.NotificationKind.SequenceTrigger.value,
            title=title,
            body=body,
            scheduled_for=now,
            fired_at=now,
            status=notification_service.NotificationStatus.Fired.value,
            requires_action=True,
            payload={
                "source_log_id": None,
                "trigger_device_id": trig_dev_id,
                "trigger_action": rule["trigger_action"],
                "target_device_id": tgt_dev_id,
                "device_id": tgt_dev_id,
                "action": rule["target_action"],
                "confidence": round(rule["probability"], 3),
            },
        )
        s.add(note)
        inserted_notifs += 1

    s.commit()

    print(f"habit_matrix rows inserted: {inserted_matrix}")
    print(f"Device habit rows inserted: {inserted_habits}")
    print(f"sequence_trigger notifications inserted: {inserted_notifs}")
    print("\nDone — log in as test1, open the bell and the Habits page.")

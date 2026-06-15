"""User-planned advice sessions.

The dashboard advice tile opens a tiny "start time + duration" dialog.
We persist the plan in ``advice_schedules``, write a ``positive_advice_logs``
row immediately (so streak / Community Progress update right away), and drop
a paired ``advice_reminder`` Notification. Bell confirm is optional and
idempotent when the schedule is already marked completed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.application.services import notification_service, positive_advice_service
from app.application.services.recommendation_catalog import ADVICE_CATALOG
from app.core.models import (
    AdviceSchedule,
    Notification,
    NotificationKind,
    NotificationStatus,
)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def schedule_advice(
    *,
    user_id: str,
    advice_key: str,
    scheduled_for: datetime,
    duration_minutes: int,
    session: Session,
) -> dict[str, Any]:
    """Plan a future positive-advice session for the user.

    Creates two rows atomically:
      • ``advice_schedules`` with the plan (status ``pending``)
      • ``notifications`` (kind ``advice_reminder``, requires_action=True)

    If the chosen ``scheduled_for`` is already in the past (e.g., the user
    is logging right now), the notification is created in ``fired`` state
    so it appears in the bell modal immediately.
    """
    if advice_key not in ADVICE_CATALOG:
        raise HTTPException(status_code=400, detail=f"Unknown advice_key: {advice_key}")
    if duration_minutes < 0 or duration_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="duration_minutes out of range.")

    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=UTC)
    scheduled_for = scheduled_for.astimezone(UTC)

    title_label = ADVICE_CATALOG[advice_key]["title"]
    sched = AdviceSchedule(
        user_id=user_id,
        advice_key=advice_key,
        advice_title=title_label,
        scheduled_for=scheduled_for,
        duration_minutes=duration_minutes,
        status="pending",
    )
    session.add(sched)
    session.flush()  # populate sched.id for the payload

    now = _now_utc()
    initial = (
        NotificationStatus.Fired if scheduled_for <= now else NotificationStatus.Pending
    )
    note = Notification(
        user_id=user_id,
        kind=NotificationKind.AdviceReminder.value,
        title=f"Ready for {title_label}?",
        body=(
            f"You planned {duration_minutes} min of "
            f"{title_label.lower()}. Tap confirm when you start."
        ),
        scheduled_for=scheduled_for,
        status=initial.value,
        requires_action=True,
        payload={
            "schedule_id": sched.id,
            "advice_key": advice_key,
            "advice_title": title_label,
            "duration_minutes": duration_minutes,
        },
        fired_at=now if initial == NotificationStatus.Fired else None,
    )
    session.add(note)
    session.flush()

    sched.notification_id = note.id
    session.add(sched)
    session.commit()
    session.refresh(sched)
    session.refresh(note)

    # User entered start time + duration on the dashboard — count it toward
    # streak/habit progress immediately (bell confirm is optional / idempotent).
    positive_advice_service.log_advice_completion(
        user_id=user_id,
        advice_key=advice_key,
        duration_minutes=duration_minutes,
        completed_at=scheduled_for,
        session=session,
    )
    sched = session.get(AdviceSchedule, sched.id)
    if sched is not None:
        sched.status = "completed"
        session.add(sched)
        session.commit()
        session.refresh(sched)

    note = session.get(Notification, note.id) or note

    return {
        "schedule": {
            "id": sched.id,
            "user_id": sched.user_id,
            "advice_key": sched.advice_key,
            "advice_title": sched.advice_title,
            "scheduled_for": sched.scheduled_for.isoformat(),
            "duration_minutes": sched.duration_minutes,
            "status": sched.status,
        },
        "notification": notification_service._serialize(note),  # noqa: SLF001
    }

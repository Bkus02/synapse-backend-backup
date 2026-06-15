"""Bell-modal feed endpoints + the day-31 simulation helper."""

from __future__ import annotations

from datetime import datetime, date
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.deps import current_user_id
from app.application.services import (
    advice_schedule_service,
    notification_service,
)
from app.db.database import get_session

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("")
def list_feed(
    include_expired: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return the current bell-modal feed for the signed-in user.

    Side-effect: any ``pending`` rows whose ``scheduled_for`` is past are
    flipped to ``fired`` first so the dashboard always sees a fresh feed
    without a separate scheduler process.
    """
    notification_service.fire_due_notifications(session)
    rows = notification_service.feed_for_user(
        user_id, session, include_expired=include_expired, limit=limit
    )
    return [notification_service._serialize(r) for r in rows]  # noqa: SLF001


@router.get("/badge")
def badge_count(
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    notification_service.fire_due_notifications(session)
    return {"unread": notification_service.unread_count(user_id, session)}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@router.post("/{note_id}/confirm")
def confirm(
    note_id: int,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return notification_service.confirm(note_id, user_id, session)


@router.post("/{note_id}/dismiss")
def dismiss(
    note_id: int,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return notification_service.dismiss(note_id, user_id, session)


# ---------------------------------------------------------------------------
# Day-31 simulation: re-run every generator for "today in Istanbul".
# ---------------------------------------------------------------------------


@router.post("/seed-today")
def seed_today(
    session: Session = Depends(get_session),
) -> dict[str, int]:
    """Backfill all of today's notifications for every user.

    Designed for the demo: we already have 30 days of seeded behaviour, so
    treat today as "day 31" and produce the greeting, device-routine
    confirms, and any new streak-milestone celebrations. Idempotent —
    re-running is safe.
    """
    greetings = notification_service.generate_morning_greetings(session)
    routines = notification_service.generate_device_routine_reminders(session)
    advice_habits = notification_service.generate_advice_habit_reminders(session)
    milestones = notification_service.generate_streak_milestones(session)
    streak_risk = notification_service.generate_streak_risk_reminders(session)
    fired = notification_service.fire_due_notifications(session)
    expired = notification_service.expire_overdue(session)
    return {
        "morning_greetings": greetings,
        "device_routine_reminders": routines,
        "advice_habit_reminders": advice_habits,
        "streak_milestones": milestones,
        "streak_risk_reminders": streak_risk,
        "fired_now": fired,
        "expired": expired,
    }


# ---------------------------------------------------------------------------
# Advice scheduling — paired with notifications.
# ---------------------------------------------------------------------------


schedule_router = APIRouter(prefix="/advice-schedules", tags=["Advice schedules"])


class AdviceScheduleBody(BaseModel):
    advice_key: str = Field(..., description="ADVICE_CATALOG key (e.g. 'light_walk').")
    scheduled_for: datetime = Field(..., description="When the user plans to start.")
    duration_minutes: int = Field(default=0, ge=0, le=24 * 60)


@schedule_router.post("", status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: AdviceScheduleBody,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return advice_schedule_service.schedule_advice(
        user_id=user_id,
        advice_key=body.advice_key,
        scheduled_for=body.scheduled_for,
        duration_minutes=body.duration_minutes,
        session=session,
    )

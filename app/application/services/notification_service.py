"""In-app notification service.

The notification feed is *persistent*: each row in ``notifications`` walks
the lifecycle ``pending → fired → confirmed | dismissed | expired``. The
service exposes:

  • ``feed_for_user``      – everything the bell modal should show.
  • ``confirm`` / ``dismiss`` – user action handlers that may have side
    effects (logging an advice completion, writing a BehaviorLog row,
    recomputing the daily streak, etc.).
  • ``generate_morning_greetings``  – idempotent daily 09:00 greeting.
  • ``generate_device_routine_reminders`` – schedules confirm prompts for
    each currently-active device routine habit (probability > 0.60).
  • ``fire_due_notifications``     – flips ``pending`` rows whose
    ``scheduled_for`` is past to ``fired`` and stamps ``fired_at``.
  • ``expire_overdue``             – end-of-day cleanup.

All times are stored as UTC `TIMESTAMPTZ`. The Istanbul-relative
"morning at 09:00" logic uses the ``Europe/Istanbul`` zone to compute the
correct UTC instant.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, text as sql_text
from sqlmodel import Session, select

from app.application.services import positive_advice_service
from app.application.services.recommendation_catalog import ADVICE_CATALOG
from app.core.models import (
    AdviceSchedule,
    BehaviorLog,
    Device,
    Habit,
    Notification,
    NotificationKind,
    NotificationStatus,
    PositiveAdviceLog,
    User,
    UserDailyStreak,
)

# Reverse map "advice title" → advice_key so we can resolve an "Advice: <Title>"
# habit row back to its catalog key (the habit name is the only link we keep).
_ADVICE_TITLE_TO_KEY: dict[str, str] = {
    str(item["title"]): key for key, item in ADVICE_CATALOG.items()
}
_ADVICE_HABIT_PREFIX = "Advice: "

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
MORNING_GREETING_HOUR = 9  # local Istanbul time

# Device routine habit prefix written by smart_home_service.detect_device_routines
# Habit name shape: "Routine: <Device Name> <TurnOn|TurnOff> @HH"
# We accept any casing because detect_device_routines runs `.title()` on
# the action token which lowercases the trailing letters (TurnOn → Turnon).
_ROUTINE_NAME_PATTERN = re.compile(
    r"^Routine:\s+(?P<device>.+?)\s+(?P<action>TurnOn|TurnOff)\s+@(?P<hour>\d{1,2})\b",
    re.IGNORECASE,
)


def _canonical_action(raw: str) -> str:
    """Normalise the action token back to the BehaviorLog enum casing."""
    lower = raw.lower()
    if lower in {"turnon", "turn_on"}:
        return "TurnOn"
    if lower in {"turnoff", "turn_off"}:
        return "TurnOff"
    return raw

# Hysteresis threshold: only confirmed habits trigger device reminders.
DEVICE_HABIT_MIN_PROBABILITY = 0.60


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------


def feed_for_user(
    user_id: str,
    session: Session,
    *,
    include_expired: bool = False,
    limit: int = 50,
) -> list[Notification]:
    """Return the bell-feed for a user, ``fired`` items first then ``pending``.

    Returned items are sorted by ``scheduled_for`` descending so the most
    recent / soonest-due appears at the top.
    """
    statuses: list[str] = [
        NotificationStatus.Fired.value,
        NotificationStatus.Pending.value,
        NotificationStatus.Confirmed.value,
        NotificationStatus.Dismissed.value,
    ]
    if include_expired:
        statuses.append(NotificationStatus.Expired.value)
    rows = list(
        session.exec(
            select(Notification)
            .where(Notification.user_id == user_id)
            .where(Notification.status.in_(statuses))  # type: ignore[attr-defined]
            .order_by(Notification.scheduled_for.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
    )
    return rows


def unread_count(user_id: str, session: Session) -> int:
    """How many notifications are currently in the bell badge.

    Definition: notifications that are ``fired`` (visible) and either
    require_action (still awaiting a tap) or were not yet acted on. We
    keep it simple: count ``fired`` rows.
    """
    row = session.exec(
        sql_text(
            """
            SELECT COUNT(*) FROM notifications
            WHERE user_id = :uid AND status = 'fired'
            """
        ).bindparams(uid=user_id)
    ).first()
    if row is None:
        return 0
    return int(row[0])


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _create_notification(
    session: Session,
    *,
    user_id: str,
    kind: NotificationKind | str,
    title: str,
    body: str,
    scheduled_for: datetime,
    requires_action: bool = False,
    payload: dict[str, Any] | None = None,
    initial_status: NotificationStatus | str = NotificationStatus.Pending,
) -> Notification:
    kind_val = kind.value if isinstance(kind, NotificationKind) else str(kind)
    status_val = (
        initial_status.value
        if isinstance(initial_status, NotificationStatus)
        else str(initial_status)
    )
    note = Notification(
        user_id=user_id,
        kind=kind_val,
        title=title,
        body=body,
        scheduled_for=scheduled_for,
        status=status_val,
        requires_action=requires_action,
        payload=payload or {},
    )
    session.add(note)
    session.flush()
    return note


# ---------------------------------------------------------------------------
# Lifecycle: confirm / dismiss
# ---------------------------------------------------------------------------


def _serialize(note: Notification) -> dict[str, Any]:
    """Tiny serializer for API responses (so payload comes through cleanly)."""
    return {
        "id": note.id,
        "user_id": note.user_id,
        "kind": note.kind,
        "title": note.title,
        "body": note.body,
        "scheduled_for": note.scheduled_for.isoformat() if note.scheduled_for else None,
        "fired_at": note.fired_at.isoformat() if note.fired_at else None,
        "status": note.status,
        "requires_action": note.requires_action,
        "payload": note.payload or {},
    }


def confirm(
    note_id: int,
    user_id: str,
    session: Session,
) -> dict[str, Any]:
    """User tapped the positive action button.

    Side effects per kind:

      • ``advice_reminder``  → write a `positive_advice_logs` row using the
        linked AdviceSchedule, recompute daily streak.
      • ``device_routine``   → write a synthetic ``BehaviorLog`` (action +
        device) so habit confidence stays warm.
      • ``sequence_trigger`` → write a ``BehaviorLog`` for the target device.
      • other kinds          → just mark confirmed.
    """
    note = _get_owned(note_id, user_id, session)
    if note.status in {NotificationStatus.Confirmed.value, NotificationStatus.Dismissed.value}:
        return _serialize(note)

    payload = note.payload or {}

    if note.kind == NotificationKind.AdviceReminder.value:
        sched_id = payload.get("schedule_id")
        if sched_id is not None:
            sched = session.get(AdviceSchedule, int(sched_id))
            if sched is not None and sched.user_id == user_id:
                # schedule_advice already logs on plan submit; avoid duplicates.
                if sched.status != "completed":
                    positive_advice_service.log_advice_completion(
                        user_id=user_id,
                        advice_key=sched.advice_key,
                        duration_minutes=sched.duration_minutes,
                        completed_at=_now_utc(),
                        session=session,
                    )
                    sched.status = "completed"
                    session.add(sched)
                    positive_advice_service.recompute_daily_streak(user_id, session)
        else:
            # Habit-driven daily reminder (no schedule row). Log directly from
            # the payload so the streak / flare advances on confirm.
            advice_key = payload.get("advice_key")
            if advice_key:
                positive_advice_service.log_advice_completion(
                    user_id=user_id,
                    advice_key=str(advice_key),
                    duration_minutes=int(payload.get("duration_minutes", 0) or 0),
                    completed_at=_now_utc(),
                    session=session,
                )
                positive_advice_service.recompute_daily_streak(user_id, session)

    elif note.kind in {
        NotificationKind.DeviceRoutine.value,
        NotificationKind.SequenceTrigger.value,
    }:
        device_id = payload.get("device_id") or payload.get("target_device_id")
        action = payload.get("action", "TurnOn")
        if device_id is not None:
            log = BehaviorLog(
                user_id=user_id,
                device_id=int(device_id),
                action=str(action),
                event_time=_now_utc(),
            )
            session.add(log)

    elif note.kind == NotificationKind.EnvironmentInvite.value:
        # Davet kabul edildi → kullaniciyi environment'e ekle.
        env_id = payload.get("environment_id")
        if env_id:
            # Local import to avoid a circular import at module load time.
            from fastapi import HTTPException

            from app.application.services import smart_home_service

            try:
                smart_home_service.add_user_to_environment(
                    str(env_id), user_id, session
                )
            except HTTPException as exc:
                # 409 (zaten uye) gibi durumlarda daveti yine de kapat;
                # environment silinmis (404) ise hatayi yukari ilet.
                if exc.status_code != 409:
                    raise

    note.status = NotificationStatus.Confirmed.value
    note.updated_at = _now_utc()
    session.add(note)
    session.commit()
    session.refresh(note)
    return _serialize(note)


def dismiss(
    note_id: int,
    user_id: str,
    session: Session,
) -> dict[str, Any]:
    note = _get_owned(note_id, user_id, session)
    if note.status in {NotificationStatus.Confirmed.value, NotificationStatus.Dismissed.value}:
        return _serialize(note)
    note.status = NotificationStatus.Dismissed.value
    note.updated_at = _now_utc()
    # Cancel a linked advice schedule too so it doesn't get re-scheduled.
    if note.kind == NotificationKind.AdviceReminder.value:
        sched_id = (note.payload or {}).get("schedule_id")
        if sched_id is not None:
            sched = session.get(AdviceSchedule, int(sched_id))
            if sched is not None and sched.user_id == user_id:
                sched.status = "cancelled"
                session.add(sched)
    session.add(note)
    session.commit()
    session.refresh(note)
    return _serialize(note)


def _get_owned(note_id: int, user_id: str, session: Session) -> Notification:
    from fastapi import HTTPException

    note = session.get(Notification, note_id)
    if note is None or note.user_id != user_id:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return note


# ---------------------------------------------------------------------------
# Scheduler-like helpers (called from a route or by the seed-today endpoint)
# ---------------------------------------------------------------------------


def fire_due_notifications(session: Session, *, now: datetime | None = None) -> int:
    """Move ``pending`` rows whose ``scheduled_for`` is past into ``fired``.

    Returns the number of rows flipped.
    """
    now = now or _now_utc()
    pending = list(
        session.exec(
            select(Notification).where(
                and_(
                    Notification.status == NotificationStatus.Pending.value,
                    Notification.scheduled_for <= now,
                )
            )
        )
    )
    for n in pending:
        n.status = NotificationStatus.Fired.value
        n.fired_at = now
        n.updated_at = now
        session.add(n)
    if pending:
        session.commit()
    return len(pending)


def expire_overdue(
    session: Session,
    *,
    today_local: date | None = None,
) -> int:
    """End-of-day cleanup — fired/pending rows older than ``today_local`` 00:00
    Istanbul time become ``expired``."""
    today_local = today_local or _today_istanbul()
    midnight_local = datetime.combine(today_local, time(0, 0), tzinfo=ISTANBUL_TZ)
    cutoff = midnight_local.astimezone(UTC)
    overdue = list(
        session.exec(
            select(Notification).where(
                and_(
                    Notification.scheduled_for < cutoff,
                    Notification.status.in_(  # type: ignore[attr-defined]
                        [
                            NotificationStatus.Pending.value,
                            NotificationStatus.Fired.value,
                        ]
                    ),
                )
            )
        )
    )
    for n in overdue:
        n.status = NotificationStatus.Expired.value
        n.updated_at = _now_utc()
        session.add(n)
    if overdue:
        session.commit()
    return len(overdue)


# ---------------------------------------------------------------------------
# Generators — idempotent per (user_id, scheduled_for, kind, payload key)
# ---------------------------------------------------------------------------


def _today_istanbul() -> date:
    return datetime.now(ISTANBUL_TZ).date()


def _local_to_utc(d: date, hour: int, minute: int = 0) -> datetime:
    """Construct an Istanbul-local datetime then convert to UTC."""
    local = datetime.combine(d, time(hour, minute), tzinfo=ISTANBUL_TZ)
    return local.astimezone(UTC)


def _exists(
    session: Session,
    *,
    user_id: str,
    kind: str,
    scheduled_for: datetime,
    payload_key: str | None = None,
    payload_value: Any | None = None,
) -> bool:
    """Cheap idempotency check — same user/kind/time (+optional payload key)."""
    q = (
        select(Notification.id)
        .where(Notification.user_id == user_id)
        .where(Notification.kind == kind)
        .where(Notification.scheduled_for == scheduled_for)
    )
    rows = list(session.exec(q))
    if not rows:
        return False
    if payload_key is None:
        return True
    for nid in rows:
        n = session.get(Notification, nid)
        if n is not None and (n.payload or {}).get(payload_key) == payload_value:
            return True
    return False


def generate_morning_greetings(
    session: Session,
    *,
    target_day: date | None = None,
) -> int:
    """Insert (idempotent) one morning greeting per user for ``target_day``.

    Defaults to "today in Istanbul". The notification is created with
    status ``fired`` so it shows up immediately if 09:00 has already passed
    when the generator runs; otherwise it stays ``pending`` until
    ``fire_due_notifications`` flips it.
    """
    target_day = target_day or _today_istanbul()
    scheduled = _local_to_utc(target_day, MORNING_GREETING_HOUR)
    now = _now_utc()
    initial = (
        NotificationStatus.Fired if scheduled <= now else NotificationStatus.Pending
    )

    users = list(session.exec(select(User)))
    created = 0
    for u in users:
        if _exists(
            session,
            user_id=u.id,
            kind=NotificationKind.MorningGreeting.value,
            scheduled_for=scheduled,
        ):
            continue
        note = _create_notification(
            session,
            user_id=u.id,
            kind=NotificationKind.MorningGreeting,
            title="Good morning :)",
            body="Don't forget your positive advices today.",
            scheduled_for=scheduled,
            requires_action=False,
            payload={"day": target_day.isoformat()},
            initial_status=initial,
        )
        if initial == NotificationStatus.Fired:
            note.fired_at = now
            session.add(note)
        created += 1
    if created:
        session.commit()
    return created


def generate_device_routine_reminders(
    session: Session,
    *,
    target_day: date | None = None,
) -> int:
    """For every confirmed device-routine habit, plan today's confirm prompt.

    Only habits matching ALL of these are eligible:
      • ``name`` starts with ``Routine:`` (single-action time-of-day routine)
      • ``is_active = TRUE``
      • ``probability_score > 0.60`` (out of the hysteresis ambiguous band)
      • ``device_id`` resolves to an existing device

    The habit name is parsed for the canonical "@HH" hour suffix; if
    missing, the habit is skipped (no time → no schedule).
    """
    target_day = target_day or _today_istanbul()
    now = _now_utc()
    created = 0

    habits = list(
        session.exec(
            select(Habit).where(
                and_(
                    Habit.is_active == True,  # noqa: E712
                    Habit.name.like("Routine:%"),  # type: ignore[attr-defined]
                )
            )
        )
    )
    for h in habits:
        try:
            if float(h.probability_score) <= DEVICE_HABIT_MIN_PROBABILITY:
                continue
        except (TypeError, ValueError):
            continue
        m = _ROUTINE_NAME_PATTERN.match(h.name)
        if not m:
            continue
        device_name = m.group("device")
        action = _canonical_action(m.group("action"))
        hour = int(m.group("hour"))
        if not (0 <= hour <= 23):
            continue

        device = (
            session.get(Device, h.device_id) if h.device_id is not None else None
        )
        if device is None:
            continue

        scheduled = _local_to_utc(target_day, hour, 0)
        if _exists(
            session,
            user_id=h.user_id,
            kind=NotificationKind.DeviceRoutine.value,
            scheduled_for=scheduled,
            payload_key="habit_id",
            payload_value=h.id,
        ):
            continue

        verb = "turn on" if action == "TurnOn" else "turn off"
        title = f"Time to {verb} {device_name}"
        body = (
            f"You usually {verb} {device_name} around "
            f"{hour:02d}:00. Confirm to log it."
        )
        initial = (
            NotificationStatus.Fired if scheduled <= now else NotificationStatus.Pending
        )
        note = _create_notification(
            session,
            user_id=h.user_id,
            kind=NotificationKind.DeviceRoutine,
            title=title,
            body=body,
            scheduled_for=scheduled,
            requires_action=True,
            payload={
                "habit_id": h.id,
                "device_id": device.id,
                "device_name": device_name,
                "action": action,
                "hour": hour,
            },
            initial_status=initial,
        )
        if initial == NotificationStatus.Fired:
            note.fired_at = now
            session.add(note)
        created += 1
    if created:
        session.commit()
    return created


def _advice_key_for_habit(habit: Habit) -> str | None:
    """Resolve the catalog advice_key behind an "Advice: <Title>" habit row."""
    if not habit.name or not habit.name.startswith(_ADVICE_HABIT_PREFIX):
        return None
    title = habit.name[len(_ADVICE_HABIT_PREFIX):].strip()
    return _ADVICE_TITLE_TO_KEY.get(title)


def _typical_hour_and_duration(
    user_id: str, advice_key: str, session: Session
) -> tuple[int, int] | None:
    """Most frequent local (Istanbul) hour and duration from past completions.

    Returns ``None`` when the user has no logged completion for this advice.
    """
    logs = list(
        session.exec(
            select(PositiveAdviceLog).where(
                PositiveAdviceLog.user_id == user_id,
                PositiveAdviceLog.advice_key == advice_key,
            )
        )
    )
    if not logs:
        return None

    from collections import Counter

    hour_counts: Counter[int] = Counter()
    duration_counts: Counter[int] = Counter()
    for log in logs:
        ts = log.completed_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        local_hour = ts.astimezone(ISTANBUL_TZ).hour
        hour_counts[local_hour] += 1
        if log.duration_minutes and log.duration_minutes > 0:
            duration_counts[int(log.duration_minutes)] += 1

    if not hour_counts:
        return None
    # most_common breaks ties by insertion; good enough for a reminder hour.
    hour = hour_counts.most_common(1)[0][0]
    duration = duration_counts.most_common(1)[0][0] if duration_counts else 30
    return hour, duration


def generate_advice_habit_reminders(
    session: Session,
    *,
    target_day: date | None = None,
) -> int:
    """Plan a daily confirm prompt for every active advice-based habit.

    A positive advice becomes a Habit once it has >= 10 logs (see
    ``positive_advice_service.ADVICE_HABIT_LOG_THRESHOLD``). From then on we
    remind the user at the hour they most often complete it, so the streak
    keeps its momentum. The reminder carries the ``advice_key`` directly;
    confirming it logs a completion and recomputes the streak.
    """
    target_day = target_day or _today_istanbul()
    now = _now_utc()
    today_start = _local_to_utc(target_day, 0, 0)
    created = 0

    habits = list(
        session.exec(
            select(Habit).where(
                and_(
                    Habit.is_active == True,  # noqa: E712
                    Habit.name.like(f"{_ADVICE_HABIT_PREFIX}%"),  # type: ignore[attr-defined]
                )
            )
        )
    )
    for h in habits:
        advice_key = _advice_key_for_habit(h)
        if advice_key is None:
            continue
        # Already done today? No nudge needed.
        if _advice_done_today(h.user_id, advice_key, today_start, session):
            continue
        typical = _typical_hour_and_duration(h.user_id, advice_key, session)
        if typical is None:
            continue
        hour, duration = typical
        scheduled = _local_to_utc(target_day, hour, 0)
        if _exists(
            session,
            user_id=h.user_id,
            kind=NotificationKind.AdviceReminder.value,
            scheduled_for=scheduled,
            payload_key="habit_id",
            payload_value=h.id,
        ):
            continue

        title_label = h.name[len(_ADVICE_HABIT_PREFIX):].strip() or advice_key
        # Reminders are informational nudges — no confirmation required.
        initial = (
            NotificationStatus.Fired if scheduled <= now else NotificationStatus.Pending
        )
        note = _create_notification(
            session,
            user_id=h.user_id,
            kind=NotificationKind.AdviceReminder,
            title=f"{title_label} reminder",
            body=(
                f"You haven't done {title_label.lower()} yet today. "
                f"You usually do it around {hour:02d}:00 — want to?"
            ),
            scheduled_for=scheduled,
            requires_action=False,
            payload={
                "habit_id": h.id,
                "advice_key": advice_key,
                "advice_title": title_label,
                "duration_minutes": duration,
                "hour": hour,
                "source": "habit",
            },
            initial_status=initial,
        )
        if initial == NotificationStatus.Fired:
            note.fired_at = now
            session.add(note)
        created += 1
    if created:
        session.commit()
    return created


def _advice_done_today(
    user_id: str, advice_key: str, today_start_utc: datetime, session: Session
) -> bool:
    """True when the user already logged ``advice_key`` since local midnight."""
    row = session.exec(
        select(PositiveAdviceLog.id).where(
            PositiveAdviceLog.user_id == user_id,
            PositiveAdviceLog.advice_key == advice_key,
            PositiveAdviceLog.completed_at >= today_start_utc,
        )
    ).first()
    return row is not None


def generate_streak_risk_reminders(
    session: Session,
    *,
    target_day: date | None = None,
) -> int:
    """Warn users with an active streak who haven't qualified today yet.

    A day "qualifies" once the user logs
    ``positive_advice_service.QUALIFYING_ADVICES_PER_DAY`` distinct advices.
    Anyone with ``current_streak >= 1`` who is still short gets a single
    informational nudge ("finish N more to keep your streak"). Fired
    immediately so it surfaces right away; deduped per day via a fixed
    evening ``scheduled_for``.
    """
    target_day = target_day or _today_istanbul()
    now = _now_utc()
    today_start = _local_to_utc(target_day, 0, 0)
    scheduled = _local_to_utc(target_day, 20, 0)  # stable per-day slot for dedup
    needed = positive_advice_service.QUALIFYING_ADVICES_PER_DAY
    created = 0

    for r in session.exec(select(UserDailyStreak)):
        if r.current_streak < 1:
            continue
        keys_today = {
            k
            for k in session.exec(
                select(PositiveAdviceLog.advice_key).where(
                    PositiveAdviceLog.user_id == r.user_id,
                    PositiveAdviceLog.completed_at >= today_start,
                )
            )
        }
        if len(keys_today) >= needed:
            continue  # already safe today
        if _exists(
            session,
            user_id=r.user_id,
            kind=NotificationKind.StreakRisk.value,
            scheduled_for=scheduled,
        ):
            continue

        remaining = needed - len(keys_today)
        plural = "advice" if remaining == 1 else "advices"
        note = _create_notification(
            session,
            user_id=r.user_id,
            kind=NotificationKind.StreakRisk,
            title=f"Don't lose your {r.current_streak}-day streak",
            body=(
                f"You haven't completed today's positive advices yet. "
                f"Finish {remaining} more {plural} today to keep your "
                f"{r.current_streak}-day streak alive."
            ),
            scheduled_for=scheduled,
            requires_action=False,
            payload={"streak": r.current_streak, "remaining": remaining},
            initial_status=NotificationStatus.Fired,
        )
        note.fired_at = now
        session.add(note)
        created += 1
    if created:
        session.commit()
    return created


def generate_streak_milestones(
    session: Session,
    *,
    milestones: tuple[int, ...] = (7, 14, 30, 60),
) -> int:
    """Drop a celebratory notification when ``current_streak`` exactly equals
    one of the milestones. Idempotent — re-running on the same day with the
    same streak value is a no-op (payload['streak'] dedup)."""
    rows = list(session.exec(select(UserDailyStreak)))
    now = _now_utc()
    today_local = _today_istanbul()
    scheduled = _local_to_utc(today_local, 12, 0)  # noon Istanbul
    created = 0
    for r in rows:
        if r.current_streak not in milestones:
            continue
        if _exists(
            session,
            user_id=r.user_id,
            kind=NotificationKind.StreakMilestone.value,
            scheduled_for=scheduled,
            payload_key="streak",
            payload_value=r.current_streak,
        ):
            continue
        note = _create_notification(
            session,
            user_id=r.user_id,
            kind=NotificationKind.StreakMilestone,
            title=f"{r.current_streak}-day streak!",
            body=(
                f"You hit {r.current_streak} consecutive qualifying days "
                "of positive advices. Keep it going."
            ),
            scheduled_for=scheduled,
            requires_action=False,
            payload={"streak": r.current_streak},
            initial_status=NotificationStatus.Fired,
        )
        note.fired_at = now
        session.add(note)
        created += 1
    if created:
        session.commit()
    return created

"""Positive-advice tracking, daily streak engine and auto-habit promotion.

Responsibilities
---------------
1. ``log_advice_completion`` records when a user completes a positive advice
   (e.g. "Brisk Walk — 30 min"), persists it in ``positive_advice_logs`` and
   recomputes their daily streak.
2. ``recompute_daily_streak`` evaluates the user's history and writes the
   single-row ``user_daily_streaks`` record. A day "qualifies" when the user
   has logged **at least 2 distinct advice keys** that day; consecutive
   qualifying days build the streak.
3. After every insert, ``maybe_promote_advice_to_habit`` checks whether a
   given ``advice_key`` has accumulated **>= 10 logs**; if so, an entry in the
   ``habits`` table is upserted with ``is_active=True`` so the dashboard's
   "Active Habits" card surfaces it next to device-derived habits.
4. ``seed_advice_catalog`` is called from app start-up so the
   ``positive_advices`` lookup table is always populated from the curated
   ``recommendation_catalog`` (idempotent — only inserts missing entries).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.application.services.recommendation_catalog import ADVICE_CATALOG
from app.core.models import (
    AdviceCategory,
    Habit,
    HabitRecurrence,
    PositiveAdvice,
    PositiveAdviceLog,
    UserDailyStreak,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: A day is "qualifying" once this many distinct advice keys are completed.
QUALIFYING_ADVICES_PER_DAY: int = 2

#: After this many positive-advice logs, the advice gets promoted to a Habit
#: row (same behaviour we use on the device-mining side).
ADVICE_HABIT_LOG_THRESHOLD: int = 10

#: How many days back the streak engine walks before resetting.
STREAK_LOOKBACK_DAYS: int = 365


# Catalog key → DB enum mapping (kept here so the catalog file stays UI-only).
_CATEGORY_BY_KEY: dict[str, AdviceCategory] = {
    "reading_time": AdviceCategory.Reading,
    "hydration": AdviceCategory.Water,
    "sleep_routine": AdviceCategory.Sleep,
    "morning_sunlight": AdviceCategory.Mindfulness,
    "screen_curfew": AdviceCategory.Mindfulness,
    "posture_break": AdviceCategory.Exercise,
    "light_walk": AdviceCategory.Exercise,
    "brisk_walk": AdviceCategory.Exercise,
    "strength_training": AdviceCategory.Exercise,
    "low_impact_mobility": AdviceCategory.Exercise,
    "fruit_break": AdviceCategory.Other,
    "high_protein_snack": AdviceCategory.Other,
    "calorie_dense_meal": AdviceCategory.Other,
    "portion_control": AdviceCategory.Other,
    "reduce_sugar": AdviceCategory.Other,
}


def category_for_key(advice_key: str) -> AdviceCategory:
    return _CATEGORY_BY_KEY.get(advice_key, AdviceCategory.Other)


# ---------------------------------------------------------------------------
# Catalog seeding (called at startup)
# ---------------------------------------------------------------------------


def seed_advice_catalog(session: Session) -> int:
    """Make sure every advice in ``ADVICE_CATALOG`` exists in ``positive_advices``.

    Returns the number of newly-inserted rows. Existing rows are not touched.
    """
    existing_titles = {
        row.title for row in session.exec(select(PositiveAdvice))
    }
    inserted = 0
    for key, item in ADVICE_CATALOG.items():
        title = item["title"]
        if title in existing_titles:
            continue
        session.add(
            PositiveAdvice(
                title=title,
                description=item.get("summary"),
                category=category_for_key(key),
            )
        )
        inserted += 1
    if inserted:
        try:
            session.commit()
        except Exception as exc:  # pragma: no cover - defensive
            session.rollback()
            logger.warning("seed_advice_catalog failed: %s", exc)
            return 0
        logger.info("positive_advices catalog seeded: %d new rows", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Logging completions
# ---------------------------------------------------------------------------


def log_advice_completion(
    *,
    user_id: str,
    advice_key: str,
    duration_minutes: int = 0,
    completed_at: datetime | None = None,
    session: Session,
) -> PositiveAdviceLog:
    """Persist a single positive-advice completion and refresh derived data."""
    if advice_key not in ADVICE_CATALOG:
        raise HTTPException(
            status_code=400, detail=f"Bilinmeyen advice_key: {advice_key}"
        )

    item = ADVICE_CATALOG[advice_key]
    log = PositiveAdviceLog(
        user_id=user_id,
        advice_key=advice_key,
        advice_title=item["title"],
        category=category_for_key(advice_key),
        completed_at=completed_at or datetime.now(UTC),
        duration_minutes=max(0, int(duration_minutes)),
    )
    session.add(log)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=400, detail=f"PositiveAdviceLog kaydedilemedi: {exc}"
        ) from exc
    session.refresh(log)

    recompute_daily_streak(user_id, session)
    maybe_promote_advice_to_habit(user_id, advice_key, session)
    return log


def list_advice_logs(
    user_id: str,
    *,
    session: Session,
    limit: int = 200,
) -> list[PositiveAdviceLog]:
    rows = list(
        session.exec(
            select(PositiveAdviceLog)
            .where(PositiveAdviceLog.user_id == user_id)
            .order_by(PositiveAdviceLog.completed_at.desc())
            .limit(limit)
        )
    )
    return rows


# ---------------------------------------------------------------------------
# Streak engine
# ---------------------------------------------------------------------------


def _completions_by_day(
    user_id: str, session: Session, *, lookback_days: int
) -> dict[date, set[str]]:
    """Group the user's logs by calendar day (UTC) → set of advice_keys."""
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    rows = list(
        session.exec(
            select(PositiveAdviceLog).where(
                PositiveAdviceLog.user_id == user_id,
                PositiveAdviceLog.completed_at >= cutoff,
            )
        )
    )
    by_day: dict[date, set[str]] = defaultdict(set)
    for r in rows:
        by_day[r.completed_at.date()].add(r.advice_key)
    return by_day


def _streak_from_history(by_day: dict[date, set[str]], today: date) -> tuple[int, date | None]:
    """Walk backwards from today to compute the current streak.

    Today itself counts only if it already qualifies. Otherwise we start the
    walk from yesterday so a not-yet-completed today doesn't reset progress.
    """
    def qualifies(d: date) -> bool:
        return len(by_day.get(d, set())) >= QUALIFYING_ADVICES_PER_DAY

    start = today if qualifies(today) else today - timedelta(days=1)
    streak = 0
    last_qualifying: date | None = None
    cursor = start
    while qualifies(cursor):
        streak += 1
        if last_qualifying is None:
            last_qualifying = cursor
        cursor -= timedelta(days=1)
    return streak, last_qualifying


def recompute_daily_streak(user_id: str, session: Session) -> UserDailyStreak:
    """Recompute and persist the user's daily streak row."""
    by_day = _completions_by_day(user_id, session, lookback_days=STREAK_LOOKBACK_DAYS)
    today = datetime.now(UTC).date()
    current, last_qual = _streak_from_history(by_day, today)

    row = session.get(UserDailyStreak, user_id)
    if row is None:
        row = UserDailyStreak(user_id=user_id, current_streak=0, max_streak=0)
        session.add(row)

    row.current_streak = current
    row.max_streak = max(row.max_streak, current)
    row.last_qualifying_date = last_qual
    row.updated_at = datetime.now(UTC)

    try:
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        session.rollback()
        logger.warning("recompute_daily_streak failed for %s: %s", user_id, exc)
        return row
    session.refresh(row)
    return row


def get_daily_streak(user_id: str, session: Session) -> dict[str, Any]:
    """Read the streak (recomputing if missing) and add today's qualifying counter."""
    row = session.get(UserDailyStreak, user_id)
    if row is None:
        row = recompute_daily_streak(user_id, session)
    by_day = _completions_by_day(user_id, session, lookback_days=1)
    today = datetime.now(UTC).date()
    completed_today = sorted(by_day.get(today, set()))
    return {
        "user_id": user_id,
        "current_streak": int(row.current_streak),
        "max_streak": int(row.max_streak),
        "last_qualifying_date": row.last_qualifying_date.isoformat()
        if row.last_qualifying_date
        else None,
        "qualifying_threshold": QUALIFYING_ADVICES_PER_DAY,
        "completed_today_count": len(completed_today),
        "completed_today_keys": completed_today,
        "qualifies_today": len(completed_today) >= QUALIFYING_ADVICES_PER_DAY,
    }


# ---------------------------------------------------------------------------
# Advice → Habit promotion (>= 10 logs)
# ---------------------------------------------------------------------------


def _habit_name_for_advice(advice_key: str) -> str:
    item = ADVICE_CATALOG.get(advice_key)
    title = item["title"] if item else advice_key.replace("_", " ").title()
    return f"Advice: {title}"


def maybe_promote_advice_to_habit(
    user_id: str, advice_key: str, session: Session
) -> Habit | None:
    """Upsert a Habit row when the user has >= 10 logs for ``advice_key``."""
    count = len(
        list(
            session.exec(
                select(PositiveAdviceLog).where(
                    PositiveAdviceLog.user_id == user_id,
                    PositiveAdviceLog.advice_key == advice_key,
                )
            )
        )
    )
    if count < ADVICE_HABIT_LOG_THRESHOLD:
        return None

    name = _habit_name_for_advice(advice_key)
    existing = list(
        session.exec(
            select(Habit).where(Habit.user_id == user_id, Habit.name == name)
        )
    )
    # Probability proxy: 0.60 at exactly the threshold, growing logarithmically
    # toward 0.95 as the log count climbs. Caps at 0.95 to leave headroom.
    import math

    growth = min(0.95, 0.60 + 0.05 * math.log2(max(1, count - ADVICE_HABIT_LOG_THRESHOLD + 1)))
    prob = Decimal(str(round(growth, 2)))

    if existing:
        habit = existing[0]
        habit.probability_score = prob
        habit.is_active = True
        session.add(habit)
    else:
        habit = Habit(
            user_id=user_id,
            name=name,
            probability_score=prob,
            is_active=True,
            recurrence_type=HabitRecurrence.Daily,
            device_id=None,
        )
        session.add(habit)

    try:
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        session.rollback()
        logger.warning("habit promotion failed for %s/%s: %s", user_id, advice_key, exc)
        return None
    session.refresh(habit)
    return habit

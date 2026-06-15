"""Generate one month of realistic mock usage for the 12 test accounts.

Design notes
------------
* **Environments are left untouched** — they were created by the user. We only
  rewrite the *devices* inside them, the behaviour logs, advice logs, streaks
  and notifications.
* **Canonical English devices only.** Every environment is reset to a clean,
  single-instance set: one ``Lamp``, one ``AC``, ``Washing Machine``, ``Oven``,
  ``Dishwasher`` — the only lamp variant is ``Lamp (Tuya)``. No
  "Living Room AC"/"Bedroom AC" style duplicates.
* **Per-environment-kind layout**
    - ``... Office``       → only ``AC``
    - ``... Home``         → a mixed subset (varies per home)
    - ``... Summer House`` → ``Lamp`` + ``AC``
    - ``My Room``          → ``Lamp (Tuya)``
    - anything else        → ``Lamp``
* **Per-user habit device.** Each "device-habit" user earns a routine from ONE
  specific device (e.g. test2 → only ``AC``); other devices are touched
  sporadically so no extra habit forms.
* **Advice habits / streaks / day-31 notifications** as before.

Run:
    python -m scripts.seed_month_mock
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import text
from sqlmodel import Session, select

from app.application.services import notification_service
from app.application.services.positive_advice_service import (
    category_for_key,
    maybe_promote_advice_to_habit,
    recompute_daily_streak,
)
from app.application.services.recommendation_catalog import ADVICE_CATALOG
from app.application.services.smart_home_service import detect_device_routines
from app.core.models import (
    BehaviorLog,
    Device,
    DeviceType,
    Environment,
    PositiveAdviceLog,
    User,
    UserEnvironment,
)
from app.db.database import engine

# Istanbul wall-clock so behaviour timestamps (and the resulting "@HH" routine
# names) read as local time instead of UTC.
TR = timezone(timedelta(hours=3))

DAYS = 30  # days 1..30 == (today-30) .. (today-1); today is the fresh "day 31"

TEST_USERS = [f"P{n:07d}" for n in range(18, 30)]  # P0000018 .. P0000029

# Canonical device catalog: name -> (DeviceType, on_hour, on_duration_minutes)
DEVICE_SPECS: dict[str, tuple[DeviceType, int, int]] = {
    "Lamp": (DeviceType.Lamp, 19, 180),
    "Lamp (Tuya)": (DeviceType.Lamp, 7, 60),
    "AC": (DeviceType.Thermostat, 14, 180),
    "Washing Machine": (DeviceType.Plug, 20, 90),
    "Oven": (DeviceType.Plug, 18, 60),
    "Dishwasher": (DeviceType.Plug, 21, 120),
}

# Mixed device layout per home (kept different so homes aren't identical).
HOME_DEVICE_SETS: dict[str, list[str]] = {
    "H0000016": ["Lamp", "AC", "Washing Machine"],          # Istanbul Home
    "H0000017": ["Lamp", "AC", "Oven", "Dishwasher"],       # Ankara Home
    "H0000018": ["Lamp", "AC", "Dishwasher"],               # Izmir Home
}

# Two-key pair the "advice-habit" users repeat every single day.
FIXED_ADVICE_PAIR = ["hydration", "reading_time"]
# Pool the non-advice-habit users rotate through (so no key hits 10 logs).
ROTATE_ADVICE = [
    "hydration",
    "reading_time",
    "light_walk",
    "sleep_routine",
    "posture_break",
    "morning_sunlight",
    "fruit_break",
    "brisk_walk",
]

# Per-user profile:
#   (current_streak, earns_advice_habit, habit_device_name | None)
# Index 0 == test1 (P0000018) ... index 11 == test12 (P0000029).
# habit_device_name None  → no device routine for this user.
PROFILES: list[tuple[int, bool, str | None]] = [
    (30, True,  "Lamp"),            # test1
    (30, True,  "AC"),              # test2  (user's example: habit only from AC)
    (27, True,  None),              # test3
    (24, False, "Washing Machine"), # test4
    (21, True,  "AC"),              # test5
    (18, False, None),              # test6
    (15, True,  "Oven"),            # test7
    (12, True,  None),              # test8
    (10, False, "Lamp"),            # test9
    (10, False, None),              # test10
    (7,  False, "Dishwasher"),      # test11
    (4,  False, None),              # test12
]

GENDERS = ["Erkek", "Kadin"]


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _device_names_for_env(env: Environment) -> list[str]:
    name = (env.name or "").lower()
    if "office" in name:
        return ["AC"]
    if "summer house" in name:
        return ["Lamp", "AC"]
    if "my room" in name:
        return ["Lamp (Tuya)"]
    if "home" in name:
        return HOME_DEVICE_SETS.get(env.id, ["Lamp", "AC"])
    return ["Lamp"]


def _reset_env_devices(session: Session, env: Environment) -> dict[str, Device]:
    """Wipe an environment's devices (and their logs/habits) and recreate the
    clean canonical English set. Returns name -> Device."""
    old = session.exec(
        select(Device).where(Device.environment_id == env.id)
    ).all()
    if old:
        ids = ",".join(str(d.id) for d in old)
        conn = session.connection()
        conn.execute(text(f"DELETE FROM behavior_logs WHERE device_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM habits WHERE device_id IN ({ids})"))
        conn.execute(text(f"DELETE FROM devices WHERE id IN ({ids})"))
        session.commit()

    out: dict[str, Device] = {}
    for dev_name in _device_names_for_env(env):
        dtype, _, _ = DEVICE_SPECS[dev_name]
        dev = Device(
            environment_id=env.id,
            type=dtype,
            status=False,
            name=dev_name,
            room="Home",
        )
        session.add(dev)
        session.flush()
        out[dev_name] = dev
    session.commit()
    return out


def _wipe_user_activity(session: Session) -> None:
    """Delete derived activity for the 12 test users (keeps accounts/envs)."""
    ids = ",".join(f"'{u}'" for u in TEST_USERS)
    conn = session.connection()
    for t in [
        "notifications",
        "advice_schedules",
        "positive_advice_logs",
        "user_daily_streaks",
        "user_streaks",
        "behavior_logs",
        "habits",
    ]:
        try:
            conn.execute(text(f"DELETE FROM {t} WHERE user_id IN ({ids})"))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  ! skip {t}: {exc}")
    session.commit()


# ---------------------------------------------------------------------------
# Log seeding
# ---------------------------------------------------------------------------


def _emit_device_day(
    session: Session,
    *,
    user_id: str,
    device: Device,
    day_index: int,
    today_local: datetime,
    rng: random.Random,
) -> None:
    spec = DEVICE_SPECS.get(device.name or "Lamp", (DeviceType.Lamp, 19, 120))
    _, on_hour, dur_min = spec
    days_ago = DAYS - day_index  # day_index 0 == 30 days ago, DAYS-1 == yesterday
    base = (today_local - timedelta(days=days_ago)).replace(
        hour=on_hour, minute=0, second=0, microsecond=0
    )
    on = base + timedelta(minutes=rng.randint(-10, 10))  # +-10 min smoothing
    off = on + timedelta(minutes=dur_min + rng.randint(-10, 10))
    session.add(
        BehaviorLog(
            user_id=user_id,
            device_id=device.id,
            action="TurnOn",
            event_time=on,
            parameters="mock_month",
        )
    )
    session.add(
        BehaviorLog(
            user_id=user_id,
            device_id=device.id,
            action="TurnOff",
            event_time=off,
            duration_hm=(off - on),
            parameters="mock_month",
        )
    )


def _seed_advice_logs(
    session: Session,
    *,
    user_id: str,
    streak_days: int,
    earns_advice_habit: bool,
    today_utc_date,
) -> set[str]:
    used: set[str] = set()
    for d in range(streak_days):
        # day = yesterday, day-before, ... so the streak ends yesterday and
        # leaves "today" (day 31) fresh.
        log_date = today_utc_date - timedelta(days=d + 1)
        completed_at = datetime(
            log_date.year, log_date.month, log_date.day, 12, 0, tzinfo=UTC
        )
        if earns_advice_habit:
            keys = list(FIXED_ADVICE_PAIR)
        else:
            i = (d * 2) % len(ROTATE_ADVICE)
            keys = [ROTATE_ADVICE[i], ROTATE_ADVICE[(i + 1) % len(ROTATE_ADVICE)]]
        for key in keys:
            item = ADVICE_CATALOG[key]
            session.add(
                PositiveAdviceLog(
                    user_id=user_id,
                    advice_key=key,
                    advice_title=item["title"],
                    category=category_for_key(key),
                    completed_at=completed_at,
                    duration_minutes=20,
                )
            )
            used.add(key)
    session.commit()
    return used


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _user_envs(session: Session, user_id: str) -> list[Environment]:
    """Environments the user belongs to, with Home environments listed first."""
    env_ids = session.exec(
        select(UserEnvironment.environment_id).where(
            UserEnvironment.user_id == user_id
        )
    ).all()
    envs = [session.get(Environment, eid) for eid in env_ids]
    envs = [e for e in envs if e is not None]
    envs.sort(key=lambda e: 0 if "home" in (e.name or "").lower() else 1)
    return envs


def main() -> None:
    rng = random.Random(31)  # deterministic
    now_local = datetime.now(TR)
    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc_date = datetime.now(UTC).date()

    with Session(engine) as session:
        print("Wiping previous activity for 12 test users ...")
        _wipe_user_activity(session)

        # Reset devices in every environment any test user belongs to.
        print("Rebuilding clean English device sets per environment ...")
        test_env_ids: set[str] = set()
        for u in TEST_USERS:
            for eid in session.exec(
                select(UserEnvironment.environment_id).where(
                    UserEnvironment.user_id == u
                )
            ).all():
                test_env_ids.add(eid)

        env_devices: dict[str, dict[str, Device]] = {}
        for eid in sorted(test_env_ids):
            env = session.get(Environment, eid)
            if env is None:
                continue
            env_devices[eid] = _reset_env_devices(session, env)
            names = ", ".join(env_devices[eid].keys())
            print(f"  {eid} {env.name:24s} -> [{names}]")

        print("Assigning gender + seeding 30 days of usage ...")
        for idx, user_id in enumerate(TEST_USERS):
            user = session.get(User, user_id)
            if user is None:
                print(f"  ! {user_id} missing, skip")
                continue
            streak_days, earns_advice, habit_device_name = PROFILES[idx]

            # 1) gender
            user.gender = rng.choice(GENDERS)
            session.add(user)
            session.commit()

            envs = _user_envs(session, user_id)

            # 2) device behaviour logs (one habit device + sporadic others)
            habit_dev: Device | None = None
            if habit_device_name:
                for e in envs:
                    d = env_devices.get(e.id, {}).get(habit_device_name)
                    if d is not None:
                        habit_dev = d
                        break

            if habit_dev is not None:
                # ~26/30 active days → strong recency-weighted routine.
                skip = set(rng.sample(range(DAYS), 4))
                for d in range(DAYS):
                    if d in skip:
                        continue
                    _emit_device_day(
                        session,
                        user_id=user_id,
                        device=habit_dev,
                        day_index=d,
                        today_local=today_local,
                        rng=rng,
                    )

            # Sporadic touches on another device in the user's home (no habit:
            # < ROUTINE_MIN_ACTIVE_DAYS active days).
            other_devs = [
                d
                for e in envs
                for d in env_devices.get(e.id, {}).values()
                if habit_dev is None or d.id != habit_dev.id
            ]
            if other_devs:
                extra = other_devs[0]
                for d in sorted(rng.sample(range(DAYS), 3)):
                    _emit_device_day(
                        session,
                        user_id=user_id,
                        device=extra,
                        day_index=d,
                        today_local=today_local,
                        rng=rng,
                    )
            session.commit()

            # 3) advice completions → streak + advice habits
            used_keys = _seed_advice_logs(
                session,
                user_id=user_id,
                streak_days=streak_days,
                earns_advice_habit=earns_advice,
                today_utc_date=today_utc_date,
            )
            recompute_daily_streak(user_id, session)
            for key in used_keys:
                maybe_promote_advice_to_habit(user_id, key, session)

            print(
                f"  {user_id} g={user.gender:5s} streak={streak_days:2d} "
                f"advice_habit={earns_advice} "
                f"habit_device={habit_device_name if habit_dev else None}"
            )

        # 4) Mine single-action device routines against "now".
        print("Detecting device routines ...")
        routines = detect_device_routines(session, reference_time=datetime.now(UTC))
        print(f"  routine habits touched: {routines}")

        # 5) Day-31 notifications, fired against the current clock.
        print("Seeding day-31 notifications ...")
        g = notification_service.generate_morning_greetings(session)
        r = notification_service.generate_device_routine_reminders(session)
        a = notification_service.generate_advice_habit_reminders(session)
        m = notification_service.generate_streak_milestones(session)
        sr = notification_service.generate_streak_risk_reminders(session)
        fired = notification_service.fire_due_notifications(session)
        notification_service.expire_overdue(session)
        print(
            f"  greetings={g} routine_reminders={r} advice_reminders={a} "
            f"milestones={m} streak_risk={sr} fired_now={fired}"
        )

    print("Done.")


if __name__ == "__main__":
    main()

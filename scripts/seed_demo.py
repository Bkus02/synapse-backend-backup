"""Seed demo data for streak / habit / advice testing.

Creates 12 deterministic users (test1..test12), 9 environments (Home/Office/
Summer House) plus one personal "My Room" environment for test1, the
corresponding devices, and 30 days of realistic BehaviorLog entries so the
dashboard streak counter and habit-matrix scheduler have something to work with.

Run from the project root (after activating the venv):

    python -m scripts.seed_demo --reset

Use --reset to remove the previous demo data first (idempotent re-runs).
"""

from __future__ import annotations

import argparse
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Sequence

from sqlalchemy import text
from sqlmodel import Session, select

from app.api.schemas import (
    BehaviorLogCreate,
    DeviceCreate,
    EnvironmentCreate,
    UserCreate,
)
from app.application.services import positive_advice_service, smart_home_service
from app.application.services.recommendation_catalog import ADVICE_CATALOG
from app.core.models import (
    Device,
    DeviceType,
    Environment,
    Habit,
    HabitRecurrence,
    User,
    UserEnvironment,
)
from app.db.database import engine
from decimal import Decimal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEMO_EMAIL_PREFIX = "test"
DEMO_EMAIL_DOMAIN = "@gmail.com"


# -----------------------------------------------------------------------------
# User matrix
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class UserSeed:
    index: int  # 1..12
    full_name: str
    city: str
    age: int
    height: int
    weight: int
    gender: str

    @property
    def email(self) -> str:
        return f"{DEMO_EMAIL_PREFIX}{self.index}{DEMO_EMAIL_DOMAIN}"

    @property
    def password(self) -> str:
        return str(self.index)


USERS: list[UserSeed] = [
    # Istanbul (4 ages × 1 user)
    UserSeed(1, "Test One", "istanbul", 25, 178, 70, "Erkek"),
    UserSeed(2, "Test Two", "istanbul", 35, 168, 72, "Kadın"),
    UserSeed(3, "Test Three", "istanbul", 50, 175, 95, "Erkek"),
    UserSeed(4, "Test Four", "istanbul", 65, 162, 60, "Kadın"),
    # Ankara
    UserSeed(5, "Test Five", "ankara", 25, 172, 60, "Kadın"),
    UserSeed(6, "Test Six", "ankara", 35, 180, 100, "Erkek"),
    UserSeed(7, "Test Seven", "ankara", 50, 167, 70, "Kadın"),
    UserSeed(8, "Test Eight", "ankara", 65, 170, 78, "Erkek"),
    # Izmir
    UserSeed(9, "Test Nine", "izmir", 25, 165, 52, "Kadın"),
    UserSeed(10, "Test Ten", "izmir", 35, 182, 84, "Erkek"),
    UserSeed(11, "Test Eleven", "izmir", 50, 169, 76, "Kadın"),
    UserSeed(12, "Test Twelve", "izmir", 65, 174, 80, "Erkek"),
]


# -----------------------------------------------------------------------------
# Environment + device plan
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceSeed:
    name: str
    type: DeviceType
    room: str | None = None


HOME_DEVICES = (
    DeviceSeed("Living Room Lamp", DeviceType.Lamp, "Living Room"),
    DeviceSeed("Living Room AC", DeviceType.Thermostat, "Living Room"),
    DeviceSeed("Bedroom Thermostat", DeviceType.Thermostat, "Bedroom"),
    DeviceSeed("Kitchen Oven", DeviceType.Plug, "Kitchen"),
    DeviceSeed("Dishwasher", DeviceType.Plug, "Kitchen"),
    DeviceSeed("Washing Machine", DeviceType.Plug, "Bathroom"),
)
OFFICE_DEVICES = (DeviceSeed("Office AC", DeviceType.Thermostat, "Office"),)
SUMMER_DEVICES = (
    DeviceSeed("Summer House Lamp", DeviceType.Lamp, "Living Room"),
    DeviceSeed("Summer House AC", DeviceType.Thermostat, "Living Room"),
)
MY_ROOM_DEVICES = (
    DeviceSeed("My Room Lamp (Tuya)", DeviceType.Lamp, "Bedroom"),
)


@dataclass(frozen=True)
class EnvironmentSeed:
    key: str  # internal lookup key
    name: str
    location: str
    icon_key: str
    admin_index: int
    member_indices: Sequence[int]
    devices: Sequence[DeviceSeed]


ENVIRONMENTS: list[EnvironmentSeed] = [
    # ---- Home environments (4 members each) ----
    EnvironmentSeed("home_istanbul", "Istanbul Home", "Istanbul", "home", 1, (1, 2, 3, 4), HOME_DEVICES),
    EnvironmentSeed("home_ankara", "Ankara Home", "Ankara", "home", 5, (5, 6, 7, 8), HOME_DEVICES),
    EnvironmentSeed("home_izmir", "Izmir Home", "Izmir", "home", 9, (9, 10, 11, 12), HOME_DEVICES),
    # ---- Office environments (young + adult per city) ----
    EnvironmentSeed("office_istanbul", "Istanbul Office", "Istanbul", "office", 1, (1, 2), OFFICE_DEVICES),
    EnvironmentSeed("office_ankara", "Ankara Office", "Ankara", "office", 5, (5, 6), OFFICE_DEVICES),
    EnvironmentSeed("office_izmir", "Izmir Office", "Izmir", "office", 9, (9, 10), OFFICE_DEVICES),
    # ---- Summer houses (senior only, per city) ----
    EnvironmentSeed("summer_istanbul", "Istanbul Summer House", "Istanbul", "vacation", 4, (4,), SUMMER_DEVICES),
    EnvironmentSeed("summer_ankara", "Ankara Summer House", "Ankara", "vacation", 8, (8,), SUMMER_DEVICES),
    EnvironmentSeed("summer_izmir", "Izmir Summer House", "Izmir", "vacation", 12, (12,), SUMMER_DEVICES),
    # ---- Personal "My Room" for test1 (Tuya lamp lives here) ----
    EnvironmentSeed("my_room_test1", "My Room", "Istanbul", "bedroom", 1, (1,), MY_ROOM_DEVICES),
]


# -----------------------------------------------------------------------------
# Behavior log usage plan
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageSlot:
    """Daily on/off slot for a single device, in local 24h time."""

    device_name: str
    env_key: str
    on_hour: int
    on_minute: int
    off_hour: int
    off_minute: int
    weekdays_only: bool = False
    weekends_only: bool = False
    skip_chance: float = 0.15  # probability of skipping the day (streak variance)


# Per-user usage slots. Natural A→B chains intentionally engineered so that
# sequence_miner can lift them as candidate habit pairs (15-min window):
#   - AC OFF → 5–10 min later Oven ON (dinner ritual starts)
#   - Oven OFF → 10 min later Dishwasher ON (post-meal cleanup)
#   - Washing Machine → morning or weekend routine
USER_USAGE: dict[int, tuple[UsageSlot, ...]] = {
    1: (  # young Istanbul — lamp + office AC + Tuya bedside + weekend laundry
        UsageSlot("Living Room Lamp", "home_istanbul", 18, 30, 23, 0, skip_chance=0.10),
        UsageSlot("Office AC", "office_istanbul", 9, 0, 17, 0, weekdays_only=True, skip_chance=0.20),
        UsageSlot("My Room Lamp (Tuya)", "my_room_test1", 22, 0, 0, 30, skip_chance=0.10),
        UsageSlot("Washing Machine", "home_istanbul", 10, 0, 11, 30, weekends_only=True, skip_chance=0.20),
    ),
    2: (  # adult Istanbul — AC → OVEN → DISHWASHER chain (dinner ritual)
        UsageSlot("Living Room Lamp", "home_istanbul", 19, 0, 23, 30, skip_chance=0.15),
        UsageSlot("Living Room AC", "home_istanbul", 17, 30, 19, 50, skip_chance=0.15),
        UsageSlot("Kitchen Oven", "home_istanbul", 20, 0, 21, 0, skip_chance=0.10),  # +10 min after AC OFF
        UsageSlot("Dishwasher", "home_istanbul", 21, 10, 22, 30, skip_chance=0.15),  # +10 min after Oven OFF
        UsageSlot("Office AC", "office_istanbul", 9, 0, 18, 0, weekdays_only=True, skip_chance=0.25),
    ),
    3: (  # middle Istanbul — thermostat routine + after-dinner dishwasher
        UsageSlot("Living Room Lamp", "home_istanbul", 18, 0, 22, 0, skip_chance=0.20),
        UsageSlot("Bedroom Thermostat", "home_istanbul", 7, 0, 7, 5, skip_chance=0.25),
        UsageSlot("Bedroom Thermostat", "home_istanbul", 19, 0, 19, 5, skip_chance=0.25),
        UsageSlot("Kitchen Oven", "home_istanbul", 19, 30, 20, 30, skip_chance=0.20),
        UsageSlot("Dishwasher", "home_istanbul", 20, 40, 22, 0, skip_chance=0.20),
    ),
    4: (  # senior Istanbul — AC → OVEN chain + weekend summer house
        UsageSlot("Living Room Lamp", "home_istanbul", 17, 0, 22, 0, skip_chance=0.10),
        UsageSlot("Living Room AC", "home_istanbul", 15, 0, 17, 50, skip_chance=0.20),
        UsageSlot("Kitchen Oven", "home_istanbul", 18, 0, 19, 30, skip_chance=0.15),  # +10 min after AC OFF
        UsageSlot("Summer House Lamp", "summer_istanbul", 19, 0, 23, 0, weekends_only=True, skip_chance=0.20),
    ),
    5: (  # young Ankara — simple usage
        UsageSlot("Living Room Lamp", "home_ankara", 18, 30, 23, 0, skip_chance=0.15),
        UsageSlot("Office AC", "office_ankara", 9, 0, 17, 0, weekdays_only=True, skip_chance=0.30),
    ),
    6: (  # adult Ankara — AC → OVEN → DISHWASHER + office AC
        UsageSlot("Living Room Lamp", "home_ankara", 19, 0, 23, 30, skip_chance=0.10),
        UsageSlot("Living Room AC", "home_ankara", 17, 0, 19, 50, skip_chance=0.20),
        UsageSlot("Kitchen Oven", "home_ankara", 20, 0, 21, 0, skip_chance=0.15),  # +10 min after AC OFF
        UsageSlot("Dishwasher", "home_ankara", 21, 10, 22, 30, skip_chance=0.20),  # +10 min after Oven OFF
        UsageSlot("Office AC", "office_ankara", 9, 0, 18, 0, weekdays_only=True, skip_chance=0.20),
    ),
    7: (  # middle Ankara — full chain (most engaged user, ideal mining target)
        UsageSlot("Living Room Lamp", "home_ankara", 18, 0, 22, 30, skip_chance=0.05),
        UsageSlot("Living Room AC", "home_ankara", 16, 0, 18, 50, skip_chance=0.10),
        UsageSlot("Kitchen Oven", "home_ankara", 19, 0, 20, 30, skip_chance=0.05),  # +10 min after AC OFF
        UsageSlot("Dishwasher", "home_ankara", 20, 40, 22, 0, skip_chance=0.10),  # +10 min after Oven OFF
        UsageSlot("Bedroom Thermostat", "home_ankara", 7, 0, 7, 5, skip_chance=0.10),
        UsageSlot("Bedroom Thermostat", "home_ankara", 22, 0, 22, 5, skip_chance=0.10),
        UsageSlot("Washing Machine", "home_ankara", 10, 0, 11, 30, weekends_only=True, skip_chance=0.10),
    ),
    8: (  # senior Ankara — lamp + summer house (weekend)
        UsageSlot("Living Room Lamp", "home_ankara", 17, 30, 22, 0, skip_chance=0.10),
        UsageSlot("Kitchen Oven", "home_ankara", 18, 0, 19, 30, skip_chance=0.25),
        UsageSlot("Summer House Lamp", "summer_ankara", 19, 0, 23, 0, weekends_only=True, skip_chance=0.20),
        UsageSlot("Summer House AC", "summer_ankara", 14, 0, 18, 0, weekends_only=True, skip_chance=0.30),
    ),
    9: (  # young Izmir — minimal use, only lamp
        UsageSlot("Living Room Lamp", "home_izmir", 20, 0, 23, 30, skip_chance=0.45),
    ),
    10: (  # adult Izmir — AC → OVEN chain + office
        UsageSlot("Living Room Lamp", "home_izmir", 19, 0, 23, 0, skip_chance=0.15),
        UsageSlot("Living Room AC", "home_izmir", 16, 0, 18, 50, skip_chance=0.20),
        UsageSlot("Kitchen Oven", "home_izmir", 19, 0, 20, 0, skip_chance=0.20),  # +10 min after AC OFF
        UsageSlot("Dishwasher", "home_izmir", 20, 10, 21, 30, skip_chance=0.25),  # +10 min after Oven OFF
        UsageSlot("Office AC", "office_izmir", 9, 0, 18, 0, weekdays_only=True, skip_chance=0.20),
    ),
    11: (  # middle Izmir — Mediterranean summer routine
        UsageSlot("Living Room Lamp", "home_izmir", 18, 0, 22, 30, skip_chance=0.15),
        UsageSlot("Living Room AC", "home_izmir", 13, 0, 17, 0, skip_chance=0.25),
        UsageSlot("Bedroom Thermostat", "home_izmir", 7, 0, 7, 5, skip_chance=0.30),
        UsageSlot("Washing Machine", "home_izmir", 9, 0, 10, 30, skip_chance=0.40),
    ),
    12: (  # senior Izmir — intense summer house + AC → OVEN chain
        UsageSlot("Living Room Lamp", "home_izmir", 17, 30, 22, 0, skip_chance=0.10),
        UsageSlot("Living Room AC", "home_izmir", 15, 0, 17, 50, skip_chance=0.20),
        UsageSlot("Kitchen Oven", "home_izmir", 18, 0, 19, 30, skip_chance=0.20),  # +10 min after AC OFF
        UsageSlot("Summer House Lamp", "summer_izmir", 19, 0, 23, 0, weekends_only=True, skip_chance=0.10),
        UsageSlot("Summer House AC", "summer_izmir", 13, 0, 18, 0, weekends_only=True, skip_chance=0.15),
    ),
}


# -----------------------------------------------------------------------------
# Positive advice usage plan (1 month behaviour)
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvicePlan:
    """How often a user completes a given advice and how long it takes.

    ``is_core``:
        True  → "habit-bound" advice. Always performed on qualifying days
                → 10+ logs → automatic Habit row is created.
        False → "extra" advice. Performed sporadically with low probability
                → never reaches the 10-log threshold → never becomes a habit.
    """

    advice_key: str
    is_core: bool
    duration_minutes: int
    preferred_hour: int = 9
    extra_chance: float = 0.18  # daily probability that an extra advice runs


# Per-user deterministic target_streak:
#   - Last ``target_streak`` days are consecutive-qualifying (≥2 advice/day)
#   - The day right before the window is a breaker that snaps the streak
#   - Older days are random (~70% qualify) → max_streak may exceed the target
USER_STREAK_TARGET: dict[int, int] = {
    1: 30,   # perfect run (every day)
    2: 10,   # mid range
    3: 3,    # low
    4: 25,   # high
    5: 1,    # barely any
    6: 15,   # mid-high
    7: 28,   # very disciplined (nearly perfect)
    8: 5,    # low
    9: 0,    # streak broken today
    10: 18,  # mid-high
    11: 20,  # mid-high
    12: 7,   # mid-low
}


# Each user has 4 advices (BMI×age catalog). The first 2 are core (become
# habits), the last 2 are extras (sporadic; never reach the habit threshold).
# On qualifying days the core advices are always completed (2 distinct ⇒
# day qualifies), while the extras drop in occasionally.
ADVICE_USAGE: dict[int, tuple[AdvicePlan, ...]] = {
    1: (
        AdvicePlan("strength_training", True, 35, 18),
        AdvicePlan("hydration", True, 5, 10),
        AdvicePlan("light_walk", False, 20, 12),
        AdvicePlan("reading_time", False, 30, 22),
    ),
    2: (
        AdvicePlan("light_walk", True, 25, 13),
        AdvicePlan("posture_break", True, 5, 15),
        AdvicePlan("strength_training", False, 30, 19),
        AdvicePlan("sleep_routine", False, 480, 23),
    ),
    3: (
        AdvicePlan("brisk_walk", True, 30, 17),
        AdvicePlan("portion_control", True, 0, 13),
        AdvicePlan("reduce_sugar", False, 0, 9),
        AdvicePlan("posture_break", False, 5, 14),
    ),
    4: (
        AdvicePlan("morning_sunlight", True, 15, 8),
        AdvicePlan("light_walk", True, 25, 11),
        AdvicePlan("posture_break", False, 5, 15),
        AdvicePlan("hydration", False, 5, 16),
    ),
    5: (
        AdvicePlan("hydration", True, 5, 10),
        AdvicePlan("light_walk", True, 20, 13),
        AdvicePlan("strength_training", False, 30, 18),
        AdvicePlan("reading_time", False, 25, 22),
    ),
    6: (
        AdvicePlan("portion_control", True, 0, 13),
        AdvicePlan("brisk_walk", True, 30, 17),
        AdvicePlan("reduce_sugar", False, 0, 10),
        AdvicePlan("high_protein_snack", False, 10, 11),
    ),
    7: (
        AdvicePlan("light_walk", True, 30, 12),
        AdvicePlan("morning_sunlight", True, 15, 8),
        AdvicePlan("posture_break", False, 5, 15),
        AdvicePlan("sleep_routine", False, 480, 23),
    ),
    8: (
        AdvicePlan("morning_sunlight", True, 15, 9),
        AdvicePlan("hydration", True, 5, 16),
        AdvicePlan("light_walk", False, 20, 11),
        AdvicePlan("posture_break", False, 5, 15),
    ),
    9: (
        AdvicePlan("high_protein_snack", True, 10, 10),
        AdvicePlan("calorie_dense_meal", True, 0, 13),
        AdvicePlan("strength_training", False, 30, 19),
        AdvicePlan("reading_time", False, 20, 22),
    ),
    10: (
        AdvicePlan("brisk_walk", True, 35, 18),
        AdvicePlan("portion_control", True, 0, 13),
        AdvicePlan("strength_training", False, 30, 19),
        AdvicePlan("reduce_sugar", False, 0, 10),
    ),
    11: (
        AdvicePlan("brisk_walk", True, 30, 18),
        AdvicePlan("portion_control", True, 0, 13),
        AdvicePlan("posture_break", False, 5, 15),
        AdvicePlan("reduce_sugar", False, 0, 10),
    ),
    12: (
        AdvicePlan("morning_sunlight", True, 15, 8),
        AdvicePlan("hydration", True, 5, 16),
        AdvicePlan("low_impact_mobility", False, 25, 9),
        AdvicePlan("light_walk", False, 20, 11),
    ),
}


# -----------------------------------------------------------------------------
# Manual habits that no device or advice can derive (e.g. swimming, yoga).
# These prove the "Add Habit" manual flow without needing UI clicks.
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ManualHabit:
    user_index: int
    name: str
    probability_score: float
    recurrence: HabitRecurrence = HabitRecurrence.Daily


MANUAL_HABITS: tuple[ManualHabit, ...] = (
    ManualHabit(1, "Custom: Swimming", 0.78),
    ManualHabit(2, "Custom: Yoga", 0.72),
    ManualHabit(7, "Custom: Evening Run", 0.85),
    ManualHabit(11, "Custom: Pilates", 0.70, HabitRecurrence.Weekly),
    ManualHabit(12, "Custom: Morning Tea", 0.90),
)


# -----------------------------------------------------------------------------
# Reset + helpers
# -----------------------------------------------------------------------------


def _demo_emails() -> list[str]:
    return [u.email for u in USERS]


def reset_demo(session: Session) -> None:
    emails = _demo_emails()
    user_ids = session.exec(select(User.id).where(User.email.in_(emails))).all()
    if not user_ids:
        logger.info("reset: no demo users found, nothing to delete.")
        return

    env_ids = session.exec(
        select(UserEnvironment.environment_id).where(
            UserEnvironment.user_id.in_(user_ids)
        )
    ).all()
    env_ids = list(set(env_ids))

    logger.info(
        "reset: deleting %s users, %s environments and dependent rows",
        len(user_ids),
        len(env_ids),
    )

    def _safe_delete(table: str, where: str, **bindparams) -> None:
        try:
            session.exec(text(f"DELETE FROM {table} WHERE {where}").bindparams(**bindparams))
        except Exception as exc:
            session.rollback()
            logger.warning("reset: skipping %s — %s", table, exc)

    # Clean user-scoped tables first — habits.device_id FK forces this order
    # (habits must go before devices).
    _safe_delete("habits", "user_id = ANY(:ids)", ids=list(user_ids))
    _safe_delete("behavior_logs", "user_id = ANY(:ids)", ids=list(user_ids))
    _safe_delete("user_streaks", "user_id = ANY(:ids)", ids=list(user_ids))
    _safe_delete("user_daily_streaks", "user_id = ANY(:ids)", ids=list(user_ids))
    _safe_delete("positive_advice_logs", "user_id = ANY(:ids)", ids=list(user_ids))
    _safe_delete("habit_matrix", "user_id = ANY(:ids)", ids=list(user_ids))
    _safe_delete("recommendations", "user_id = ANY(:ids)", ids=list(user_ids))
    _safe_delete(
        "environment_join_requests", "user_id = ANY(:ids)", ids=list(user_ids)
    )

    # Then drop devices (and any leftover behavior_logs that reference them).
    if env_ids:
        device_ids = session.exec(
            select(Device.id).where(Device.environment_id.in_(env_ids))
        ).all()
        if device_ids:
            session.exec(
                text("DELETE FROM behavior_logs WHERE device_id = ANY(:ids)").bindparams(
                    ids=list(device_ids)
                )
            )
        session.exec(
            text("DELETE FROM devices WHERE environment_id = ANY(:ids)").bindparams(
                ids=env_ids
            )
        )
    if env_ids:
        session.exec(
            text(
                "DELETE FROM environment_join_requests WHERE environment_id = ANY(:ids)"
            ).bindparams(ids=env_ids)
        )
    session.exec(
        text("DELETE FROM user_environments WHERE user_id = ANY(:ids)").bindparams(
            ids=list(user_ids)
        )
    )
    if env_ids:
        session.exec(
            text("DELETE FROM environments WHERE id = ANY(:ids)").bindparams(
                ids=env_ids
            )
        )
    session.exec(
        text("DELETE FROM users WHERE id = ANY(:ids)").bindparams(ids=list(user_ids))
    )
    session.commit()
    logger.info("reset: done.")


def upsert_users(session: Session) -> dict[int, User]:
    by_index: dict[int, User] = {}
    for seed in USERS:
        existing = session.exec(select(User).where(User.email == seed.email)).first()
        if existing is not None:
            by_index[seed.index] = existing
            logger.info("user exists: %s (%s)", existing.id, seed.email)
            continue
        # NOTE: not passing `gender` on purpose — that triggers the legacy
        # peer_group cold-start provisioning which requires a `recommendations`
        # table some demo DBs do not have. Our BMI×age catalog runs anyway.
        payload = UserCreate(
            full_name=seed.full_name,
            email=seed.email,
            password=seed.password,
            height=seed.height,
            weight=seed.weight,
            age=seed.age,
            location=seed.city,
        )
        user = smart_home_service.create_user(payload, session)
        by_index[seed.index] = user
        logger.info("user created: %s (%s, %s)", user.id, user.email, seed.city)
    return by_index


def upsert_environments(
    session: Session, users_by_index: dict[int, User]
) -> dict[str, Environment]:
    envs_by_key: dict[str, Environment] = {}
    for env_seed in ENVIRONMENTS:
        admin = users_by_index[env_seed.admin_index]
        existing = session.exec(
            select(Environment).where(
                Environment.name == env_seed.name,
                Environment.admin_id == admin.id,
            )
        ).first()
        if existing is None:
            payload = EnvironmentCreate(
                name=env_seed.name,
                admin_id=admin.id,
                location=env_seed.location,
                icon_key=env_seed.icon_key,
            )
            env = smart_home_service.create_environment(payload, session)
            logger.info("env created: %s (%s)", env.id, env.name)
        else:
            env = existing
            logger.info("env exists: %s (%s)", env.id, env.name)
        envs_by_key[env_seed.key] = env

        # Ensure memberships.
        for idx in env_seed.member_indices:
            member = users_by_index[idx]
            present = session.exec(
                select(UserEnvironment).where(
                    UserEnvironment.user_id == member.id,
                    UserEnvironment.environment_id == env.id,
                )
            ).first()
            if present is None:
                session.add(
                    UserEnvironment(user_id=member.id, environment_id=env.id)
                )
        session.commit()
    return envs_by_key


def upsert_devices(
    session: Session, envs_by_key: dict[str, Environment]
) -> dict[tuple[str, str], Device]:
    devices: dict[tuple[str, str], Device] = {}
    for env_seed in ENVIRONMENTS:
        env = envs_by_key[env_seed.key]
        for d in env_seed.devices:
            existing = session.exec(
                select(Device).where(
                    Device.environment_id == env.id,
                    Device.name == d.name,
                )
            ).first()
            if existing is not None:
                devices[(env_seed.key, d.name)] = existing
                continue
            payload = DeviceCreate(
                environment_id=env.id,
                type=d.type,
                name=d.name,
                room=d.room,
                status=False,
            )
            device = smart_home_service.create_device(payload, session)
            devices[(env_seed.key, d.name)] = device
            logger.info(
                "device created: %s in %s (id=%s)", d.name, env.name, device.id
            )
    return devices


def _slot_should_run(slot: UsageSlot, day_offset: int, day_dt: datetime, rng: random.Random) -> bool:
    weekday = day_dt.weekday()  # Mon=0 .. Sun=6
    if slot.weekdays_only and weekday >= 5:
        return False
    if slot.weekends_only and weekday < 5:
        return False
    if rng.random() < slot.skip_chance:
        return False
    return True


def _event_datetime(day_dt: datetime, hour: int, minute: int, *, next_day: bool) -> datetime:
    base = day_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_day:
        base = base + timedelta(days=1)
    return base.astimezone(UTC)


def generate_behavior_logs(
    session: Session,
    users_by_index: dict[int, User],
    devices: dict[tuple[str, str], Device],
    *,
    days: int,
    seed: int = 42,
) -> int:
    rng = random.Random(seed)
    now = datetime.now(UTC)
    today = now.date()
    total = 0
    for idx, slots in USER_USAGE.items():
        user = users_by_index[idx]
        for offset in range(days):
            day = today - timedelta(days=days - 1 - offset)
            day_dt = datetime.combine(day, time(0, 0), tzinfo=UTC)
            for slot in slots:
                if not _slot_should_run(slot, offset, day_dt, rng):
                    continue
                device = devices.get((slot.env_key, slot.device_name))
                if device is None or device.id is None:
                    continue
                # On
                on_time = _event_datetime(day_dt, slot.on_hour, slot.on_minute, next_day=False)
                # Off (next day if hour rolls past midnight)
                rolls = slot.off_hour < slot.on_hour or (
                    slot.off_hour == slot.on_hour and slot.off_minute <= slot.on_minute
                )
                off_time = _event_datetime(
                    day_dt, slot.off_hour, slot.off_minute, next_day=rolls
                )
                if off_time <= on_time:
                    continue
                smart_home_service.create_behavior_log(
                    BehaviorLogCreate(
                        user_id=user.id,
                        device_id=device.id,
                        action="TurnOn",
                        event_time=on_time,
                    ),
                    session,
                )
                smart_home_service.create_behavior_log(
                    BehaviorLogCreate(
                        user_id=user.id,
                        device_id=device.id,
                        action="TurnOff",
                        event_time=off_time,
                    ),
                    session,
                )
                total += 2
    return total


def rebuild_habits(session: Session) -> None:
    try:
        result = smart_home_service.rebuild_habit_matrix(session)
        logger.info(
            "habit matrix rebuild: users=%s rules=%s device_habits=%s routines=%s",
            result.get("users_processed"),
            result.get("rules_upserted"),
            result.get("device_habits_upserted"),
            result.get("routine_habits_upserted"),
        )
    except Exception:
        logger.exception("habit matrix rebuild failed (continuing anyway)")


def generate_advice_logs(
    session: Session,
    users_by_index: dict[int, User],
    *,
    days: int,
    seed: int = 42,
) -> int:
    """Insert 1 month of positive-advice completions per user.

    Streak engine: a day qualifies when ≥2 DISTINCT advices are completed.
    This routine deterministically writes core advices so each user lands at
    exactly the ``USER_STREAK_TARGET`` value for current_streak:

    - Last ``target`` days → consecutive qualifying (2 core advices logged)
    - The day right before the window → core advice skipped → streak snaps
    - Older days → random (~70% qualify) → max_streak ends up a bit higher
    - Extra advices fire each day with ``plan.extra_chance`` (≈18%) →
      ~5–6 logs over 30 days, well below the 10-log habit threshold
    """
    positive_advice_service.seed_advice_catalog(session)

    rng = random.Random(seed * 2 + 1)
    now = datetime.now(UTC)
    today = now.date()
    total = 0

    for idx, plans in ADVICE_USAGE.items():
        user = users_by_index[idx]
        target = max(0, min(days, USER_STREAK_TARGET.get(idx, 0)))

        for offset in range(days):
            # offset 0 = oldest day, offset (days-1) = today
            day = today - timedelta(days=days - 1 - offset)
            days_from_today = days - 1 - offset  # 0=today, days-1=oldest

            if days_from_today < target:
                qualify = True  # inside the streak window → always qualify
            elif days_from_today == target:
                qualify = False  # breaker → streak snaps here
            else:
                qualify = rng.random() < 0.70  # organic distribution

            for plan in plans:
                if plan.advice_key not in ADVICE_CATALOG:
                    continue
                if plan.is_core:
                    if not qualify:
                        continue
                else:
                    # extra advice: drops in sporadically without affecting streak
                    if rng.random() > plan.extra_chance:
                        continue

                hour = max(0, min(23, plan.preferred_hour))
                minute = rng.randint(0, 59)
                completed_at = datetime.combine(
                    day, time(hour, minute), tzinfo=UTC
                )
                positive_advice_service.log_advice_completion(
                    user_id=user.id,
                    advice_key=plan.advice_key,
                    duration_minutes=plan.duration_minutes,
                    completed_at=completed_at,
                    session=session,
                )
                total += 1
    return total


def upsert_manual_habits(
    session: Session, users_by_index: dict[int, User]
) -> int:
    """Insert the curated set of manual habits (Swimming, Yoga, etc.)."""
    created = 0
    for mh in MANUAL_HABITS:
        user = users_by_index.get(mh.user_index)
        if user is None:
            continue
        existing = session.exec(
            select(Habit).where(
                Habit.user_id == user.id, Habit.name == mh.name
            )
        ).first()
        if existing is not None:
            continue
        habit = Habit(
            user_id=user.id,
            name=mh.name,
            probability_score=Decimal(str(round(mh.probability_score, 2))),
            is_active=True,
            recurrence_type=mh.recurrence,
            device_id=None,
        )
        session.add(habit)
        created += 1
    if created:
        session.commit()
        logger.info("manual habits added: %s", created)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Synapse demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete previous demo users / environments before seeding.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of past days of behavior logs to generate (default: 30).",
    )
    parser.add_argument(
        "--no-logs",
        action="store_true",
        help="Skip behavior log generation (creates users/envs/devices only).",
    )
    parser.add_argument(
        "--no-habits",
        action="store_true",
        help="Skip habit-matrix rebuild after seeding.",
    )
    args = parser.parse_args()

    with Session(engine) as session:
        if args.reset:
            reset_demo(session)

        users = upsert_users(session)
        envs = upsert_environments(session, users)
        devices = upsert_devices(session, envs)

        if not args.no_logs:
            total = generate_behavior_logs(
                session, users, devices, days=args.days
            )
            logger.info("generated %s behavior log entries", total)
            advice_total = generate_advice_logs(
                session, users, days=args.days
            )
            logger.info("generated %s positive-advice log entries", advice_total)
        else:
            logger.info("--no-logs set: skipped behavior + advice log generation")

        manual_added = upsert_manual_habits(session, users)
        if manual_added == 0:
            logger.info("manual habits: nothing to add (already present).")

        if not args.no_habits:
            rebuild_habits(session)

    logger.info("seed completed.")
    print("\nSeed summary")
    print(f"  Users      : {len(USERS)} (test1..test{len(USERS)})")
    print(f"  Environments: {len(ENVIRONMENTS)}")
    print(f"  Login example: test1{DEMO_EMAIL_DOMAIN} / 1")


if __name__ == "__main__":
    main()

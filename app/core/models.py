"""
Rapor Bölüm 4.1.2 (Logical View) ve PostgreSQL `public` şeması ile uyumlu SQLModel modelleri.

Python'da alan adları veritabanı sütunlarıyla aynı olacak şekilde snake_case kullanılır.
Rapordaki camelCase eşlemesi her sınıfın docstring'inde verilmiştir.

Kimlik kısıtları (uygulama doğrulaması):
- User.id: P ile başlayan 8 karakter (CHECK + regex).
- Environment.id: H ile başlayan 8 karakter (CHECK + regex).

ENUM ve trigger'lar PostgreSQL tarafında; `create_type=False`.

`BehaviorLog.parameters` kolonu: `migrations/001_add_behavior_logs_parameters.sql` ile eklenir.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum

from pydantic import field_validator
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Interval,
    Numeric,
    Text,
    UniqueConstraint,
    false,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, JSONB
from sqlmodel import Field, SQLModel

# --- PostgreSQL ENUM karşılıkları ---


class DeviceType(str, Enum):
    """Cihaz tipi (Lamba, Termostat, …). Rapor: Device.type."""

    Lamp = "Lamp"
    Thermostat = "Thermostat"
    Plug = "Plug"
    Sensor = "Sensor"
    Other = "Other"


class HabitRecurrence(str, Enum):
    Daily = "Daily"
    Weekly = "Weekly"
    Monthly = "Monthly"


class AdviceCategory(str, Enum):
    Reading = "Reading"
    Water = "Water"
    Exercise = "Exercise"
    Sleep = "Sleep"
    Mindfulness = "Mindfulness"
    Other = "Other"


class RecommendationStatus(str, Enum):
    Pending = "PENDING"
    Accepted = "ACCEPTED"
    Rejected = "REJECTED"
    Expired = "EXPIRED"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [e.value for e in enum_cls]


_pg_device_type = PG_ENUM(
    DeviceType,
    name="device_type",
    create_type=False,
    values_callable=_enum_values,
)
_pg_habit_recurrence = PG_ENUM(
    HabitRecurrence,
    name="habit_recurrence",
    create_type=False,
    values_callable=_enum_values,
)
_pg_advice_category = PG_ENUM(
    AdviceCategory,
    name="advice_category",
    create_type=False,
    values_callable=_enum_values,
)
_pg_recommendation_status = PG_ENUM(
    RecommendationStatus,
    name="recommendation_status",
    create_type=False,
    values_callable=_enum_values,
)


def _check_ph_char8(value: str | None, prefix: str, label: str) -> str | None:
    if value is None:
        return value
    v = value.strip()
    if len(v) != 8 or not v.startswith(prefix):
        raise ValueError(f"{label} tam 8 karakter ve '{prefix}' ile başlamalı")
    return v


# --- Tablolar ---


class User(SQLModel, table=True):
    """
    Rapor eşlemesi: userID→id, fullName→full_name, environmentID (rapor) ayrıca `user_environments` ile.

    Alanlar: id (P…), full_name, email, height, weight, age, location; ayrıca kimlik doğrulama için password_hash (DB).
    """

    __tablename__ = "users"

    id: str | None = Field(
        default=None,
        primary_key=True,
        max_length=8,
        description="userID — P ile başlayan 8 karakter; INSERT’te NULL bırakılırsa DB tetikleyicisi üretebilir.",
    )
    full_name: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="fullName",
    )
    email: str | None = Field(
        default=None,
        sa_column=Column(Text, unique=True),
        description="E-posta (benzersiz).",
    )
    password_hash: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Parola özeti (rapor diyagramında yok; güvenlik için DB’de).",
    )
    height: int | None = Field(default=None, description="Boy (cold-start / öneri).")
    weight: int | None = Field(default=None, description="Kilo (cold-start / öneri).")
    age: int | None = Field(default=None, description="Yaş (cold-start / öneri).")
    location: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Konum / iklim bağlamı.",
    )
    avatar_key: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Preset profile avatar key.",
    )
    gender: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Cinsiyet (Erkek/Kadın) — cold-start ve öneri kohortu için.",
    )

    @field_validator("id")
    @classmethod
    def user_id_db_check(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        _check_ph_char8(v, "P", "User id")
        if not re.fullmatch(r"P[A-Z0-9]{7}", v):
            raise ValueError("User id: P + 7 büyük harf veya rakam olmalı")
        return v


class Environment(SQLModel, table=True):
    """
    Rapor eşlemesi: environmentID→id, address/creationDate raporda; DB’de name, admin_id, location.
    """

    __tablename__ = "environments"

    id: str | None = Field(
        default=None,
        primary_key=True,
        max_length=8,
        description="environmentID — H ile başlayan 8 karakter.",
    )
    name: str | None = Field(default=None, sa_column=Column(Text), description="Ortam / ev adı.")
    admin_id: str | None = Field(
        default=None,
        foreign_key="users.id",
        max_length=8,
        description="Ev yöneticisi kullanıcı (User.id).",
    )
    location: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Konum metni (DB şemasında).",
    )
    icon_key: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Environment icon key.",
    )

    @field_validator("id")
    @classmethod
    def environment_id_db_check(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        _check_ph_char8(v, "H", "Environment id")
        if not re.fullmatch(r"H[A-Z0-9]{7}", v):
            raise ValueError("Environment id: H + 7 büyük harf veya rakam olmalı")
        return v


class Device(SQLModel, table=True):
    """
    Rapor eşlemesi: deviceID→id, environmentID→environment_id, type, status (On/Off).

    Ek: name (kullanıcı dostu isim), current_value (parlaklık / sıcaklık vb.).
    RaporlastModificationDate: şu an PostgreSQL şemasında yok; ileride eklenebilir.
    """

    __tablename__ = "devices"

    id: int | None = Field(default=None, primary_key=True, description="deviceID (SERIAL).")
    environment_id: str = Field(
        max_length=8,
        foreign_key="environments.id",
        description="Bağlı olduğu environmentID.",
    )
    type: DeviceType = Field(
        sa_column=Column(_pg_device_type, nullable=False),
        description="Lamba, Termostat, Fiş vb. (device_type ENUM).",
    )
    status: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=false()),
        description="Açık/kapalı (On/Off).",
    )
    current_value: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric),
        description="Parlaklık, sıcaklık gibi sayısal değer.",
    )
    name: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Örn. Salon Lambası.",
    )
    room: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Room or zone label.",
    )


class BehaviorLog(SQLModel, table=True):
    """
    Rapor eşlemesi: logID→id, userID→user_id, deviceID→device_id, action, timestamp→event_time, parameters.

    `parameters` kolonu için: `migrations/001_add_behavior_logs_parameters.sql` çalıştırılmalı.
    """

    __tablename__ = "behavior_logs"

    id: int | None = Field(default=None, primary_key=True, description="logID.")
    user_id: str = Field(max_length=8, foreign_key="users.id", description="userID.")
    device_id: int = Field(foreign_key="devices.id", description="deviceID.")
    action: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Örn. TurnOn, parlaklık komutu veya serbest metin.",
    )
    event_time: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="timestamp (dakikaya yuvarlama DB tetikleyicisi ile).",
    )
    duration_hm: timedelta | None = Field(
        default=None,
        sa_column=Column(Interval),
        description="Süre (saat+dakika); rapor 3.4.1 ile uyumlu INTERVAL.",
    )
    parameters: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Rapor: ek bağlam (örn. Parlaklık: %70).",
    )


class Habit(SQLModel, table=True):
    """
    Rapor eşlemesi: habitID→id, userID→user_id, habitType→name (örn. Drink Water, Reading).

    Ek (DB): probability_score, is_active (histerezis tetikleyicisi), recurrence_type, device_id.
    """

    __tablename__ = "habits"

    id: int | None = Field(default=None, primary_key=True, description="habitID.")
    user_id: str = Field(max_length=8, foreign_key="users.id", description="userID.")
    name: str = Field(
        sa_column=Column(Text, nullable=False),
        description="habitType / alışkanlık adı (örn. su içme, kitap okuma).",
    )
    probability_score: Decimal = Field(
        sa_column=Column(Numeric(4, 2), nullable=False),
        description="0.00–1.00 olasılık; giriş >0.60 / çıkış <0.45 histerezis.",
    )
    is_active: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=false()),
        description="Alışkanlık şu an aktif mi (tetikleyici günceller).",
    )
    recurrence_type: HabitRecurrence = Field(
        sa_column=Column(_pg_habit_recurrence, nullable=False),
        description="Günlük / Haftalık / Aylık tekrar.",
    )
    device_id: int | None = Field(
        default=None,
        foreign_key="devices.id",
        description="İlgili cihaz (opsiyonel).",
    )


class PositiveAdvice(SQLModel, table=True):
    __tablename__ = "positive_advices"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text))
    category: AdviceCategory = Field(
        default=AdviceCategory.Other,
        sa_column=Column(_pg_advice_category, nullable=False),
    )


class UserEnvironment(SQLModel, table=True):
    """Kullanıcı–ev üyeliği (çoktan çoğa)."""

    __tablename__ = "user_environments"

    user_id: str = Field(max_length=8, foreign_key="users.id", primary_key=True)
    environment_id: str = Field(
        max_length=8, foreign_key="environments.id", primary_key=True
    )


class EnvironmentJoinRequest(SQLModel, table=True):
    """Onay bekleyen environment katılma isteği."""

    __tablename__ = "environment_join_requests"
    __table_args__ = (
        UniqueConstraint("environment_id", "user_id", name="uq_env_join_user"),
    )

    id: int | None = Field(default=None, primary_key=True)
    environment_id: str = Field(max_length=8, foreign_key="environments.id")
    user_id: str = Field(max_length=8, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class UserStreak(SQLModel, table=True):
    __tablename__ = "user_streaks"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(max_length=8, foreign_key="users.id")
    advice_id: int = Field(foreign_key="positive_advices.id")
    current_streak: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    max_streak: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    last_completed_on: date | None = Field(
        default=None,
        sa_column=Column(Date),
    )


class PositiveAdviceLog(SQLModel, table=True):
    """Bir kullanıcının pozitif tavsiyeyi tamamladığı kayıt.

    `advice_key` kataloğumuzdaki anahtardır (ör. ``strength_training``),
    `advice_title` görünüm için denormalize edilmiş başlıktır.
    """

    __tablename__ = "positive_advice_logs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(max_length=8, foreign_key="users.id")
    advice_key: str = Field(sa_column=Column(Text, nullable=False))
    advice_title: str = Field(sa_column=Column(Text, nullable=False))
    category: AdviceCategory = Field(
        default=AdviceCategory.Other,
        sa_column=Column(_pg_advice_category, nullable=False),
    )
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    duration_minutes: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )


class UserDailyStreak(SQLModel, table=True):
    """Kullanıcı başına günlük "qualifying day" streak'i.

    Bir gün ≥2 farklı pozitif tavsiye tamamlandığında "qualifying" sayılır.
    Ardışık qualifying günler ``current_streak``'i artırır.
    """

    __tablename__ = "user_daily_streaks"

    user_id: str = Field(max_length=8, primary_key=True, foreign_key="users.id")
    current_streak: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    max_streak: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    last_qualifying_date: date | None = Field(default=None, sa_column=Column(Date))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Recommendation(SQLModel, table=True):
    __tablename__ = "recommendations"

    id: str = Field(primary_key=True, max_length=11, description="REC-0000001 benzeri kimlik.")
    user_id: str = Field(max_length=8, foreign_key="users.id")
    trigger_device: str = Field(sa_column=Column(Text, nullable=False))
    target_device: str = Field(sa_column=Column(Text, nullable=False))
    action: str = Field(sa_column=Column(Text, nullable=False))
    confidence: Decimal = Field(sa_column=Column(Numeric(5, 4), nullable=False))
    recommendation_type: str = Field(
        default="SUGGESTION",
        sa_column=Column(Text, nullable=False, server_default="SUGGESTION"),
    )
    context: str = Field(
        default="Pending",
        sa_column=Column(Text, nullable=False, server_default="Pending"),
    )
    status: RecommendationStatus = Field(
        default=RecommendationStatus.Pending,
        sa_column=Column(
            _pg_recommendation_status,
            nullable=False,
            server_default=RecommendationStatus.Pending.value,
        ),
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


# -----------------------------------------------------------------------
# Notifications & advice schedules
# -----------------------------------------------------------------------


class NotificationKind(str, Enum):
    """Identifier for the kind of notification — extensible TEXT column."""

    MorningGreeting = "morning_greeting"
    AdviceReminder = "advice_reminder"
    DeviceRoutine = "device_routine"
    SequenceTrigger = "sequence_trigger"
    StreakMilestone = "streak_milestone"
    StreakRisk = "streak_risk"
    SafetyAnomaly = "safety_anomaly"
    EnvironmentInvite = "environment_invite"


class NotificationStatus(str, Enum):
    Pending = "pending"
    Fired = "fired"
    Confirmed = "confirmed"
    Dismissed = "dismissed"
    Expired = "expired"


class Notification(SQLModel, table=True):
    """In-app notification feed entry.

    Notifications are *persistent* — they live in this table until the user
    confirms / dismisses them, or until end-of-day expiry. ``status`` walks
    the lifecycle: ``pending`` → ``fired`` (visible) → ``confirmed`` /
    ``dismissed`` / ``expired``.

    ``payload`` carries kind-specific extras (advice_key, device_id,
    schedule_id, etc.) as JSONB so we can extend kinds without migrations.
    """

    __tablename__ = "notifications"

    id: int | None = Field(
        default=None,
        # BIGINT does not autoincrement on SQLite (only INTEGER PK does),
        # so fall back to INTEGER there for the test engine.
        sa_column=Column(
            BigInteger().with_variant(Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
    )
    user_id: str = Field(max_length=8, foreign_key="users.id")
    kind: str = Field(sa_column=Column(Text, nullable=False))
    title: str = Field(sa_column=Column(Text, nullable=False))
    body: str = Field(sa_column=Column(Text, nullable=False))
    scheduled_for: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    fired_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )
    status: str = Field(
        default=NotificationStatus.Pending.value,
        sa_column=Column(Text, nullable=False, server_default="pending"),
    )
    requires_action: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=false()),
    )
    payload: dict = Field(
        default_factory=dict,
        # JSONB on PostgreSQL, plain JSON on SQLite so the in-memory test
        # engine (which cannot compile JSONB) can still create the table.
        sa_column=Column(
            JSONB().with_variant(JSON(), "sqlite"),
            nullable=False,
            server_default=sql_text("'{}'"),
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AdviceSchedule(SQLModel, table=True):
    """User-planned positive-advice session.

    Created when the user picks a start time + duration from the dashboard.
    The accompanying `advice_reminder` Notification row holds the bell-feed
    entry; on confirm we look up this schedule by `notification_id` and
    log the actual positive_advice completion.
    """

    __tablename__ = "advice_schedules"

    id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger().with_variant(Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
    )
    user_id: str = Field(max_length=8, foreign_key="users.id")
    advice_key: str = Field(sa_column=Column(Text, nullable=False))
    advice_title: str = Field(sa_column=Column(Text, nullable=False))
    scheduled_for: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    duration_minutes: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    status: str = Field(
        default="pending",
        sa_column=Column(Text, nullable=False, server_default="pending"),
    )
    notification_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("notifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

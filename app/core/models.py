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
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import field_validator
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Interval, Numeric, Text, false
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
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


def _check_ph_char8(value: Optional[str], prefix: str, label: str) -> Optional[str]:
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

    id: Optional[str] = Field(
        default=None,
        primary_key=True,
        max_length=8,
        description="userID — P ile başlayan 8 karakter; INSERT’te NULL bırakılırsa DB tetikleyicisi üretebilir.",
    )
    full_name: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="fullName",
    )
    email: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, unique=True),
        description="E-posta (benzersiz).",
    )
    password_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Parola özeti (rapor diyagramında yok; güvenlik için DB’de).",
    )
    height: Optional[int] = Field(default=None, description="Boy (cold-start / öneri).")
    weight: Optional[int] = Field(default=None, description="Kilo (cold-start / öneri).")
    age: Optional[int] = Field(default=None, description="Yaş (cold-start / öneri).")
    location: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Konum / iklim bağlamı.",
    )

    @field_validator("id")
    @classmethod
    def user_id_db_check(cls, v: Optional[str]) -> Optional[str]:
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

    id: Optional[str] = Field(
        default=None,
        primary_key=True,
        max_length=8,
        description="environmentID — H ile başlayan 8 karakter.",
    )
    name: Optional[str] = Field(default=None, sa_column=Column(Text), description="Ortam / ev adı.")
    admin_id: Optional[str] = Field(
        default=None,
        foreign_key="users.id",
        max_length=8,
        description="Ev yöneticisi kullanıcı (User.id).",
    )
    location: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Konum metni (DB şemasında).",
    )

    @field_validator("id")
    @classmethod
    def environment_id_db_check(cls, v: Optional[str]) -> Optional[str]:
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

    id: Optional[int] = Field(default=None, primary_key=True, description="deviceID (SERIAL).")
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
    current_value: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric),
        description="Parlaklık, sıcaklık gibi sayısal değer.",
    )
    name: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Örn. Salon Lambası.",
    )


class BehaviorLog(SQLModel, table=True):
    """
    Rapor eşlemesi: logID→id, userID→user_id, deviceID→device_id, action, timestamp→event_time, parameters.

    `parameters` kolonu için: `migrations/001_add_behavior_logs_parameters.sql` çalıştırılmalı.
    """

    __tablename__ = "behavior_logs"

    id: Optional[int] = Field(default=None, primary_key=True, description="logID.")
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
    duration_hm: Optional[timedelta] = Field(
        default=None,
        sa_column=Column(Interval),
        description="Süre (saat+dakika); rapor 3.4.1 ile uyumlu INTERVAL.",
    )
    parameters: Optional[str] = Field(
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

    id: Optional[int] = Field(default=None, primary_key=True, description="habitID.")
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
    device_id: Optional[int] = Field(
        default=None,
        foreign_key="devices.id",
        description="İlgili cihaz (opsiyonel).",
    )


class PositiveAdvice(SQLModel, table=True):
    __tablename__ = "positive_advices"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(sa_column=Column(Text, nullable=False))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
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


class UserStreak(SQLModel, table=True):
    __tablename__ = "user_streaks"

    id: Optional[int] = Field(default=None, primary_key=True)
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
    last_completed_on: Optional[date] = Field(
        default=None,
        sa_column=Column(Date),
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

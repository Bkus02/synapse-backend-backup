from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import SQLModel

from app.core.models import DeviceType, HabitRecurrence


class UserCreate(SQLModel):
    id: str | None = None
    full_name: str | None = None
    email: str | None = None
    # Düz parola: geriye uyum için `password_hash` ile de gönderilebilir
    # (Sprint B öncesi frontend bu adı kullanıyordu). Servis katmanı
    # alınan değeri bcrypt ile hashleyip `User.password_hash`'a yazar.
    password: str | None = None
    password_hash: str | None = None
    height: int | None = None
    weight: int | None = None
    age: int | None = None
    location: str | None = None
    gender: str | None = None


class LoginRequest(SQLModel):
    email: str
    password: str


class UserPublic(SQLModel):
    """Auth/me ve login response icinde kullanilan, password_hash icermeyen view."""

    id: str | None = None
    full_name: str | None = None
    email: str | None = None
    height: int | None = None
    weight: int | None = None
    age: int | None = None
    location: str | None = None
    avatar_key: str | None = None


class LoginResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # saniye
    user: UserPublic


class UserUpdate(SQLModel):
    full_name: str | None = None
    email: str | None = None
    password: str | None = None        # yeni: düz parola
    password_hash: str | None = None   # geri uyum
    height: int | None = None
    weight: int | None = None
    age: int | None = None
    location: str | None = None
    avatar_key: str | None = None


class EnvironmentCreate(SQLModel):
    id: str | None = None
    name: str | None = None
    admin_id: str | None = None
    location: str | None = None
    icon_key: str | None = None


class AddUserToEnvironmentRequest(SQLModel):
    user_id: str


class JoinEnvironmentRequest(SQLModel):
    user_id: str


class AdminUserBody(SQLModel):
    admin_user_id: str


class SuggestedEnvironmentId(SQLModel):
    id: str


class EnvironmentMemberOut(SQLModel):
    user_id: str
    full_name: str | None = None
    avatar_key: str | None = None


class JoinRequestOut(SQLModel):
    id: int
    environment_id: str
    user_id: str
    requester_name: str | None = None
    requester_avatar_key: str | None = None
    created_at: datetime | None = None


class DeviceCreate(SQLModel):
    environment_id: str
    type: DeviceType
    status: bool = False
    current_value: Decimal | None = None
    name: str | None = None
    room: str | None = None


class DeviceUpdate(SQLModel):
    """Partial update; sadece gönderilen alanlar değişir."""

    status: bool | None = None
    current_value: Decimal | None = None
    name: str | None = None
    room: str | None = None


class BehaviorLogCreate(SQLModel):
    user_id: str
    device_id: int
    action: str
    event_time: datetime
    duration_hm: timedelta | None = None
    parameters: str | None = None


class HabitCreate(SQLModel):
    user_id: str
    name: str
    probability_score: Decimal
    is_active: bool = False
    recurrence_type: HabitRecurrence
    device_id: int | None = None


class HabitUpdate(SQLModel):
    name: str | None = None
    is_active: bool | None = None
    recurrence_type: HabitRecurrence | None = None
    probability_score: Decimal | None = None
    device_id: int | None = None


class HabitSequenceResponse(SQLModel):
    trigger: str
    target: str
    confidence: float
    context: str


class RecommendationResponse(SQLModel):
    id: str
    user_id: str
    type: str
    trigger: str
    target: str
    context: str
    final_confidence: float
    status: str
    created_at: datetime | None = None


class RecommendationStatusUpdateResponse(SQLModel):
    id: str
    status: str


class DailyActivityDay(SQLModel):
    date: str  # ISO YYYY-MM-DD
    active: bool


class DailyActivityResponse(SQLModel):
    user_id: str
    days: list[DailyActivityDay]
    weekly_streak_count: int

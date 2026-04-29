from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import SQLModel

from app.core.models import DeviceType, HabitRecurrence


class UserCreate(SQLModel):
    id: str | None = None
    full_name: str | None = None
    email: str | None = None
    password_hash: str | None = None
    height: int | None = None
    weight: int | None = None
    age: int | None = None
    location: str | None = None


class EnvironmentCreate(SQLModel):
    id: str | None = None
    name: str | None = None
    admin_id: str | None = None
    location: str | None = None


class AddUserToEnvironmentRequest(SQLModel):
    user_id: str


class DeviceCreate(SQLModel):
    environment_id: str
    type: DeviceType
    status: bool = False
    current_value: Decimal | None = None
    name: str | None = None


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

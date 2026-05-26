from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.models import Device, DeviceType, User
from app.infrastructure.events.in_memory_publisher import InMemoryEventPublisher


@pytest.fixture
def sqlite_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def event_publisher() -> InMemoryEventPublisher:
    return InMemoryEventPublisher()


@pytest.fixture
def sample_user(sqlite_session: Session) -> User:
    user = User(
        id="PTEST001",
        full_name="Test User",
        email="test@synapse.local",
        age=22,
        height=180,
        weight=75,
        location="İzmir",
    )
    sqlite_session.add(user)
    sqlite_session.commit()
    sqlite_session.refresh(user)
    return user


@pytest.fixture
def sample_device(sqlite_session: Session, sample_user: User) -> Device:
    env_id = "HTEST001"
    from app.core.models import Environment

    env = Environment(id=env_id, name="Test Home", admin_id=sample_user.id)
    sqlite_session.add(env)
    dev = Device(
        id=1,
        environment_id=env_id,
        type=DeviceType.Lamp,
        status=False,
        name="Salon Lambasi",
    )
    sqlite_session.add(dev)
    sqlite_session.commit()
    sqlite_session.refresh(dev)
    return dev

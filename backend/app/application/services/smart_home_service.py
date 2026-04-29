import re
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.api.schemas import (
    BehaviorLogCreate,
    DeviceCreate,
    EnvironmentCreate,
    HabitCreate,
    HabitUpdate,
    LoginRequest,
    UserCreate,
    UserUpdate,
)
from app.core.models import (
    BehaviorLog,
    Device,
    Environment,
    EnvironmentJoinRequest,
    Habit,
    User,
    UserEnvironment,
)


def _commit_or_400(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=message) from exc


def _next_prefixed_id(session: Session, model_cls: type[SQLModel], prefix: str) -> str:
    existing_ids = session.exec(select(model_cls.id)).all()  # type: ignore[attr-defined]
    max_num = 0
    pattern = re.compile(rf"^{prefix}(\d{{7}})$")
    for raw in existing_ids:
        if isinstance(raw, str):
            m = pattern.match(raw)
            if m:
                max_num = max(max_num, int(m.group(1)))
    return f"{prefix}{max_num + 1:07d}"


def round_to_nearest_minute(ts: datetime) -> datetime:
    rounded = ts.replace(second=0, microsecond=0)
    if ts.second >= 30:
        rounded = rounded + timedelta(minutes=1)
    return rounded


def _duration_as_interval(start_time: datetime, end_time: datetime) -> timedelta:
    delta = end_time - start_time
    if delta.total_seconds() < 60:
        return timedelta(minutes=1)
    minutes = int(delta.total_seconds() // 60)
    if delta.total_seconds() % 60 != 0:
        minutes += 1
    return timedelta(minutes=max(1, minutes))


def _is_off_action(action: str) -> bool:
    return "off" in action.lower()


def _is_on_action(action: str) -> bool:
    return "on" in action.lower()


def list_environments(session: Session) -> list[Environment]:
    return list(session.exec(select(Environment)))


def suggest_next_environment_id(session: Session) -> str:
    return _next_prefixed_id(session, Environment, "H")


def list_environments_for_user(user_id: str, session: Session) -> list[Environment]:
    member_subq = select(UserEnvironment.environment_id).where(
        UserEnvironment.user_id == user_id
    )
    stmt = select(Environment).where(
        or_(
            Environment.admin_id == user_id,
            Environment.id.in_(member_subq),
        )
    )
    return list(session.exec(stmt).all())


def create_environment(payload: EnvironmentCreate, session: Session) -> Environment:
    data = payload.model_dump(exclude_unset=True)
    if not data.get("id"):
        data["id"] = _next_prefixed_id(session, Environment, "H")
    env = Environment.model_validate(data)
    session.add(env)
    session.flush()
    if env.admin_id and env.id:
        session.add(
            UserEnvironment(user_id=env.admin_id, environment_id=env.id)
        )
    _commit_or_400(session, "Could not create environment: check ID and admin.")
    session.refresh(env)
    return env


def delete_environment(environment_id: str, session: Session) -> dict[str, str]:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    session.delete(env)
    _commit_or_400(session, "Could not delete environment.")
    return {"message": "Environment silindi."}


def add_user_to_environment(environment_id: str, user_id: str, session: Session) -> UserEnvironment:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    existing = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="User is already a member of this environment."
        )

    membership = UserEnvironment(user_id=user_id, environment_id=environment_id)
    session.add(membership)
    _commit_or_400(session, "Could not add user to environment.")
    session.refresh(membership)
    return membership


def _get_env_or_404(environment_id: str, session: Session) -> Environment:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    return env


def _assert_env_admin(env: Environment, admin_user_id: str) -> None:
    if env.admin_id != admin_user_id:
        raise HTTPException(
            status_code=403, detail="You must be the environment admin for this action."
        )


def create_join_request(environment_id: str, user_id: str, session: Session) -> EnvironmentJoinRequest:
    env = _get_env_or_404(environment_id, session)
    if env.admin_id == user_id:
        raise HTTPException(
            status_code=400,
            detail="You are already this environment's admin; membership is implicit.",
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    existing = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="You are already a member of this environment."
        )
    req = EnvironmentJoinRequest(environment_id=environment_id, user_id=user_id)
    session.add(req)
    _commit_or_400(
        session,
        "Could not create join request (pending request or conflict).",
    )
    session.refresh(req)
    return req


def list_join_requests(
    environment_id: str, admin_user_id: str, session: Session
) -> list[EnvironmentJoinRequest]:
    env = _get_env_or_404(environment_id, session)
    _assert_env_admin(env, admin_user_id)
    return list(
        session.exec(
            select(EnvironmentJoinRequest).where(
                EnvironmentJoinRequest.environment_id == environment_id
            )
        ).all()
    )


def approve_join_request(
    environment_id: str,
    request_id: int,
    admin_user_id: str,
    session: Session,
) -> UserEnvironment:
    env = _get_env_or_404(environment_id, session)
    _assert_env_admin(env, admin_user_id)
    req = session.get(EnvironmentJoinRequest, request_id)
    if req is None or req.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Join request not found.")
    membership = UserEnvironment(
        user_id=req.user_id, environment_id=environment_id
    )
    session.add(membership)
    session.delete(req)
    _commit_or_400(session, "Could not add membership.")
    session.refresh(membership)
    return membership


def reject_join_request(
    environment_id: str,
    request_id: int,
    admin_user_id: str,
    session: Session,
) -> dict[str, str]:
    env = _get_env_or_404(environment_id, session)
    _assert_env_admin(env, admin_user_id)
    req = session.get(EnvironmentJoinRequest, request_id)
    if req is None or req.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Join request not found.")
    session.delete(req)
    _commit_or_400(session, "Could not delete request.")
    return {"message": "Join request rejected."}


def list_environment_members(
    environment_id: str, session: Session
) -> list[dict[str, str | None]]:
    _get_env_or_404(environment_id, session)
    rows = session.exec(
        select(UserEnvironment.user_id).where(
            UserEnvironment.environment_id == environment_id
        )
    ).all()
    out: list[dict[str, str | None]] = []
    for uid in rows:
        u = session.get(User, uid)
        if u is not None:
            out.append(
                {
                    "user_id": u.id,
                    "full_name": u.full_name,
                    "avatar_key": u.avatar_key,
                }
            )
    return out


def _require_environment_access(
    user_id: str, environment_id: str, session: Session
) -> None:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found.")
    if env.admin_id == user_id:
        return
    link = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if link is None:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this environment.",
        )


def list_devices_for_environment(
    environment_id: str, user_id: str, session: Session
) -> list[Device]:
    _require_environment_access(user_id, environment_id, session)
    return list(
        session.exec(select(Device).where(Device.environment_id == environment_id))
    )


def create_device_authenticated(
    payload: DeviceCreate, user_id: str, session: Session
) -> Device:
    _require_environment_access(user_id, payload.environment_id, session)
    device = Device.model_validate(payload.model_dump(exclude_unset=True))
    session.add(device)
    _commit_or_400(session, "Could not create device: check environment and foreign keys.")
    session.refresh(device)
    return device


def delete_device_authenticated(
    device_id: int, user_id: str, session: Session
) -> dict[str, str]:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    _require_environment_access(user_id, device.environment_id, session)
    session.delete(device)
    _commit_or_400(session, "Could not delete device.")
    return {"message": "Device deleted."}


def list_behavior_logs(session: Session) -> list[BehaviorLog]:
    return list(session.exec(select(BehaviorLog)))


def create_behavior_log(payload: BehaviorLogCreate, session: Session) -> BehaviorLog:
    data = payload.model_dump(exclude_unset=True)
    data["event_time"] = round_to_nearest_minute(data["event_time"])

    if _is_off_action(data["action"]) and not data.get("duration_hm"):
        previous_logs = session.exec(
            select(BehaviorLog)
            .where(
                BehaviorLog.user_id == data["user_id"],
                BehaviorLog.device_id == data["device_id"],
            )
            .order_by(BehaviorLog.event_time.desc())
        ).all()

        last_on_log = next((x for x in previous_logs if _is_on_action(x.action)), None)
        if last_on_log is not None:
            start = round_to_nearest_minute(last_on_log.event_time)
            end = data["event_time"]
            if end >= start:
                data["duration_hm"] = _duration_as_interval(start, end)

    log = BehaviorLog.model_validate(data)
    session.add(log)
    _commit_or_400(
        session, "Could not create behavior log: check user, device, and foreign keys."
    )
    session.refresh(log)
    return log


def delete_behavior_log(log_id: int, session: Session) -> dict[str, str]:
    log = session.get(BehaviorLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Behavior log not found.")
    session.delete(log)
    _commit_or_400(session, "Could not delete behavior log.")
    return {"message": "BehaviorLog silindi."}


def list_habits_for_user(user_id: str, session: Session) -> list[Habit]:
    return list(session.exec(select(Habit).where(Habit.user_id == user_id)))


def create_habit(payload: HabitCreate, session: Session) -> Habit:
    habit = Habit.model_validate(payload.model_dump(exclude_unset=True))
    session.add(habit)
    _commit_or_400(
        session, "Could not create habit: check foreign keys and probability value."
    )
    session.refresh(habit)
    return habit


def patch_habit(
    habit_id: int, user_id: str, payload: HabitUpdate, session: Session
) -> Habit:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(status_code=404, detail="Habit not found.")
    if habit.user_id != user_id:
        raise HTTPException(
            status_code=403, detail="You can only update your own habits."
        )
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(habit, key, value)
    session.add(habit)
    _commit_or_400(session, "Could not update habit.")
    session.refresh(habit)
    return habit


def delete_habit_authenticated(
    habit_id: int, user_id: str, session: Session
) -> dict[str, str]:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(status_code=404, detail="Habit not found.")
    if habit.user_id != user_id:
        raise HTTPException(
            status_code=403, detail="You can only delete your own habits."
        )
    session.delete(habit)
    _commit_or_400(session, "Could not delete habit.")
    return {"message": "Habit deleted."}


def list_users(session: Session) -> list[User]:
    return list(session.exec(select(User)))


def login_user(payload: LoginRequest, session: Session) -> User:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or (user.password_hash or "") != payload.password:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )
    return user


def create_user(payload: UserCreate, session: Session) -> User:
    data = payload.model_dump(exclude_unset=True)
    if not data.get("id"):
        data["id"] = _next_prefixed_id(session, User, "P")
    user = User.model_validate(data)
    session.add(user)
    _commit_or_400(
        session,
        "Could not create user: ID or email may already exist.",
    )
    session.refresh(user)
    return user


def update_user(user_id: str, payload: UserUpdate, session: Session) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    session.add(user)
    _commit_or_400(
        session,
        "Update failed: email may already be used by another user.",
    )
    session.refresh(user)
    return user

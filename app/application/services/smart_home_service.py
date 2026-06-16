import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.analytics.decision_engine import process_decision_sync
from app.analytics.sequence_miner import SequenceMinerConfig, mine_habit_sequences
from app.api.schemas import (
    BehaviorLogCreate,
    DeviceCreate,
    DeviceUpdate,
    EnvironmentCreate,
    HabitCreate,
    HabitUpdate,
    LoginRequest,
    UserCreate,
    UserUpdate,
)
from app.application.services.cold_start_provisioning import provision_cold_start_defaults
from app.core.domain.anomaly_detection import evaluate_duration_anomaly
from app.core.domain.events import AnomalyDetected
from app.core.models import (
    BehaviorLog,
    Device,
    Environment,
    EnvironmentJoinRequest,
    Habit,
    HabitRecurrence,
    Notification,
    NotificationKind,
    NotificationStatus,
    PositiveAdviceLog,
    Recommendation,
    RecommendationStatus,
    User,
    UserDailyStreak,
    UserEnvironment,
)
from app.core.ports.event_publisher import EventPublisher
from app.core.security import (
    hash_password,
    looks_like_bcrypt_hash,
    verify_password,
)
from app.core.settings import settings
from app.models.habit_matrix import HabitMatrix

logger = logging.getLogger(__name__)


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
    member_ids = session.exec(
        select(UserEnvironment.environment_id).where(UserEnvironment.user_id == user_id)
    ).all()
    return list(
        session.exec(
            select(Environment).where(
                (Environment.admin_id == user_id) | (Environment.id.in_(member_ids))
            )
        )
    )


def create_environment(payload: EnvironmentCreate, session: Session) -> Environment:
    data = payload.model_dump(exclude_unset=True)
    if not data.get("id"):
        data["id"] = _next_prefixed_id(session, Environment, "H")
    env = Environment.model_validate(data)
    session.add(env)
    session.flush()
    if env.admin_id and env.id:
        existing = session.exec(
            select(UserEnvironment).where(
                UserEnvironment.user_id == env.admin_id,
                UserEnvironment.environment_id == env.id,
            )
        ).first()
        if existing is None:
            session.add(UserEnvironment(user_id=env.admin_id, environment_id=env.id))
    _commit_or_400(session, "Environment olusturulamadi: ID/Admin kontrol edin.")
    session.refresh(env)
    return env


def delete_environment(environment_id: str, session: Session) -> dict[str, str]:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment bulunamadi.")
    session.delete(env)
    _commit_or_400(session, "Environment silinemedi.")
    return {"message": "Environment silindi."}


def add_user_to_environment(environment_id: str, user_id: str, session: Session) -> UserEnvironment:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment bulunamadi.")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User bulunamadi.")

    existing = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Kullanici zaten bu environment icinde.")

    membership = UserEnvironment(user_id=user_id, environment_id=environment_id)
    session.add(membership)
    _commit_or_400(session, "Kullanici environment'e eklenemedi.")
    session.refresh(membership)
    return membership


def invite_user_to_environment(
    environment_id: str, inviter_id: str, target_user_id: str, session: Session
) -> dict[str, str]:
    """Admin, bir kullaniciyi ID'sine gore environment'e davet eder.

    Dogrudan eklemek yerine hedef kullaniciya bir bildirim (kind=
    ``environment_invite``, requires_action) gonderir. Kullanici bildirimi
    onaylarsa ``confirm()`` icinde ``add_user_to_environment`` calisir.
    """
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment bulunamadi.")
    require_environment_admin(inviter_id, environment_id, session)

    target = session.get(User, target_user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Bu ID ile bir kullanici bulunamadi.")

    if target_user_id == env.admin_id:
        raise HTTPException(status_code=400, detail="Kullanici zaten environment admini.")

    existing = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == target_user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Kullanici zaten bu environment icinde.")

    # Local import to avoid a circular import with notification_service.
    from app.application.services import notification_service

    # Ayni environment icin bekleyen bir davet varsa tekrar gondermeyelim.
    pending_invites = list(
        session.exec(
            select(Notification).where(
                Notification.user_id == target_user_id,
                Notification.kind == NotificationKind.EnvironmentInvite.value,
                Notification.status.in_(  # type: ignore[attr-defined]
                    [NotificationStatus.Fired.value, NotificationStatus.Pending.value]
                ),
            )
        )
    )
    for inv in pending_invites:
        if (inv.payload or {}).get("environment_id") == environment_id:
            raise HTTPException(
                status_code=409,
                detail="Bu kullaniciya zaten bekleyen bir davet gonderildi.",
            )

    inviter = session.get(User, inviter_id)
    inviter_name = (inviter.full_name if inviter else None) or inviter_id
    env_name = env.name or environment_id
    now = datetime.now(UTC)

    note = notification_service._create_notification(  # noqa: SLF001
        session,
        user_id=target_user_id,
        kind=NotificationKind.EnvironmentInvite,
        title="Environment daveti",
        body=(
            f"{inviter_name}, seni \"{env_name}\" ({environment_id}) environment'ine "
            "davet etti. Katilmak icin onayla."
        ),
        scheduled_for=now,
        requires_action=True,
        payload={
            "environment_id": environment_id,
            "environment_name": env_name,
            "inviter_id": inviter_id,
            "inviter_name": inviter_name,
        },
        initial_status=NotificationStatus.Fired,
    )
    note.fired_at = now
    session.add(note)
    _commit_or_400(session, "Davet gonderilemedi.")
    return {"message": f"{target.full_name or target_user_id} kullanicisina davet gonderildi."}


def remove_user_from_environment(
    environment_id: str, user_id: str, session: Session
) -> dict[str, str]:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment bulunamadi.")
    if env.admin_id == user_id:
        raise HTTPException(
            status_code=400, detail="Environment admini cikarilamaz."
        )
    membership = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=404, detail="Kullanici bu environment icinde degil.")
    session.delete(membership)
    _commit_or_400(session, "Kullanici environment'ten cikarilamadi.")
    return {"message": "Kullanici environment'ten cikarildi."}


def _get_env_or_404(environment_id: str, session: Session) -> Environment:
    env = session.get(Environment, environment_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment bulunamadi.")
    return env


def _assert_env_admin(env: Environment, admin_user_id: str) -> None:
    if env.admin_id != admin_user_id:
        raise HTTPException(status_code=403, detail="Bu islem icin environment admini olmalisiniz.")


def create_join_request(
    environment_id: str, user_id: str, session: Session
) -> EnvironmentJoinRequest:
    env = _get_env_or_404(environment_id, session)
    if env.admin_id == user_id:
        raise HTTPException(status_code=400, detail="Kullanici zaten environment admini.")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User bulunamadi.")
    existing = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Kullanici zaten bu environment icinde.")
    req = EnvironmentJoinRequest(environment_id=environment_id, user_id=user_id)
    session.add(req)
    _commit_or_400(session, "Join request olusturulamadi.")
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
        )
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
        raise HTTPException(status_code=404, detail="Join request bulunamadi.")
    existing = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == req.user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if existing is not None:
        session.delete(req)
        _commit_or_400(session, "Join request temizlenemedi.")
        return existing
    membership = UserEnvironment(user_id=req.user_id, environment_id=environment_id)
    session.add(membership)
    session.delete(req)
    _commit_or_400(session, "Membership olusturulamadi.")
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
        raise HTTPException(status_code=404, detail="Join request bulunamadi.")
    session.delete(req)
    _commit_or_400(session, "Join request silinemedi.")
    return {"message": "Join request reddedildi."}


def list_environment_members(
    environment_id: str, session: Session
) -> list[dict[str, str | None]]:
    _get_env_or_404(environment_id, session)
    user_ids = session.exec(
        select(UserEnvironment.user_id).where(
            UserEnvironment.environment_id == environment_id
        )
    ).all()
    members: list[dict[str, str | None]] = []
    for user_id in user_ids:
        user = session.get(User, user_id)
        if user is not None:
            members.append(
                {
                    "user_id": user.id,
                    "full_name": user.full_name,
                    "avatar_key": user.avatar_key,
                }
            )
    return members


def list_environment_streaks(
    environment_id: str,
    session: Session,
    *,
    days: int = 10,
) -> list[dict[str, Any]]:
    """Return per-member positive-advice streak data for an environment.

    Each entry contains: user_id, full_name, avatar_key, days (list[bool]) for
    the last `days` calendar days where the day "qualifies" (≥2 distinct
    advice completions), and weekly_streak_count which is the *current*
    running streak (from `user_daily_streaks.current_streak`). The list is
    sorted by current streak desc (top performers first).
    """
    _get_env_or_404(environment_id, session)
    days = max(1, min(days, 60))
    user_ids = session.exec(
        select(UserEnvironment.user_id).where(
            UserEnvironment.environment_id == environment_id
        )
    ).all()

    now = datetime.now(UTC)
    today = now.date()
    start_day = today - timedelta(days=days - 1)

    results: list[dict[str, Any]] = []
    for user_id in user_ids:
        user = session.get(User, user_id)
        if user is None:
            continue
        active_dates = _qualifying_advice_dates(
            user_id, session, start_day=start_day
        )
        flags: list[bool] = []
        for offset in range(days):
            d = start_day + timedelta(days=offset)
            flags.append(d in active_dates)
        streak_row = session.get(UserDailyStreak, user_id)
        current_streak = streak_row.current_streak if streak_row is not None else 0
        results.append(
            {
                "user_id": user.id,
                "full_name": user.full_name,
                "avatar_key": user.avatar_key,
                "days": flags,
                "weekly_streak_count": current_streak,
            }
        )
    results.sort(key=lambda r: r["weekly_streak_count"], reverse=True)
    return results


def _require_environment_access(user_id: str, environment_id: str, session: Session) -> None:
    env = _get_env_or_404(environment_id, session)
    if env.admin_id == user_id:
        return
    link = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == environment_id,
        )
    ).first()
    if link is None:
        raise HTTPException(status_code=403, detail="Bu environment icin yetkiniz yok.")


def require_environment_access(user_id: str, environment_id: str, session: Session) -> None:
    """Public alias for route-level authorization checks."""
    _require_environment_access(user_id, environment_id, session)


def require_environment_admin(user_id: str, environment_id: str, session: Session) -> None:
    env = _get_env_or_404(environment_id, session)
    _assert_env_admin(env, user_id)


def list_devices(session: Session) -> list[Device]:
    return list(session.exec(select(Device)))


def list_devices_for_environment(
    environment_id: str, user_id: str, session: Session
) -> list[Device]:
    _require_environment_access(user_id, environment_id, session)
    return list(session.exec(select(Device).where(Device.environment_id == environment_id)))


def create_device(payload: DeviceCreate, session: Session) -> Device:
    device = Device.model_validate(payload.model_dump(exclude_unset=True))
    session.add(device)
    _commit_or_400(session, "Device olusturulamadi: Environment/FK kontrol edin.")
    session.refresh(device)
    return device


def create_device_authenticated(
    payload: DeviceCreate, user_id: str, session: Session
) -> Device:
    _require_environment_access(user_id, payload.environment_id, session)
    return create_device(payload, session)


def delete_device(device_id: int, session: Session) -> dict[str, str]:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device bulunamadi.")
    session.delete(device)
    _commit_or_400(session, "Device silinemedi.")
    return {"message": "Device silindi."}


def delete_device_authenticated(device_id: int, user_id: str, session: Session) -> dict[str, str]:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device bulunamadi.")
    _require_environment_access(user_id, device.environment_id, session)
    return delete_device(device_id, session)


def patch_device(
    device_id: int, user_id: str, payload: DeviceUpdate, session: Session
) -> Device:
    """Partial update for a device — used for runtime controls like
    temperature, brightness and on/off state, and for renaming."""
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device bulunamadi.")
    _require_environment_access(user_id, device.environment_id, session)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(device, key, value)
    session.add(device)
    _commit_or_400(session, "Device guncellenemedi.")
    session.refresh(device)
    return device


def set_device_status_authenticated(
    device_id: int,
    user_id: str,
    status: bool,
    session: Session,
    *,
    current_value: Decimal | None = None,
) -> tuple[Device, BehaviorLog]:
    """
    Sprint D — akıllı cihaz simülasyonu: durumu günceller ve bir BehaviorLog yazar.
    Inference arka planda route katmanında tetiklenir.
    """
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device bulunamadi.")
    _require_environment_access(user_id, device.environment_id, session)

    device.status = status
    if current_value is not None:
        device.current_value = current_value
    session.add(device)
    session.flush()

    action = "TurnOn" if status else "TurnOff"
    log = BehaviorLog(
        user_id=user_id,
        device_id=device_id,
        action=action,
        event_time=datetime.now(UTC),
        parameters=json.dumps(
            {
                "source": "device_toggle",
                "device_name": device.name or str(device.type.value),
            }
        ),
    )
    session.add(log)
    _commit_or_400(session, "Cihaz durumu veya behavior log kaydedilemedi.")
    session.refresh(device)
    session.refresh(log)
    return device, log


def run_inference_for_behavior_log_background(log_id: int | None) -> None:
    """BackgroundTasks icin: yeni session acip inference calistirir."""
    if log_id is None:
        return
    from app.db.database import engine

    with Session(engine) as task_session:
        decision = run_inference_for_behavior_log(log_id, task_session)
        if decision:
            logger.info("AI onerisi (device toggle): %s", decision.get("message"))


def list_behavior_logs(session: Session) -> list[BehaviorLog]:
    return list(session.exec(select(BehaviorLog)))


def _qualifying_advice_dates(
    user_id: str,
    session: Session,
    *,
    start_day: date,
    qualifying_threshold: int = 2,
) -> set[date]:
    """Return the set of calendar dates the user completed ≥`qualifying_threshold`
    DISTINCT positive advices on (==day "qualifies" for streak)."""
    cutoff = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
    logs = list(
        session.exec(
            select(PositiveAdviceLog).where(
                PositiveAdviceLog.user_id == user_id,
                PositiveAdviceLog.completed_at >= cutoff,
            )
        )
    )
    by_day: dict[date, set[str]] = {}
    for log in logs:
        ct = log.completed_at
        if ct is None:
            continue
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=UTC)
        by_day.setdefault(ct.date(), set()).add(log.advice_key)
    return {d for d, keys in by_day.items() if len(keys) >= qualifying_threshold}


def get_daily_activity(
    user_id: str,
    session: Session,
    *,
    days: int = 10,
) -> dict[str, Any]:
    """Return last `days` days of positive-advice activity for a user.

    A day counts as `active` if the user has completed at least 2 DISTINCT
    `positive_advice_logs` on that calendar day (UTC) — the same qualifying
    rule used by the daily-streak service. The most recent day is at the
    end of the list (chronological order) — matches the dashboard streak
    visualisation. ``weekly_streak_count`` exposes the *current* running
    streak from ``user_daily_streaks.current_streak`` so the dashboard can
    show e.g. 30 days instead of the rolling 7-day window.
    """
    days = max(1, min(days, 60))
    now = datetime.now(UTC)
    today = now.date()
    start_day = today - timedelta(days=days - 1)

    active_dates = _qualifying_advice_dates(user_id, session, start_day=start_day)

    series: list[dict[str, Any]] = []
    for offset in range(days):
        d = start_day + timedelta(days=offset)
        series.append({"date": d.isoformat(), "active": d in active_dates})

    streak_row = session.get(UserDailyStreak, user_id)
    current_streak = streak_row.current_streak if streak_row is not None else 0

    return {
        "user_id": user_id,
        "days": series,
        "weekly_streak_count": current_streak,
    }


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
    _commit_or_400(session, "BehaviorLog olusturulamadi: User/Device/FK kontrol edin.")
    session.refresh(log)
    # If this action is the trigger side of a mined A→B sequence rule, drop
    # a "sequence_trigger" notification so the user can confirm starting B.
    try:
        _maybe_emit_sequence_trigger(session, log)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("sequence trigger emit failed: %s", exc)
    return log


def _maybe_emit_sequence_trigger(session: Session, log: BehaviorLog) -> None:
    """If the just-written behaviour log matches an active A→B sequence
    rule in ``habit_matrix``, emit a one-shot notification offering to
    perform B.

    ``habit_matrix`` stores trigger/target as opaque ``"{device_id}_{action}"``
    tokens (see ``rebuild_habit_matrix``), so we look up by token equality
    and parse the target side to resolve a real Device row. Low-confidence
    rules are skipped per ``DEVICE_HABIT_MIN_PROBABILITY``.
    """
    # Imported locally to avoid a circular import (notification_service
    # references core.models which itself drags this service via tests).
    from app.application.services import notification_service
    from app.models.habit_matrix import HabitMatrix

    if log.device_id is None or not log.action:
        return

    trigger_token = f"{log.device_id}_{log.action}"
    rules = list(
        session.exec(
            select(HabitMatrix).where(
                HabitMatrix.user_id == log.user_id,
                HabitMatrix.trigger_event == trigger_token,
            )
        )
    )
    if not rules:
        return

    now = datetime.now(UTC)
    emitted = 0
    for rule in rules:
        try:
            conf = float(rule.probability)
        except (TypeError, ValueError):
            continue
        if conf < notification_service.DEVICE_HABIT_MIN_PROBABILITY:
            continue

        # Parse "{device_id}_{action}" out of the target_event token.
        target_token = str(rule.target_event)
        if "_" not in target_token:
            continue
        head, _, target_action = target_token.partition("_")
        if not head.isdigit() or not target_action:
            continue
        target_device = session.get(Device, int(head))
        if target_device is None:
            continue

        target_name = target_device.name or f"Device {target_device.id}"
        verb = "turn on" if target_action.lower().endswith("on") else "turn off"
        title = f"{target_name}?"
        body = (
            f"You usually {verb} {target_name} right after this. "
            "Confirm to log it now."
        )
        note = notification_service._create_notification(  # noqa: SLF001
            session,
            user_id=log.user_id,
            kind=notification_service.NotificationKind.SequenceTrigger,
            title=title,
            body=body,
            scheduled_for=now,
            requires_action=True,
            payload={
                "source_log_id": log.id,
                "trigger_device_id": log.device_id,
                "trigger_action": log.action,
                "target_device_id": target_device.id,
                "device_id": target_device.id,
                "action": target_action,
                "confidence": round(conf, 3),
            },
            initial_status=notification_service.NotificationStatus.Fired,
        )
        note.fired_at = now
        session.add(note)
        emitted += 1
    if emitted:
        session.commit()


def delete_behavior_log(log_id: int, session: Session) -> dict[str, str]:
    log = session.get(BehaviorLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="BehaviorLog bulunamadi.")
    session.delete(log)
    _commit_or_400(session, "BehaviorLog silinemedi.")
    return {"message": "BehaviorLog silindi."}


def mine_behavior_sequences(
    session: Session,
    *,
    window_minutes: int = 15,
    min_confidence: float = 0.50,
    min_support: int = 2,
) -> list[dict[str, Any]]:
    logs = list(session.exec(select(BehaviorLog)))
    if not logs:
        return []

    rows: list[dict[str, Any]] = []
    for log in logs:
        device = session.get(Device, log.device_id)
        device_name = None
        if device is not None:
            device_name = device.name or str(device.type)
        rows.append(
            {
                "user_id": log.user_id,
                "device_id": log.device_id,
                "device_name": device_name if device_name else str(log.device_id),
                "action": log.action,
                "event_time": log.event_time,
            }
        )

    logs_df = pd.DataFrame(rows)
    cfg = SequenceMinerConfig(
        window_minutes=window_minutes,
        min_confidence=min_confidence,
        min_support=min_support,
    )
    return mine_habit_sequences(logs_df, cfg)


def list_habits(session: Session) -> list[Habit]:
    return list(session.exec(select(Habit)))


def list_habits_for_user(user_id: str, session: Session) -> list[Habit]:
    return list(session.exec(select(Habit).where(Habit.user_id == user_id)))


def create_habit(payload: HabitCreate, session: Session) -> Habit:
    habit = Habit.model_validate(payload.model_dump(exclude_unset=True))
    session.add(habit)
    _commit_or_400(session, "Habit olusturulamadi: FK veya olasilik degerini kontrol edin.")
    session.refresh(habit)
    return habit


def patch_habit(habit_id: int, user_id: str, payload: HabitUpdate, session: Session) -> Habit:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(status_code=404, detail="Habit bulunamadi.")
    if habit.user_id != user_id:
        raise HTTPException(status_code=403, detail="Sadece kendi habit kaydinizi guncelleyebilirsiniz.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(habit, key, value)
    session.add(habit)
    _commit_or_400(session, "Habit guncellenemedi.")
    session.refresh(habit)
    return habit


def delete_habit(habit_id: int, session: Session) -> dict[str, str]:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(status_code=404, detail="Habit bulunamadi.")
    session.delete(habit)
    _commit_or_400(session, "Habit silinemedi.")
    return {"message": "Habit silindi."}


def delete_habit_authenticated(habit_id: int, user_id: str, session: Session) -> dict[str, str]:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(status_code=404, detail="Habit bulunamadi.")
    if habit.user_id != user_id:
        raise HTTPException(status_code=403, detail="Sadece kendi habit kaydinizi silebilirsiniz.")
    return delete_habit(habit_id, session)


def list_users(session: Session) -> list[User]:
    return list(session.exec(select(User)))


def _extract_plain_password(data: dict[str, Any]) -> str | None:
    """`UserCreate`/`UserUpdate` payload'ından düz parolayı ayıkla.

    Geri-uyumluluk için iki alan adı da kabul edilir:
    - `password`        → yeni (Sprint B sonrası tercih edilen)
    - `password_hash`   → eski frontend; içerik düz metin parola
    """
    plain = data.pop("password", None)
    legacy = data.pop("password_hash", None)
    if plain:
        return str(plain)
    if legacy:
        # Hâlihazırda bcrypt hash gönderildiyse aynen kabul et — pratikte
        # frontend bu yolu kullanmaz, ama korunmaya değer.
        if looks_like_bcrypt_hash(str(legacy)):
            data["password_hash"] = str(legacy)
            return None
        return str(legacy)
    return None


def login_user(payload: LoginRequest, session: Session) -> User:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email veya parola hatali.")
    return user


def create_user(payload: UserCreate, session: Session) -> User:
    data = payload.model_dump(exclude_unset=True)
    # Persist gender on the user row (used by cold-start + recommendation
    # cohort). Keep the value for provisioning below.
    gender = data.get("gender")
    plain_password = _extract_plain_password(data)
    if plain_password:
        data["password_hash"] = hash_password(plain_password)
    if not data.get("id"):
        data["id"] = _next_prefixed_id(session, User, "P")
    user = User.model_validate(data)
    session.add(user)
    _commit_or_400(session, "Kullanici olusturulamadi: ID veya email cakismasi olabilir.")
    session.refresh(user)
    if gender:
        provision_cold_start_defaults(
            user, session, gender=gender, save_recommendation=save_recommendation
        )
    return user


def update_user(user_id: str, payload: UserUpdate, session: Session) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User bulunamadi.")
    data = payload.model_dump(exclude_unset=True)
    plain_password = _extract_plain_password(data)
    if plain_password:
        data["password_hash"] = hash_password(plain_password)
    for key, value in data.items():
        setattr(user, key, value)
    session.add(user)
    _commit_or_400(session, "User guncellenemedi: email cakismasi olabilir.")
    session.refresh(user)
    return user


def _next_recommendation_id(session: Session) -> str:
    existing_ids = session.exec(select(Recommendation.id)).all()
    max_num = 0
    pattern = re.compile(r"^REC-(\d{7})$")
    for raw in existing_ids:
        if isinstance(raw, str):
            m = pattern.match(raw)
            if m:
                max_num = max(max_num, int(m.group(1)))
    return f"REC-{max_num + 1:07d}"


def _fetch_user_behavior_logs(session: Session, user_id: str) -> list[BehaviorLog]:
    return list(
        session.exec(
            select(BehaviorLog).where(BehaviorLog.user_id == user_id).order_by(BehaviorLog.event_time.asc())
        )
    )


def _device_label(session: Session, device_id: int) -> str:
    dev = session.get(Device, device_id)
    if dev is None:
        return f"DEVICE_{device_id}"
    return dev.name or str(dev.type)


def save_recommendation(
    user_id: str,
    recommendation: dict[str, Any],
    session: Session,
) -> Recommendation:
    target_token = str(recommendation.get("target", ""))
    trigger_token = str(recommendation.get("trigger", ""))
    action = "ON"
    target_device = target_token
    if "_" in target_token:
        parts = target_token.split("_")
        if len(parts) >= 2:
            action = parts[-1]
            target_device = "_".join(parts[:-1])
    trigger_device = trigger_token.rsplit("_", 1)[0] if "_" in trigger_token else trigger_token

    row = Recommendation(
        id=_next_recommendation_id(session),
        user_id=user_id,
        trigger_device=trigger_device,
        target_device=target_device,
        action=action,
        confidence=Decimal(str(float(recommendation.get("final_confidence", 0.0)))),
        recommendation_type=str(recommendation.get("type", "SUGGESTION")),
        context=str(recommendation.get("context", "Pending")),
        status=RecommendationStatus.Pending,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    _commit_or_400(session, "Recommendation kaydedilemedi.")
    session.refresh(row)
    return row


def get_latest_pending_recommendation(
    user_id: str,
    session: Session,
    *,
    max_age_minutes: int | None = None,
) -> Recommendation | None:
    if max_age_minutes is None:
        max_age_minutes = settings.recommendation_max_age_minutes
    expire_old_recommendations(session, max_age_minutes=max_age_minutes)
    rows = list(
        session.exec(
            select(Recommendation)
            .where(
                Recommendation.user_id == user_id,
                Recommendation.status == RecommendationStatus.Pending,
            )
            .order_by(Recommendation.created_at.desc())
        )
    )
    if not rows:
        return None
    now = datetime.now(UTC)
    max_age = timedelta(minutes=max_age_minutes)
    for row in rows:
        created_at = row.created_at
        if isinstance(created_at, datetime) and now - created_at <= max_age:
            return row
    return None


def expire_old_recommendations(
    session: Session, *, max_age_minutes: int | None = None
) -> int:
    if max_age_minutes is None:
        max_age_minutes = settings.recommendation_max_age_minutes
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=max_age_minutes)
    rows = list(
        session.exec(
            select(Recommendation).where(
                Recommendation.status == RecommendationStatus.Pending,
                Recommendation.created_at < cutoff,
            )
        )
    )
    for row in rows:
        row.status = RecommendationStatus.Expired
        session.add(row)
    if rows:
        _commit_or_400(session, "Eski recommendation kayitlari expire edilemedi.")
    return len(rows)


def update_recommendation_status(
    recommendation_id: str,
    status: RecommendationStatus,
    session: Session,
) -> Recommendation:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation bulunamadi.")
    rec.status = status
    session.add(rec)
    _commit_or_400(session, "Recommendation status guncellenemedi.")
    session.refresh(rec)
    return rec


def penalize_habit_matrix_from_rejection(
    recommendation_id: str,
    session: Session,
    *,
    penalty_factor: float = 0.85,
    min_probability: float = 0.01,
) -> int:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation bulunamadi.")

    trigger_event = f"{rec.trigger_device}_{rec.action}"
    target_event = f"{rec.target_device}_{rec.action}"
    ctx = str(rec.context or "Pending")
    day_night = "Night" if ctx.lower() in {"night", "evening"} else "Day"
    rows = list(
        session.exec(
            select(HabitMatrix).where(
                HabitMatrix.user_id == rec.user_id,
                HabitMatrix.trigger_event == trigger_event,
                HabitMatrix.target_event == target_event,
                HabitMatrix.context == day_night,
            )
        )
    )
    for row in rows:
        new_p = max(min_probability, float(row.probability) * penalty_factor)
        row.probability = new_p
        row.last_updated = datetime.now(UTC)
        session.add(row)
    if rows:
        _commit_or_400(session, "HabitMatrix penalize islemi basarisiz.")
    return len(rows)


def run_inference_for_behavior_log(log_id: int, session: Session) -> dict[str, Any] | None:
    log = session.get(BehaviorLog, log_id)
    if log is None:
        return None

    all_logs = _fetch_user_behavior_logs(session, log.user_id)
    behavior_logs_payload: list[dict[str, Any]] = []
    for x in all_logs:
        behavior_logs_payload.append(
            {
                "user_id": x.user_id,
                "device_name": _device_label(session, x.device_id),
                "action": x.action,
                "event_time": x.event_time,
            }
        )

    trigger_event = {
        "device_id": _device_label(session, log.device_id),
        "action": log.action,
        "event_time": log.event_time,
        "user_id": log.user_id,
        "history_log_count": len(all_logs),
        "behavior_logs": behavior_logs_payload,
    }
    decision = process_decision_sync(trigger_event, session=session)
    anomaly = detect_safety_anomaly(log, session)
    if decision:
        recs = decision.get("recommendations") or []
        if recs:
            # Coklu aksiyon varsa hepsini recommendation havuzuna ekle.
            for item in recs:
                one = {
                    "trigger": decision.get("trigger", ""),
                    "target": item.get("target", ""),
                    "final_confidence": item.get("final_confidence", 0.0),
                }
                save_recommendation(log.user_id, one, session)
        else:
            save_recommendation(log.user_id, decision, session)
    if anomaly:
        save_recommendation(log.user_id, anomaly, session)
    return decision


def detect_safety_anomaly(
    log: BehaviorLog,
    session: Session,
    *,
    publisher: EventPublisher | None = None,
    k: float = 2.0,
) -> dict[str, Any] | None:
    """
    Cihaz normal acik kalma suresinin k kati asildiysa SAFETY_ANOMALY uretir ve
    AnomalyDetected domain event'ini yayinlar.
    """
    if log.duration_hm is None:
        return None
    cur_minutes = float(log.duration_hm.total_seconds() / 60.0)
    if cur_minutes <= 0:
        return None

    prev = list(
        session.exec(
            select(BehaviorLog).where(
                BehaviorLog.user_id == log.user_id,
                BehaviorLog.device_id == log.device_id,
                BehaviorLog.duration_hm.is_not(None),
                BehaviorLog.id != log.id,
            )
        )
    )
    vals = [float(x.duration_hm.total_seconds() / 60.0) for x in prev if x.duration_hm is not None]
    is_anomaly, avg_minutes = evaluate_duration_anomaly(cur_minutes, vals, k=k, min_samples=3)
    if not is_anomaly:
        return None

    dev = _device_label(session, log.device_id)
    confidence = min(0.99, cur_minutes / (k * avg_minutes))
    if publisher is not None:
        publisher.publish(
            AnomalyDetected(
                user_id=log.user_id,
                device_id=int(log.device_id),
                device_label=dev,
                action=str(log.action),
                current_minutes=cur_minutes,
                average_minutes=avg_minutes,
                k_threshold=k,
                confidence=confidence,
            )
        )
    # Drop a high-priority notification into the bell feed so the user
    # actually sees the anomaly (independent of the legacy recommendations
    # table). The notification is created already-`fired` so it appears
    # immediately and is not "actionable" — dismissing is enough.
    try:
        from app.application.services import notification_service

        now_utc = datetime.now(UTC)
        title = f"{dev} has been on too long"
        body = (
            f"{dev} ({log.action}) has been running for "
            f"{cur_minutes:.0f} min — about {cur_minutes / max(avg_minutes, 1):.1f}× "
            f"your usual {avg_minutes:.0f} min. Please check if it should be off."
        )
        note = notification_service._create_notification(  # noqa: SLF001
            session,
            user_id=log.user_id,
            kind=notification_service.NotificationKind.SafetyAnomaly,
            title=title,
            body=body,
            scheduled_for=now_utc,
            requires_action=False,
            payload={
                "device_id": log.device_id,
                "device_name": dev,
                "current_minutes": round(cur_minutes, 1),
                "average_minutes": round(avg_minutes, 1),
                "k_threshold": k,
                "confidence": round(confidence, 3),
            },
            initial_status=notification_service.NotificationStatus.Fired,
        )
        note.fired_at = now_utc
        session.add(note)
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("safety_anomaly notification emit failed: %s", exc)

    return {
        "type": "SAFETY_ANOMALY",
        "trigger": f"{dev}_{log.action}",
        "target": f"{dev}_CHECK",
        "context": "Safety",
        "final_confidence": confidence,
        "message": f"{dev} normal sureyi asti (anomaly).",
    }


def get_habit_matrix_candidates(
    user_id: str,
    trigger_event: str,
    context: str,
    session: Session,
) -> list[HabitMatrix]:
    rows = list(
        session.exec(
            select(HabitMatrix)
            .where(
                HabitMatrix.user_id == user_id,
                HabitMatrix.trigger_event == trigger_event,
                HabitMatrix.context == context,
            )
            .order_by(HabitMatrix.probability.desc())
        )
    )
    return rows


_DEVICE_HABIT_PREFIX = "Device: "
_DEVICE_ROUTINE_PREFIX = "Routine: "
_DEVICE_HABIT_ENTER_THRESHOLD = 0.60
_DEVICE_HABIT_EXIT_THRESHOLD = 0.45

# A (device, action) ritmi → habit. Aynı saat diliminde son
# ``ROUTINE_LOOKBACK_DAYS`` gün içindeki HER takvim günü bir "fırsat" sayılır;
# o gün aksiyon yapıldıysa 1, yapılmadıysa 0. Habit olasılığı, bugüne yakın
# günleri daha ağır tutan recency-ağırlıklı ortalamadır (sequence mining'den
# BAĞIMSIZ, ayrı bir konu):
#
#     P = Σ(w_d)  [aktif günler] / Σ(w_d)  [penceredeki tüm günler]
#     w_d = e^(-λ · Δgün)        λ = 0.0077  → yarı-ömür ≈ 90 gün
#
# Histerezis: P ≥ 0.60 → habit aktifleşir, P < 0.45 → pasifleşir ("unutulur").
ROUTINE_DECAY_LAMBDA: float = 0.0077  # yarı-ömür ≈ 90 gün (math.log(2)/0.0077)
ROUTINE_MIN_ACTIVE_DAYS: int = 5  # gürültü filtresi: en az bu kadar aktif gün
ROUTINE_LOOKBACK_DAYS: int = 30
# Erken/geç açılma yumuşatma payı: bu kadar dakika içindeki açılışlar AYNI
# rutin sayılır (saat sınırını geçse bile, örn. 06:55 ↔ 07:05). Sabit
# saat-kovası yerine ±dakika kümeleme kullanılır.
ROUTINE_SMOOTHING_MINUTES: int = 10


def _recency_weighted_active_ratio(
    active_dates: set[date],
    *,
    today: date,
    lookback_days: int = ROUTINE_LOOKBACK_DAYS,
    lam: float = ROUTINE_DECAY_LAMBDA,
) -> float:
    """Tek cihaz rutini için zaman-ağırlıklı alışkanlık gücü.

    Pencere: ilk aktif günden ``today``'e kadar (en fazla ``lookback_days``).
    Penceredeki her gün bir fırsattır; o gün aksiyon varsa katkı ``w_d`` kadar.

        P = Σ(w_d · yapildi_d) / Σ(w_d)   ,   w_d = exp(-lam · Δgün)

    Örn. son 10 günün 9'unda yapıldıysa P ≈ 0.90; kullanım seyrekleşip
    durdukça yeni "0" günleri ağır bastığından P düşer ve habit unutulur.
    """
    import math

    if not active_dates:
        return 0.0
    window_start = max(min(active_dates), today - timedelta(days=lookback_days - 1))
    num = 0.0
    den = 0.0
    day = window_start
    one_day = timedelta(days=1)
    while day <= today:
        weight = math.exp(-lam * (today - day).days)
        den += weight
        if day in active_dates:
            num += weight
        day += one_day
    return num / den if den > 0 else 0.0


def _circular_minute_distance(a: int, b: int) -> int:
    """İki günün-içi dakika değeri arasındaki en kısa (gün döngüsel) mesafe."""
    diff = abs(a - b) % (24 * 60)
    return min(diff, 24 * 60 - diff)


def _best_time_cluster(
    events: list[tuple[date, int]],
    tol_minutes: int = ROUTINE_SMOOTHING_MINUTES,
) -> tuple[int, set[date]]:
    """En çok ayrı günü ``±tol_minutes`` içinde toplayan zaman kümesini bulur.

    ``events`` = (tarih, günün_dakikası) listesi. Erken/geç açılmalar (örn.
    06:55 ve 07:05) tek bir rutin altında birleşsin diye sabit saat-kovası
    yerine kayan ±dakika penceresi kullanılır. Döner: (çapa_dakika, gün_kümesi).
    """
    if not events:
        return 0, set()
    candidate_minutes = sorted({m for _, m in events})
    best_anchor = candidate_minutes[0]
    best_dates: set[date] = set()
    for center in candidate_minutes:
        dates = {
            d for d, m in events if _circular_minute_distance(m, center) <= tol_minutes
        }
        if len(dates) > len(best_dates):
            best_dates = dates
            best_anchor = center
    return best_anchor, best_dates


def _sync_device_habits_from_matrix(
    session: Session,
    user_id: str,
    matrix_rules: list[dict[str, Any]],
) -> int:
    """Upsert ``Habit`` rows from mined ``habit_matrix`` rules for a user.

    Histerezis (giriş ≥0.60, çıkış <0.45) — bu eşik aralığında eski durum
    korunur. Eşik altı kurallar zaten ``mine_habit_sequences`` tarafından
    filtreleniyor olabilir; biz yine de güvenli upsert yapıyoruz.
    """
    if not matrix_rules:
        return 0

    existing = {
        h.name: h
        for h in session.exec(
            select(Habit).where(
                Habit.user_id == user_id, Habit.name.like(f"{_DEVICE_HABIT_PREFIX}%")
            )
        )
    }
    touched_names: set[str] = set()
    upserted = 0
    for rule in matrix_rules:
        trig = str(rule.get("trigger", ""))
        tgt = str(rule.get("target", ""))
        ctx = str(rule.get("context", ""))
        prob = float(rule.get("probability", rule.get("confidence", 0.0)))
        name = f"{_DEVICE_HABIT_PREFIX}{trig} → {tgt} ({ctx})"
        touched_names.add(name)
        prob_dec = Decimal(str(round(prob, 2)))

        habit = existing.get(name)
        if habit is None:
            if prob < _DEVICE_HABIT_ENTER_THRESHOLD:
                continue
            habit = Habit(
                user_id=user_id,
                name=name,
                probability_score=prob_dec,
                is_active=True,
                recurrence_type=HabitRecurrence.Daily,
                device_id=None,
            )
            session.add(habit)
            upserted += 1
        else:
            habit.probability_score = prob_dec
            if prob >= _DEVICE_HABIT_ENTER_THRESHOLD:
                habit.is_active = True
            elif prob < _DEVICE_HABIT_EXIT_THRESHOLD:
                habit.is_active = False
            session.add(habit)
            upserted += 1

    # Mining kurallarından düşen eski habitleri pasifleştir (silmiyoruz —
    # geçmiş tetikleyici izini korumak için).
    for name, habit in existing.items():
        if name not in touched_names and habit.is_active:
            habit.is_active = False
            session.add(habit)
    return upserted


def detect_device_routines(
    session: Session,
    *,
    reference_time: datetime | None = None,
) -> int:
    """Tek-aksiyon ritimlerini ("Routine: Oven TurnOn @18") Habit'e çevirir.

    Sequence miner sadece A→B çiftlerini yakaladığı için "her sabah 7'de
    lambayı açma" gibi tek cihaz–tek kullanıcı ritimleri burada ele alınır.
    Her ``(user, device, action)`` için en yoğun saat dilimindeki aktif günler
    bulunur ve olasılık ``_recency_weighted_active_ratio`` ile zaman-ağırlıklı
    ortalama olarak hesaplanır. Histerezis (giriş ≥0.60, çıkış <0.45) ile
    habit aktif/pasif yapılır — kullanım durunca P düşer ve habit "unutulur".

    ``reference_time`` test/senaryo için "bugün"ü sabitlemeye yarar.
    """
    from collections import defaultdict

    now = reference_time or datetime.now(UTC)
    today = now.date()
    cutoff = now - timedelta(days=ROUTINE_LOOKBACK_DAYS)
    logs = list(
        session.exec(
            select(BehaviorLog).where(
                BehaviorLog.event_time >= cutoff,
                BehaviorLog.event_time <= now,
            )
        )
    )
    if not logs:
        return 0

    # (user, device, action) -> [(tarih, günün_dakikası), ...]
    grouped: dict[tuple[str, int, str], list[tuple[date, int]]] = defaultdict(list)
    for log in logs:
        if log.device_id is None:
            continue
        key = (log.user_id, log.device_id, log.action)
        minute_of_day = log.event_time.hour * 60 + log.event_time.minute
        grouped[key].append((log.event_time.date(), minute_of_day))

    existing_routines = list(
        session.exec(
            select(Habit).where(Habit.name.like(f"{_DEVICE_ROUTINE_PREFIX}%"))
        )
    )
    by_name: dict[tuple[str, str], Habit] = {
        (h.user_id, h.name): h for h in existing_routines
    }
    touched: set[tuple[str, str]] = set()

    upserted = 0
    for (uid, device_id, action), events in grouped.items():
        # ±10 dk yumuşatma ile en yoğun zaman kümesi ve o kümedeki aktif günler.
        anchor_minute, best_dates = _best_time_cluster(
            events, ROUTINE_SMOOTHING_MINUTES
        )
        if len(best_dates) < ROUTINE_MIN_ACTIVE_DAYS:
            continue

        # Recency-ağırlıklı alışkanlık gücü (sequence mining'den bağımsız).
        prob = min(0.99, _recency_weighted_active_ratio(best_dates, today=today))
        prob_dec = Decimal(str(round(prob, 2)))

        device = session.get(Device, device_id)
        device_name = device.name if device and device.name else f"Device {device_id}"
        action_label = str(action).replace("_", " ").title()
        # Name shape: "Routine: <device> <TurnOn|TurnOff> @HH"
        # The "@HH" suffix is the canonical hour token the notification
        # service parses to know when to fire today's confirm prompt; çapanın
        # en yakın saatine yuvarlanır (±10 dk küme merkezinden).
        name_hour = int(round(anchor_minute / 60.0)) % 24
        name = (
            f"{_DEVICE_ROUTINE_PREFIX}{device_name} {action_label} "
            f"@{name_hour:02d}"
        )

        habit = by_name.get((uid, name))
        if habit is None:
            # Yeni habit yalnızca giriş eşiğini aşınca oluşur.
            if prob < _DEVICE_HABIT_ENTER_THRESHOLD:
                continue
            habit = Habit(
                user_id=uid,
                name=name,
                probability_score=prob_dec,
                is_active=True,
                recurrence_type=HabitRecurrence.Daily,
                device_id=device_id,
            )
            session.add(habit)
        else:
            # Histerezis: skoru daima güncelle; aktiflik eşiklere göre değişir.
            habit.probability_score = prob_dec
            if prob >= _DEVICE_HABIT_ENTER_THRESHOLD:
                habit.is_active = True
            elif prob < _DEVICE_HABIT_EXIT_THRESHOLD:
                habit.is_active = False
            session.add(habit)
        touched.add((uid, name))
        upserted += 1

    # Bu turda hiç görülmeyen eski rutinleri pasifleştir (siliyoruz değil).
    for (uid_name), habit in by_name.items():
        if uid_name not in touched and habit.is_active:
            habit.is_active = False
            session.add(habit)

    try:
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        session.rollback()
        logger.warning("detect_device_routines failed: %s", exc)
        return 0
    return upserted


def rebuild_habit_matrix(session: Session) -> dict[str, int]:
    """
    Tum kullanicilar icin sequence miner'i calistirip habit_matrix tablosuna upsert yapar.

    Aynı zamanda yüksek olasılıklı her kuralı ``habits`` tablosunda
    histerezisli ``Habit`` satırına dönüştürür (dashboard "Active Habits"
    kartı buradan beslenir).
    """
    logs = list(session.exec(select(BehaviorLog).order_by(BehaviorLog.user_id, BehaviorLog.event_time)))
    if not logs:
        return {"users_processed": 0, "rules_upserted": 0, "device_habits_upserted": 0}

    rows: list[dict[str, Any]] = []
    for log in logs:
        rows.append(
            {
                "user_id": log.user_id,
                "device_name": _device_label(session, log.device_id),
                "action": log.action,
                "event_time": log.event_time,
            }
        )
    logs_df = pd.DataFrame(rows)
    users = sorted(logs_df["user_id"].dropna().astype(str).unique().tolist())

    rules_upserted = 0
    device_habits_upserted = 0
    now = datetime.now(UTC)
    cfg = SequenceMinerConfig()

    def _to_day_night(ctx: str) -> str:
        c = str(ctx).strip().lower()
        if c in {"night", "evening"}:
            return "Night"
        return "Day"

    for uid in users:
        sub = logs_df[logs_df["user_id"].astype(str) == uid].copy()
        if sub.empty:
            continue
        mined = mine_habit_sequences(sub, cfg)
        # Kullanici icin tum eski matrix satirlarini silip taze kurallarla yenile.
        old_rows = list(session.exec(select(HabitMatrix).where(HabitMatrix.user_id == uid)))
        for old in old_rows:
            session.delete(old)
        # Force the DELETEs to the DB before queuing INSERTs — otherwise a
        # later autoflush (triggered by _sync_device_habits_from_matrix)
        # would emit INSERTs first and hit the unique constraint on
        # (user_id, trigger_event, target_event, context).
        if old_rows:
            session.flush()
        normalised_rules: list[dict[str, Any]] = []
        for rule in mined:
            trig = str(rule.get("trigger", ""))
            tgt = str(rule.get("target", ""))
            ctx = _to_day_night(str(rule.get("context", "")))
            prob = float(rule.get("probability", rule.get("confidence", 0.0)))
            hm = HabitMatrix(
                user_id=uid,
                trigger_event=trig,
                target_event=tgt,
                context=ctx,
                probability=prob,
                last_updated=now,
            )
            session.add(hm)
            rules_upserted += 1
            normalised_rules.append(
                {"trigger": trig, "target": tgt, "context": ctx, "probability": prob}
            )

        device_habits_upserted += _sync_device_habits_from_matrix(
            session, uid, normalised_rules
        )

    _commit_or_400(session, "Habit matrix rebuild basarisiz.")

    # Tek-aksiyon ritimleri (saatlik rutin) çift kuralından bağımsız;
    # sequence_miner pair gerektirdiği için onlar burada yakalanır.
    routine_habits = detect_device_routines(session)

    return {
        "users_processed": len(users),
        "rules_upserted": rules_upserted,
        "device_habits_upserted": device_habits_upserted,
        "routine_habits_upserted": routine_habits,
    }

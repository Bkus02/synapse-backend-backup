import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.api.schemas import (
    BehaviorLogCreate,
    DeviceCreate,
    EnvironmentCreate,
    HabitCreate,
    UserCreate,
)
from app.analytics.sequence_miner import SequenceMinerConfig, mine_habit_sequences
from app.analytics.decision_engine import process_decision_sync
from app.core.models import (
    BehaviorLog,
    Device,
    Environment,
    Habit,
    Recommendation,
    RecommendationStatus,
    User,
    UserEnvironment,
)
from app.models.habit_matrix import HabitMatrix


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


def create_environment(payload: EnvironmentCreate, session: Session) -> Environment:
    data = payload.model_dump(exclude_unset=True)
    if not data.get("id"):
        data["id"] = _next_prefixed_id(session, Environment, "H")
    env = Environment.model_validate(data)
    session.add(env)
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


def list_devices(session: Session) -> list[Device]:
    return list(session.exec(select(Device)))


def create_device(payload: DeviceCreate, session: Session) -> Device:
    device = Device.model_validate(payload.model_dump(exclude_unset=True))
    session.add(device)
    _commit_or_400(session, "Device olusturulamadi: Environment/FK kontrol edin.")
    session.refresh(device)
    return device


def delete_device(device_id: int, session: Session) -> dict[str, str]:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device bulunamadi.")
    session.delete(device)
    _commit_or_400(session, "Device silinemedi.")
    return {"message": "Device silindi."}


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
    _commit_or_400(session, "BehaviorLog olusturulamadi: User/Device/FK kontrol edin.")
    session.refresh(log)
    return log


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


def create_habit(payload: HabitCreate, session: Session) -> Habit:
    habit = Habit.model_validate(payload.model_dump(exclude_unset=True))
    session.add(habit)
    _commit_or_400(session, "Habit olusturulamadi: FK veya olasilik degerini kontrol edin.")
    session.refresh(habit)
    return habit


def delete_habit(habit_id: int, session: Session) -> dict[str, str]:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(status_code=404, detail="Habit bulunamadi.")
    session.delete(habit)
    _commit_or_400(session, "Habit silinemedi.")
    return {"message": "Habit silindi."}


def list_users(session: Session) -> list[User]:
    return list(session.exec(select(User)))


def create_user(payload: UserCreate, session: Session) -> User:
    data = payload.model_dump(exclude_unset=True)
    if not data.get("id"):
        data["id"] = _next_prefixed_id(session, User, "P")
    user = User.model_validate(data)
    session.add(user)
    _commit_or_400(session, "Kullanici olusturulamadi: ID veya email cakismasi olabilir.")
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
    max_age_minutes: int = 5,
) -> Recommendation | None:
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


def expire_old_recommendations(session: Session, *, max_age_minutes: int = 5) -> int:
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


def detect_safety_anomaly(log: BehaviorLog, session: Session) -> dict[str, Any] | None:
    """
    Cihaz normal acik kalma suresinin 2 kati asildiysa SAFETY_ANOMALY uret.
    Kontrol, duration_hm bilinen (tipik olarak OFF) loglar icin yapilir.
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
    if len(vals) < 3:
        return None
    avg_minutes = sum(vals) / len(vals)
    if avg_minutes <= 0:
        return None
    if cur_minutes < 2.0 * avg_minutes:
        return None

    dev = _device_label(session, log.device_id)
    return {
        "type": "SAFETY_ANOMALY",
        "trigger": f"{dev}_{log.action}",
        "target": f"{dev}_CHECK",
        "context": "Safety",
        "final_confidence": min(0.99, cur_minutes / (2.0 * avg_minutes)),
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


def rebuild_habit_matrix(session: Session) -> dict[str, int]:
    """
    Tum kullanicilar icin sequence miner'i calistirip habit_matrix tablosuna upsert yapar.
    """
    logs = list(session.exec(select(BehaviorLog).order_by(BehaviorLog.user_id, BehaviorLog.event_time)))
    if not logs:
        return {"users_processed": 0, "rules_upserted": 0}

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
        for rule in mined:
            hm = HabitMatrix(
                user_id=uid,
                trigger_event=str(rule.get("trigger", "")),
                target_event=str(rule.get("target", "")),
                context=_to_day_night(str(rule.get("context", ""))),
                probability=float(rule.get("probability", rule.get("confidence", 0.0))),
                last_updated=now,
            )
            session.add(hm)
            rules_upserted += 1

    _commit_or_400(session, "Habit matrix rebuild basarisiz.")
    return {"users_processed": len(users), "rules_upserted": rules_upserted}

"""Demo senaryo — test1'in sabah lamba alışkanlığının recency-ağırlıklı gelişimi.

Bu, tek cihaz–tek kullanıcı RUTİN alışkanlığıdır (sequence mining DEĞİL).
Olasılık, ``smart_home_service.detect_device_routines`` ile aynı motor olan
``_recency_weighted_active_ratio`` ile hesaplanır:

    P = Σ(w_d · o_gün_yaptı) / Σ(w_d)        w_d = e^(-λ·Δgün),  λ = 0.0077

30 gün, 3 evre (her gün ~07:00 lambayı açma fırsatı):
    Evre 1 (gün 1-10) : 9/10 gün açık  -> P ≈ %90  (habit aktif)
    Evre 2 (gün 11-20): 3/10 gün açık   -> P ≈ %59  (zayıflar; histerezis ile aktif kalır)
    Evre 3 (gün 21-30): 0/10 gün açık    -> P ≈ %38  (<%45 -> habit unutulur/pasifleşir)

Loglar ``behavior_logs`` tablosuna yazılır; SQL sorguları en altta basılır.
Tekrar çalıştırılabilir: senaryo lambasının eski logları her seferinde silinir.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

# Yerel saat (Europe/Istanbul, UTC+3): loglar SQL'de sabah ~07:00 görünsün.
TR = timezone(timedelta(hours=3))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text
from sqlmodel import Session, select

from app.application.services import smart_home_service
from app.application.services.smart_home_service import (
    _DEVICE_HABIT_ENTER_THRESHOLD,
    _DEVICE_HABIT_EXIT_THRESHOLD,
    _DEVICE_ROUTINE_PREFIX,
    _recency_weighted_active_ratio,
    detect_device_routines,
)
from app.core.models import BehaviorLog, Device, DeviceType, Environment, Habit, UserEnvironment
from app.db.database import engine

USER_EMAIL = "test1@gmail.com"
ENV_NAME = "Decay Senaryosu (test1)"
LAMP_NAME = "Yatak Odasi Lamba"
MOTION_NAME = "Yatak Odasi Hareket Sensoru"  # eski yanlış senaryodan kalan; temizlenir
LAMP_ACTION = "TurnOn"

PHASE_DAYS = 10
PHASE1_SKIP = {5}             # gün 1-10: 5. gün hariç => 9/10
PHASE2_ACTIVE = {11, 14, 17}  # gün 11-20: sadece 3 gün => 3/10
# Evre 3 (20-29): hiçbir gün aktif değil => 0/10


def _find_user_id(session: Session) -> str:
    row = session.exec(
        text("SELECT id FROM users WHERE lower(email) = :e").bindparams(e=USER_EMAIL.lower())
    ).first()
    if row is None:
        row = session.exec(
            text("SELECT id FROM users WHERE lower(full_name) LIKE '%test1%' LIMIT 1")
        ).first()
    if row is None:
        raise SystemExit(f"Kullanici bulunamadi (email={USER_EMAIL}).")
    return str(row[0])


def _ensure_environment(session: Session, user_id: str) -> str:
    env = session.exec(
        select(Environment).where(
            Environment.name == ENV_NAME, Environment.admin_id == user_id
        )
    ).first()
    if env is None:
        env_id = smart_home_service._next_prefixed_id(session, Environment, "H")
        env = Environment(id=env_id, name=ENV_NAME, admin_id=user_id, location="Demo")
        session.add(env)
        session.flush()
    member = session.exec(
        select(UserEnvironment).where(
            UserEnvironment.user_id == user_id,
            UserEnvironment.environment_id == env.id,
        )
    ).first()
    if member is None:
        session.add(UserEnvironment(user_id=user_id, environment_id=env.id))
    session.flush()
    return str(env.id)


def _ensure_lamp(session: Session, env_id: str) -> int:
    dev = session.exec(
        select(Device).where(Device.environment_id == env_id, Device.name == LAMP_NAME)
    ).first()
    if dev is None:
        dev = Device(
            environment_id=env_id, type=DeviceType.Lamp, status=False,
            name=LAMP_NAME, room="Yatak Odasi",
        )
        session.add(dev)
        session.flush()
    return int(dev.id)


def _cleanup_old_motion(session: Session, env_id: str) -> None:
    """Eski (yanlış) sequence senaryosundan kalan hareket sensörünü temizle."""
    dev = session.exec(
        select(Device).where(Device.environment_id == env_id, Device.name == MOTION_NAME)
    ).first()
    if dev is not None:
        session.exec(
            text("DELETE FROM behavior_logs WHERE device_id = :d").bindparams(d=dev.id)
        )
        session.delete(dev)
        session.flush()


def _is_active_day(day_index: int) -> bool:
    if day_index < PHASE_DAYS:
        return day_index not in PHASE1_SKIP
    if day_index < 2 * PHASE_DAYS:
        return day_index in PHASE2_ACTIVE
    return False


def _phase_of(day_index: int) -> int:
    return day_index // PHASE_DAYS + 1


def seed_logs(session: Session, user_id: str, lamp_id: int) -> datetime:
    session.exec(
        text("DELETE FROM behavior_logs WHERE device_id = :d").bindparams(d=lamp_id)
    )
    today = datetime.now(TR).replace(hour=0, minute=0, second=0, microsecond=0)
    base = today - timedelta(days=3 * PHASE_DAYS - 1)  # gün 0 = bugün-29

    n_on = n_off = 0
    for day_index in range(3 * PHASE_DAYS):
        if not _is_active_day(day_index):
            continue
        phase = _phase_of(day_index)
        # AÇMA alışkanlığı: ~07:00 ±10 dk (erken/geç). 0-jitter günleri var ki
        # ±10 dk yumuşatma çapası 07:00'da tüm günleri toplasın.
        on_jitter = ((day_index % 5) - 2) * 5  # -10,-5,0,+5,+10
        on = base + timedelta(days=day_index, hours=7, minutes=on_jitter)
        # KAPATMA alışkanlığı: ~09:00 ±10 dk (ayrı bir rutin). Açma jitter'ından
        # bağımsız olduğu için lambanın yanma süresi ~2 saat etrafında doğal
        # olarak biraz oynar (duration_hm'e yazılır).
        off_jitter = (((day_index * 2) % 5) - 2) * 5  # -10,-5,0,+5,+10
        off = base + timedelta(days=day_index, hours=9, minutes=off_jitter)
        on_minutes = int((off - on).total_seconds() // 60)

        session.add(
            BehaviorLog(
                user_id=user_id, device_id=lamp_id, action="TurnOn",
                event_time=on, parameters=f"phase={phase}",
            )
        )
        session.add(
            BehaviorLog(
                user_id=user_id, device_id=lamp_id, action="TurnOff",
                event_time=off, duration_hm=(off - on),
                parameters=f"phase={phase}; on_dur_min={on_minutes}",
            )
        )
        n_on += 1
        n_off += 1
    session.commit()
    print(
        f"Yazilan log: TurnOn={n_on}, TurnOff={n_off} (Evre1=9, Evre2=3, Evre3=0)\n"
        f"  - ACMA  ~07:00 ±10 dk  (alaskanlik @07)\n"
        f"  - KAPATMA ~09:00 ±10 dk (alaskanlik @09)\n"
        f"  - yanma suresi ~2 saat (off-on) -> duration_hm"
    )
    return today


def _lamp_active_dates(session: Session, lamp_id: int, upto: datetime) -> set[date]:
    rows = session.exec(
        select(BehaviorLog).where(
            BehaviorLog.device_id == lamp_id, BehaviorLog.event_time <= upto
        )
    ).all()
    return {r.event_time.date() for r in rows}


def report(session: Session, user_id: str, lamp_id: int, today: datetime) -> None:
    base = today - timedelta(days=3 * PHASE_DAYS - 1)
    checkpoints = [
        ("Evre 1 sonu (gun 10, 9/10)", PHASE_DAYS - 1),
        ("Evre 2 sonu (gun 20, 3/10)", 2 * PHASE_DAYS - 1),
        ("Evre 3 sonu (gun 30, 0/10)", 3 * PHASE_DAYS - 1),
    ]

    print("\n" + "=" * 70)
    print("RECENCY-AGIRLIKLI RUTIN OLASILIGI  P(sabah lambayi acma)   λ=0.0077")
    print("=" * 70)
    for label, end_day in checkpoints:
        ref = base + timedelta(days=end_day, hours=23, minutes=59)
        active = _lamp_active_dates(session, lamp_id, ref)
        prob = _recency_weighted_active_ratio(active, today=ref.date())
        if prob >= _DEVICE_HABIT_ENTER_THRESHOLD:
            verdict = "HABIT AKTIF"
        elif prob >= _DEVICE_HABIT_EXIT_THRESHOLD:
            verdict = "zayifliyor (histerezis: aktif kalir)"
        else:
            verdict = "UNUTULDU (<%45 -> pasiflesir)"
        # detect_device_routines'i bu referans zamaniyla calistirip Habit'e yaz
        detect_device_routines(session, reference_time=ref)

        def _hstate(action_label: str) -> str:
            h = session.exec(
                select(Habit).where(
                    Habit.user_id == user_id,
                    Habit.name.like(
                        f"{_DEVICE_ROUTINE_PREFIX}{LAMP_NAME} {action_label}%"
                    ),
                )
            ).first()
            return (
                f"score={float(h.probability_score):.2f} active={h.is_active}"
                if h
                else "(henuz olusmadi)"
            )

        print(f"{label}: P = {prob*100:5.1f}%  -> {verdict}")
        print(f"    Acma    (Turnon  @07): {_hstate('Turnon')}")
        print(f"    Kapatma (Turnoff @09): {_hstate('Turnoff')}")
    print("=" * 70)


def main() -> None:
    with Session(engine) as session:
        user_id = _find_user_id(session)
        env_id = _ensure_environment(session, user_id)
        _cleanup_old_motion(session, env_id)
        lamp_id = _ensure_lamp(session, env_id)
        session.commit()

        # Eski rutin habit'lerini temizle (taze kurulacak; önceki denemelerden
        # kalan @10 gibi bayat satırlar raporu şaşırtmasın).
        session.exec(
            text(
                "DELETE FROM habits WHERE user_id = :u AND name LIKE :n"
            ).bindparams(u=user_id, n=f"{_DEVICE_ROUTINE_PREFIX}{LAMP_NAME}%")
        )
        session.commit()

        print(f"user_id={user_id}  env_id={env_id}  lamp_id={lamp_id}")
        today = seed_logs(session, user_id, lamp_id)
        report(session, user_id, lamp_id, today)

        print("\nSQL ile inceleme:")
        print("-" * 70)
        print(
            "-- Tum lamba loglari (on/off + sure + evre):\n"
            f"SELECT bl.id, d.name AS device, bl.action, bl.event_time,\n"
            f"       bl.duration_hm, bl.parameters\n"
            f"FROM behavior_logs bl JOIN devices d ON d.id = bl.device_id\n"
            f"WHERE bl.device_id = {lamp_id} ORDER BY bl.event_time;\n"
        )
        print(
            "-- Evre bazinda gun sayisi:\n"
            f"SELECT parameters AS evre, COUNT(*) AS gun\n"
            f"FROM behavior_logs WHERE device_id = {lamp_id}\n"
            f"GROUP BY parameters ORDER BY evre;\n"
        )
        print(
            "-- Olusan rutin habit:\n"
            f"SELECT name, probability_score, is_active FROM habits\n"
            f"WHERE user_id = '{user_id}' AND name LIKE 'Routine: {LAMP_NAME}%';"
        )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlmodel import Session, select

from app.core.models import BehaviorLog, Device, User
from app.db.database import engine


@dataclass(frozen=True)
class Persona:
    name: str
    age: int
    city: str
    chronotype: str
    user_id: str


PERSONAS: list[Persona] = [
    Persona("Izmir Student", 20, "Izmir", "night_owl", "P9000001"),
    Persona("Erzurum Officer", 45, "Erzurum", "early_bird", "P9000002"),
]


def _noise_minutes(base: datetime, jitter: int = 10) -> datetime:
    return base + timedelta(minutes=random.randint(-jitter, jitter))


def _mk_log(user_id: str, device_name: str, action: str, event_time: datetime, parameters: str | None = None) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "device_name": device_name,
        "action": action,
        "event_time": event_time,
        "parameters": parameters,
    }


def _daily_routine(persona: Persona, day: datetime) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    if persona.chronotype == "night_owl":
        wake = day.replace(hour=10, minute=0, second=0, microsecond=0)
        arrive = day.replace(hour=19, minute=0, second=0, microsecond=0)
        sleep = day.replace(hour=1, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        wake = day.replace(hour=6, minute=30, second=0, microsecond=0)
        arrive = day.replace(hour=17, minute=30, second=0, microsecond=0)
        sleep = day.replace(hour=22, minute=30, second=0, microsecond=0)

    # morning routine
    logs.append(_mk_log(persona.user_id, "LIGHT", "ON", _noise_minutes(wake)))
    logs.append(_mk_log(persona.user_id, "LIGHT", "OFF", _noise_minutes(wake + timedelta(minutes=35))))

    # evening home routine
    logs.append(_mk_log(persona.user_id, "LIGHT", "ON", _noise_minutes(arrive)))

    # seasonal HVAC behavior
    month = day.month
    if month in {11, 12, 1, 2, 3}:
        logs.append(_mk_log(persona.user_id, "HEATER", "ON", _noise_minutes(arrive + timedelta(minutes=5))))
        logs.append(_mk_log(persona.user_id, "HEATER", "OFF", _noise_minutes(arrive + timedelta(hours=2))))
    elif month in {4, 5, 6, 7, 8, 9}:
        logs.append(_mk_log(persona.user_id, "AC", "ON", _noise_minutes(arrive + timedelta(minutes=5))))
        logs.append(_mk_log(persona.user_id, "AC", "OFF", _noise_minutes(arrive + timedelta(hours=2))))

    logs.append(_mk_log(persona.user_id, "LIGHT", "OFF", _noise_minutes(sleep)))
    return logs


def _inject_anomalies(day: datetime, personas: list[Persona], anomaly_rate: float = 0.04) -> list[dict[str, Any]]:
    if random.random() > anomaly_rate:
        return []
    p = random.choice(personas)
    out: list[dict[str, Any]] = []
    # Safety anomaly: oven long ON
    start = day.replace(hour=18, minute=20, second=0, microsecond=0)
    out.append(_mk_log(p.user_id, "OVEN", "ON", start, "anomaly_seed"))
    out.append(_mk_log(p.user_id, "OVEN", "OFF", start + timedelta(hours=2, minutes=10), "anomaly_seed"))

    # Strange night light burst
    burst = day.replace(hour=3, minute=0, second=0, microsecond=0)
    out.append(_mk_log(p.user_id, "LIGHT", "ON", burst, "night_burst"))
    out.append(_mk_log(p.user_id, "LIGHT", "OFF", burst + timedelta(minutes=7), "night_burst"))
    return out


def generate_synthetic_behavior_logs(
    *,
    start_date: str = "2025-01-01",
    end_date: str = "2025-12-31",
    anomaly_rate: float = 0.04,
    seed: int = 42,
) -> pd.DataFrame:
    random.seed(seed)
    start = pd.to_datetime(start_date).to_pydatetime()
    end = pd.to_datetime(end_date).to_pydatetime()
    days = pd.date_range(start=start.date(), end=end.date(), freq="D")

    rows: list[dict[str, Any]] = []
    for day_ts in days:
        day = day_ts.to_pydatetime()
        for persona in PERSONAS:
            rows.extend(_daily_routine(persona, day))
        rows.extend(_inject_anomalies(day, PERSONAS, anomaly_rate=anomaly_rate))

    df = pd.DataFrame(rows).sort_values("event_time").reset_index(drop=True)
    return df


def export_synthetic_csv(output_path: str | Path, **kwargs: Any) -> Path:
    out = Path(output_path)
    df = generate_synthetic_behavior_logs(**kwargs)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return out


def insert_synthetic_into_db(df: pd.DataFrame) -> int:
    with Session(engine) as session:
        users = {u.id for u in session.exec(select(User)).all() if u.id}
        # Use first matching named device per environment constraints if available; fallback by name map.
        devices = list(session.exec(select(Device)).all())
        dev_map: dict[str, int] = {}
        for d in devices:
            key = (d.name or str(d.type)).upper()
            if key not in dev_map:
                dev_map[key] = int(d.id)

        inserted = 0
        for _, r in df.iterrows():
            uid = str(r["user_id"])
            if uid not in users:
                continue
            dev_name = str(r["device_name"]).upper()
            did = dev_map.get(dev_name)
            if did is None:
                continue
            log = BehaviorLog(
                user_id=uid,
                device_id=did,
                action=str(r["action"]),
                event_time=pd.to_datetime(r["event_time"]).to_pydatetime(),
                parameters=str(r["parameters"]) if pd.notna(r.get("parameters")) else None,
            )
            session.add(log)
            inserted += 1
        session.commit()
    return inserted


def _cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Synthetic behavior log generator")
    p.add_argument("--start-date", default="2025-01-01")
    p.add_argument("--end-date", default="2025-12-31")
    p.add_argument("--anomaly-rate", type=float, default=0.04)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", type=Path, default=Path("data/synthetic_behavior_logs.csv"))
    p.add_argument("--to-db", action="store_true", help="Insert generated logs into BehaviorLog table")
    return p


def main() -> None:
    args = _cli().parse_args()
    df = generate_synthetic_behavior_logs(
        start_date=args.start_date,
        end_date=args.end_date,
        anomaly_rate=args.anomaly_rate,
        seed=args.seed,
    )
    out = export_synthetic_csv(
        args.output,
        start_date=args.start_date,
        end_date=args.end_date,
        anomaly_rate=args.anomaly_rate,
        seed=args.seed,
    )
    print(f"Synthetic CSV created: {out} rows={len(df)}")
    if args.to_db:
        inserted = insert_synthetic_into_db(df)
        print(f"Inserted into DB: {inserted} rows")


if __name__ == "__main__":
    main()


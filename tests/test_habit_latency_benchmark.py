from __future__ import annotations

import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlmodel import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analytics.decision_engine import resolve_sequence_candidates
from app.analytics.sequence_miner import mine_habit_sequences
from app.models.habit_matrix import HabitMatrix

BENCHMARK_ITERATIONS = 50
LOG_COUNT = 400


def _synthetic_behavior_logs(n: int = LOG_COUNT) -> list[dict]:
    rows: list[dict] = []
    base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    devices = ["SALON_LAMBA", "KLIMA", "TV"]
    actions = ["ON", "OFF"]
    for i in range(n):
        dev = devices[i % len(devices)]
        act = actions[i % 2]
        rows.append(
            {
                "user_id": "P0000001",
                "device_name": dev,
                "action": act,
                "event_time": base + timedelta(minutes=i * 7),
            }
        )
    return rows


def _median_ms(samples_sec: list[float]) -> float:
    return statistics.median(samples_sec) * 1000.0


def _p95_ms(samples_sec: list[float]) -> float:
    if len(samples_sec) < 2:
        return samples_sec[0] * 1000.0
    ordered = sorted(samples_sec)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[idx] * 1000.0


def benchmark_runtime_mining(logs: list[dict], iterations: int = BENCHMARK_ITERATIONS) -> dict[str, float]:
    mined = mine_habit_sequences(pd.DataFrame(logs))
    if not mined:
        raise RuntimeError("Benchmark icin sequence kurali uretilemedi.")
    trigger_token = str(mined[0].get("trigger", ""))
    ctx_raw = str(mined[0].get("context", ""))
    event_time = "2026-04-29 21:00:00" if ctx_raw.lower() in {"night", "evening"} else "2026-04-29 11:00:00"
    if "_" in trigger_token:
        device_part, action_part = trigger_token.rsplit("_", 1)
    else:
        device_part, action_part = trigger_token, "ON"

    trigger_event = {
        "user_id": "P0000001",
        "device_id": device_part,
        "action": action_part,
        "event_time": event_time,
        "history_log_count": len(logs),
        "behavior_logs": logs,
    }
    samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        out = resolve_sequence_candidates(trigger_event, session=None)
        samples.append(time.perf_counter() - t0)
        assert out  # runtime path uretmeli
    return {"median_ms": _median_ms(samples), "p95_ms": _p95_ms(samples), "candidates": len(out)}


def benchmark_habit_matrix_read(sqlite_session: Session, logs: list[dict], iterations: int = BENCHMARK_ITERATIONS) -> dict[str, float]:
    mined = mine_habit_sequences(pd.DataFrame(logs))
    if not mined:
        raise RuntimeError("Benchmark icin sequence kurali uretilemedi.")
    lead = mined[0]
    trigger_token = str(lead.get("trigger", ""))
    ctx_raw = str(lead.get("context", ""))
    matrix_ctx = "Night" if ctx_raw.lower() in {"night", "evening"} else "Day"
    event_time = "2026-04-29 21:00:00" if matrix_ctx == "Night" else "2026-04-29 11:00:00"

    now = datetime.now(UTC)
    for rule in mined[:12]:
        sqlite_session.add(
            HabitMatrix(
                user_id="P0000001",
                trigger_event=str(rule.get("trigger", "")),
                target_event=str(rule.get("target", "")),
                context="Night" if str(rule.get("context", "")).lower() in {"night", "evening"} else "Day",
                probability=float(rule.get("probability", rule.get("confidence", 0.5))),
                last_updated=now,
            )
        )
    sqlite_session.commit()

    if "_" in trigger_token:
        device_part, action_part = trigger_token.rsplit("_", 1)
    else:
        device_part, action_part = trigger_token, "ON"

    trigger_event = {
        "user_id": "P0000001",
        "device_id": device_part,
        "action": action_part,
        "event_time": event_time,
        "history_log_count": len(logs),
    }
    samples: list[float] = []
    last_out: list[dict] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        last_out = resolve_sequence_candidates(trigger_event, session=sqlite_session)
        samples.append(time.perf_counter() - t0)
    assert last_out
    assert all(c.get("source") == "MATRIX" for c in last_out)
    return {"median_ms": _median_ms(samples), "p95_ms": _p95_ms(samples), "candidates": len(last_out)}


@pytest.fixture(scope="module")
def latency_comparison() -> dict[str, dict[str, float]]:
    logs = _synthetic_behavior_logs()
    runtime = benchmark_runtime_mining(logs)
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, create_engine

    import app.core.models  # noqa: F401
    from app.models.habit_matrix import HabitMatrix  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        matrix = benchmark_habit_matrix_read(session, logs)
    speedup = runtime["median_ms"] / matrix["median_ms"] if matrix["median_ms"] > 0 else 0.0
    return {"runtime": runtime, "matrix": matrix, "speedup_median_x": speedup}


def test_runtime_mining_produces_candidates(latency_comparison: dict):
    assert latency_comparison["runtime"]["candidates"] >= 1


def test_matrix_read_uses_matrix_source(latency_comparison: dict):
    assert latency_comparison["matrix"]["candidates"] >= 1


def test_matrix_read_faster_than_runtime_mining(latency_comparison: dict):
    assert latency_comparison["matrix"]["median_ms"] < latency_comparison["runtime"]["median_ms"]

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
from sqlmodel import Session, select

from app.analytics.cold_start_engine import EngineConfig, run_cold_start_engine
from app.analytics.sequence_miner import mine_habit_sequences
from app.analytics.time_utils import encode_time_cyclic
from app.core.settings import settings
from app.models.habit_matrix import HabitMatrix

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DecisionEngineConfig:
    cold_data_path: Path = Path("app/analytics/processed_synapse_data.csv")
    min_notification_confidence: float = 0.50
    high_confidence_threshold: float = 0.80
    sequence_max_weight: float = 0.85
    sequence_weight_full_at_logs: int = 50
    day_light_block: bool = True
    blocked_day_targets: tuple[str, ...] = ("LIGHT_ON", "LAMBA_ON")
    cold_engine_config: EngineConfig = field(default_factory=EngineConfig)
    mature_sequence_min_logs: int = 10
    mature_seq_weight: float = 0.80
    mature_cold_weight: float = 0.20
    sunrise_hour: int = settings.sunrise_hour
    sunset_hour: int = settings.sunset_hour
    pre_sunset_light_penalty: float = settings.pre_sunset_light_penalty


def _normalize_token(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace(" ", "_")


def _build_trigger_token(trigger_event: dict[str, Any]) -> str:
    if trigger_event.get("trigger"):
        return _normalize_token(trigger_event["trigger"])
    device = _normalize_token(trigger_event.get("device") or trigger_event.get("device_id"))
    action = _normalize_token(trigger_event.get("action"))
    if device and action:
        return f"{device}_{action}"
    return ""


def _parse_now_hms(trigger_event: dict[str, Any]) -> str:
    now_raw = (
        trigger_event.get("current_time")
        or trigger_event.get("event_time")
        or trigger_event.get("timestamp")
    )
    if isinstance(now_raw, datetime):
        return now_raw.strftime("%H:%M:%S")
    if isinstance(now_raw, str) and now_raw.strip():
        dt = pd.to_datetime(now_raw, errors="coerce")
        if pd.notna(dt):
            return dt.strftime("%H:%M:%S")
    return datetime.now().strftime("%H:%M:%S")


def _parse_now_dt(trigger_event: dict[str, Any]) -> datetime:
    now_raw = (
        trigger_event.get("current_time")
        or trigger_event.get("event_time")
        or trigger_event.get("timestamp")
    )
    if isinstance(now_raw, datetime):
        return now_raw
    if isinstance(now_raw, str) and now_raw.strip():
        dt = pd.to_datetime(now_raw, errors="coerce")
        if pd.notna(dt):
            return dt.to_pydatetime()
    return datetime.now()


def _time_period_from_cyclic(hms: str) -> tuple[str, str]:
    tmp = pd.DataFrame({"event_time_hms": [hms]})
    cyc = encode_time_cyclic(tmp, "event_time_hms", output_prefix="event_time")
    sin_v = float(cyc.loc[0, "event_time_sin"])
    cos_v = float(cyc.loc[0, "event_time_cos"])
    period = "Day" if sin_v > 0 else "Night"
    if sin_v > 0.5 and cos_v > 0.5:
        context = "Morning"
    elif sin_v > 0.5 and cos_v <= 0.5:
        context = "Afternoon"
    elif sin_v < -0.5 and cos_v < -0.5:
        context = "Evening"
    elif sin_v < -0.5 and cos_v >= -0.5:
        context = "Night"
    else:
        context = "Transition"
    return period, context


def _context_to_day_night(context: str) -> str:
    c = str(context).strip().lower()
    if c in {"night", "evening"}:
        return "Night"
    return "Day"


def _sequence_candidates(
    trigger_token: str,
    context: str,
    trigger_event: dict[str, Any],
    session: Session | None,
) -> list[dict[str, Any]]:
    user_id = trigger_event.get("user_id")
    day_night_context = _context_to_day_night(context)
    if session is not None and user_id:
        rows = list(
            session.exec(
                select(HabitMatrix)
                .where(
                    HabitMatrix.user_id == str(user_id),
                    HabitMatrix.trigger_event == trigger_token,
                    HabitMatrix.context == day_night_context,
                )
                .order_by(HabitMatrix.probability.desc())
            )
        )
        if rows:
            return [
                {"target": _normalize_token(r.target_event), "confidence": float(r.probability), "source": "MATRIX"}
                for r in rows
            ]

    rules = trigger_event.get("sequence_rules")
    if rules is None:
        logs = trigger_event.get("behavior_logs", [])
        if not logs:
            return []
        rules = mine_habit_sequences(pd.DataFrame(logs))
    candidates = [
        r
        for r in rules
        if _normalize_token(r.get("trigger")) == trigger_token and str(r.get("context")) == context
    ]
    if not candidates:
        candidates = [r for r in rules if _normalize_token(r.get("trigger")) == trigger_token]
    return [
        {"target": _normalize_token(c.get("target")), "confidence": float(c.get("confidence", 0.0)), "source": "RUNTIME"}
        for c in candidates
    ]


def _cold_signal(candidate_target: str | None, trigger_event: dict[str, Any], config: DecisionEngineConfig) -> float:
    direct = trigger_event.get("cold_start_confidence")
    if direct is not None:
        return float(direct)
    user_profile = trigger_event.get("user_profile")
    if not user_profile or not config.cold_data_path.is_file():
        return 0.0
    payload = {
        "age": float(user_profile["age"]),
        "gender": user_profile["gender"],
        "city": user_profile["city"],
        "bmi": float(
            user_profile.get("bmi", float(user_profile["weight"]) / ((float(user_profile["height"]) / 100.0) ** 2))
        ),
    }
    res = run_cold_start_engine(config.cold_data_path, payload, config.cold_engine_config)
    catalog = res["startup_catalog"]
    if candidate_target and "LIGHT" in candidate_target:
        light_candidates = [float(v[0]["share"]) for k, v in catalog.items() if "ışık" in k.lower() or "isik" in k.lower()]
        if light_candidates:
            return max(light_candidates)
    return max((float(v[0]["share"]) for v in catalog.values() if v), default=0.0)


def _apply_context_penalty(
    target: str,
    score: float,
    now_dt: datetime,
    config: DecisionEngineConfig,
) -> float:
    """
    Gun dogumu/gun batimi bazli context guard:
    gun batimindan once lamba onerilerinin skorunu dusur.
    """
    t = _normalize_token(target)
    if "LIGHT" not in t and "LAMBA" not in t:
        return score
    cur_t = now_dt.time()
    sunrise_t = time(hour=max(0, min(23, config.sunrise_hour)))
    sunset_t = time(hour=max(0, min(23, config.sunset_hour)))
    if sunrise_t <= cur_t < sunset_t:
        return score * config.pre_sunset_light_penalty
    return score


def _process_decision_impl(
    trigger_event: dict[str, Any],
    config: DecisionEngineConfig = DecisionEngineConfig(),
    session: Session | None = None,
) -> dict[str, Any] | None:
    trigger_token = _build_trigger_token(trigger_event)
    if not trigger_token:
        return None
    now_hms = _parse_now_hms(trigger_event)
    now_dt = _parse_now_dt(trigger_event)
    period, context = _time_period_from_cyclic(now_hms)
    seq_candidates = _sequence_candidates(trigger_token, context, trigger_event, session)
    history_log_count = int(trigger_event.get("history_log_count", 0))
    mature = history_log_count > config.mature_sequence_min_logs
    if mature:
        seq_w, cold_w = config.mature_seq_weight, config.mature_cold_weight
    else:
        seq_w = min(config.sequence_max_weight, max(0.0, float(history_log_count)) / float(config.sequence_weight_full_at_logs) * config.sequence_max_weight)
        cold_w = 1.0 - seq_w

    ranked: list[dict[str, Any]] = []
    for cand in seq_candidates:
        target = cand["target"]
        seq_conf = float(cand["confidence"])
        cold_conf = _cold_signal(target, trigger_event, config)
        final = seq_w * seq_conf + cold_w * cold_conf
        final = _apply_context_penalty(target, final, now_dt, config)
        ranked.append(
            {
                "target": target,
                "sequence_confidence": round(seq_conf, 4),
                "cold_start_confidence": round(cold_conf, 4),
                "final_confidence": round(final, 4),
                "source": cand["source"],
            }
        )
    if not ranked:
        cold_only = _cold_signal(None, trigger_event, config)
        if cold_only <= 0:
            return None
        ranked.append({"target": _normalize_token(trigger_event.get("fallback_target") or "LIGHT_ON"), "sequence_confidence": 0.0, "cold_start_confidence": round(cold_only, 4), "final_confidence": round(cold_only, 4), "source": "COLD_START"})

    blocked = {_normalize_token(x) for x in config.blocked_day_targets}
    filtered = [r for r in ranked if not (config.day_light_block and period == "Day" and _normalize_token(r["target"]) in blocked) and r["final_confidence"] >= config.min_notification_confidence]
    if not filtered:
        return None
    filtered = sorted(filtered, key=lambda x: -float(x["final_confidence"]))
    conflict_groups = [{"LIGHT_ON", "NIGHT_MODE_ON"}, {"LAMBA_ON", "NIGHT_MODE_ON"}]
    resolved: list[dict[str, Any]] = []
    for cand in filtered:
        t = _normalize_token(cand["target"])
        if any(any(t in grp and _normalize_token(x["target"]) in grp for grp in conflict_groups) for x in resolved):
            continue
        resolved.append(cand)
    if not resolved:
        return None

    top = resolved[0]
    top_conf = float(top["final_confidence"])
    notif_type = "HIGH_CONFIDENCE" if top_conf > config.high_confidence_threshold else "SUGGESTION"
    return {
        "type": notif_type,
        "trigger": trigger_token,
        "target": top["target"],
        "context": context,
        "final_confidence": round(top_conf, 4),
        "confidence_score": round(top_conf, 4),
        "message": f"Trigger {trigger_token} icin {top['target']} onerisi ({notif_type}).",
        "recommendations": resolved,
        "components": {
            "sequence_confidence": top["sequence_confidence"],
            "cold_start_confidence": top["cold_start_confidence"],
            "sequence_weight": round(seq_w, 4),
            "cold_weight": round(cold_w, 4),
            "history_log_count": history_log_count,
            "mature_sequence_mode": mature,
        },
    }


def resolve_sequence_candidates(
    trigger_event: dict[str, Any],
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """
    Habit Engine adaylarini cozer: oncelikle Habit Matrix (session), yoksa canli sequence mining.
    Benchmark ve testler icin public yuzey.
    """
    trigger_token = _build_trigger_token(trigger_event)
    if not trigger_token:
        return []
    now_hms = _parse_now_hms(trigger_event)
    _, context = _time_period_from_cyclic(now_hms)
    return _sequence_candidates(trigger_token, context, trigger_event, session)


def process_decision_sync(
    trigger_event: dict[str, Any],
    config: DecisionEngineConfig = DecisionEngineConfig(),
    session: Session | None = None,
) -> dict[str, Any] | None:
    return _process_decision_impl(trigger_event, config, session=session)


async def process_decision(
    trigger_event: dict[str, Any],
    config: DecisionEngineConfig = DecisionEngineConfig(),
    session: Session | None = None,
) -> dict[str, Any] | None:
    return _process_decision_impl(trigger_event, config, session=session)


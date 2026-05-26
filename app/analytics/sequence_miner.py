from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.analytics.time_utils import encode_time_cyclic
from app.core.settings import settings


@dataclass(frozen=True)
class SequenceRule:
    trigger: str
    target: str
    probability: float
    confidence: float
    context: str


@dataclass(frozen=True)
class SequenceMinerConfig:
    window_minutes: int = 15
    min_confidence: float = 0.50
    min_support: int = 2
    decay_lambda: float = settings.sequence_decay_lambda
    reference_time: datetime | None = None


def _context_from_cyclic(sin_v: float, cos_v: float) -> str:
    """
    Sin/Cos esiklerine gore zaman torbasi.

    - sin > 0.5  : gunun bir yarisi
    - sin < -0.5 : diger yarisi
    - aksi        : gecis bolgesi
    """
    if sin_v > 0.5:
        sin_bin = "high"
    elif sin_v < -0.5:
        sin_bin = "low"
    else:
        sin_bin = "mid"

    if cos_v > 0.5:
        cos_bin = "high"
    elif cos_v < -0.5:
        cos_bin = "low"
    else:
        cos_bin = "mid"

    # Daha insan okunur baglam etiketi (sin/cos tabanli)
    if sin_bin == "high" and cos_bin == "high":
        return "Morning"
    if sin_bin == "high" and cos_bin == "low":
        return "Afternoon"
    if sin_bin == "low" and cos_bin == "low":
        return "Evening"
    if sin_bin == "low" and cos_bin == "high":
        return "Night"
    return "Transition"


def _event_token(device_key: str, action: str) -> str:
    d = str(device_key).strip().upper().replace(" ", "_")
    a = str(action).strip().upper().replace(" ", "_")
    return f"{d}_{a}"


def _ensure_time_features(df: pd.DataFrame, event_col: str = "event_time") -> pd.DataFrame:
    out = df.copy()
    out[event_col] = pd.to_datetime(out[event_col], errors="coerce")
    out = out.dropna(subset=[event_col])
    out["event_time_hms"] = out[event_col].dt.strftime("%H:%M:%S")
    out = encode_time_cyclic(out, "event_time_hms", output_prefix="event_time")
    out["time_context"] = out.apply(
        lambda r: _context_from_cyclic(float(r["event_time_sin"]), float(r["event_time_cos"])),
        axis=1,
    )
    return out


def _resolve_device_col(df: pd.DataFrame) -> str:
    for candidate in ("device_name", "device", "device_label", "name"):
        if candidate in df.columns:
            return candidate
    if "device_id" in df.columns:
        return "device_id"
    raise KeyError("Behavior log icin cihaz kolonu bulunamadi (beklenen: device_id/device_name).")


def _normalize_logs(logs_df: pd.DataFrame) -> pd.DataFrame:
    required = {"action", "event_time"}
    missing = required - set(logs_df.columns)
    if missing:
        raise KeyError(f"Eksik davranis kolonu/kolonlari: {sorted(missing)}")

    out = logs_df.copy()
    out = _ensure_time_features(out, "event_time")
    out["action"] = out["action"].astype(str).str.strip().str.upper()
    dev_col = _resolve_device_col(out)
    out["device_key"] = out[dev_col].astype(str).str.strip()
    if "user_id" not in out.columns:
        out["user_id"] = "GLOBAL_USER"
    out = out.sort_values(["user_id", "event_time"]).reset_index(drop=True)
    return out


def mine_habit_sequences(
    logs_df: pd.DataFrame,
    config: SequenceMinerConfig = SequenceMinerConfig(),
) -> list[dict[str, Any]]:
    """
    Sliding-window ile A->B gecis olasiligini P(B|A) olarak hesaplar.

    - P(B|A) = support(A->B) / trigger_count(A)
    - support: A olduktan sonraki ``window_minutes`` icinde B en az bir kez olusmasi.
    - zaman baglami ``time_context`` + event_time_sin/cos ile ayrilir.
    """
    df = _normalize_logs(logs_df)
    window = pd.Timedelta(minutes=config.window_minutes)

    # P(B|A) icin payda: trigger olaylari (agirlikli)
    trigger_weights: dict[tuple[str, str], float] = {}
    # P(B|A) payi: A olduktan sonra pencere icinde B gorulme adedi
    support_counts: dict[tuple[str, str, str], int] = {}
    # Time-weighted confidence: A'ya yakin B daha agirlikli
    weighted_support_sums: dict[tuple[str, str, str], float] = {}

    for _, grp in df.groupby("user_id", sort=False):
        n = len(grp)
        rows = grp.reset_index(drop=True)
        ref_time_ts = pd.Timestamp(
            config.reference_time or datetime.now(UTC).replace(tzinfo=None)
        )
        for i in range(n):
            trigger = rows.iloc[i]
            trigger_token = _event_token(trigger["device_key"], trigger["action"])
            trig_ctx_key = (trigger_token, trigger["time_context"])
            trigger_ts = pd.Timestamp(trigger["event_time"])
            if trigger_ts.tzinfo is not None and ref_time_ts.tzinfo is None:
                ref_time_ts = ref_time_ts.tz_localize(trigger_ts.tzinfo)
            if trigger_ts.tzinfo is None and ref_time_ts.tzinfo is not None:
                trigger_ts = trigger_ts.tz_localize(ref_time_ts.tzinfo)
            delta_days = max(0.0, (ref_time_ts - trigger_ts).total_seconds() / 86400.0)
            recency_weight = math.exp(-config.decay_lambda * delta_days)
            trigger_weights[trig_ctx_key] = trigger_weights.get(trig_ctx_key, 0.0) + recency_weight

            # Ayni A olayi icin ayni hedef B bir kez sayilir (P(B|A) klasik yorumu)
            best_weight_per_target: dict[str, float] = {}
            t0 = trigger["event_time"]
            j = i + 1
            while j < n:
                target = rows.iloc[j]
                dt = target["event_time"] - t0
                if dt <= pd.Timedelta(0):
                    j += 1
                    continue
                if dt > window:
                    break
                target_token = _event_token(target["device_key"], target["action"])
                # 0-1 arasi yakinlik agirligi: 2.dk > 14.dk
                ratio = dt.total_seconds() / window.total_seconds()
                time_weight = max(0.0, 1.0 - ratio)
                weight = recency_weight * time_weight
                prev = best_weight_per_target.get(target_token)
                if prev is None or weight > prev:
                    best_weight_per_target[target_token] = weight
                j += 1

            for target_token, best_weight in best_weight_per_target.items():
                pair_key = (trigger_token, target_token, trigger["time_context"])
                support_counts[pair_key] = support_counts.get(pair_key, 0) + 1
                weighted_support_sums[pair_key] = (
                    weighted_support_sums.get(pair_key, 0.0) + best_weight
                )

    rules: list[SequenceRule] = []
    for (trigger_token, target_token, ctx), support in support_counts.items():
        trig_weight = trigger_weights.get((trigger_token, ctx), 0.0)
        if trig_weight <= 0:
            continue
        weighted_support = weighted_support_sums.get((trigger_token, target_token, ctx), 0.0)
        prob = weighted_support / trig_weight  # agirlikli P(B|A)
        weighted = weighted_support / trig_weight
        if support >= config.min_support and prob > config.min_confidence:
            rules.append(
                SequenceRule(
                    trigger=trigger_token,
                    target=target_token,
                    probability=round(prob, 4),
                    confidence=round(weighted, 4),
                    context=ctx,
                )
            )

    rules = sorted(rules, key=lambda r: (-r.probability, -r.confidence, r.trigger))
    return [
        {
            "trigger": r.trigger,
            "target": r.target,
            "probability": r.probability,
            "confidence": r.confidence,
            "context": r.context,
        }
        for r in rules
    ]


def load_behavior_logs_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def mine_sequences_from_csv(
    path: str | Path,
    config: SequenceMinerConfig = SequenceMinerConfig(),
) -> list[dict[str, Any]]:
    logs = load_behavior_logs_csv(path)
    return mine_habit_sequences(logs, config)


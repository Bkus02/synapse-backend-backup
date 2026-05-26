from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyDetectionConfig:
    k_multiplier: float = 2.0
    min_history_samples: int = 3


def evaluate_duration_anomaly(
    current_minutes: float,
    historical_minutes: list[float],
    *,
    k: float = 2.0,
    min_samples: int = 3,
) -> tuple[bool, float]:
    """
    Kullanim suresinin tarihsel ortalamanin k kati veya uzerinde olup olmadigini degerlendirir.

    Returns:
        (anomaly_detected, average_minutes)
    """
    if current_minutes <= 0 or len(historical_minutes) < min_samples:
        return False, 0.0
    avg = sum(historical_minutes) / len(historical_minutes)
    if avg <= 0:
        return False, avg
    return current_minutes >= k * avg, avg

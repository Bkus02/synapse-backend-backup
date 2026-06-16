"""Cihaz bazli oneriler — demografik peer-matching uzerinden.

Iki tur oneri uretir:

* **Robot supurge kullanim saati** — kullanicinin yas/cinsiyet/sehir/BMI
  bilgisiyle 120+ kisilik anket veri setinde (``processed_synapse_data.csv``)
  en yakin akran grubunu bulur ve o grubun en cok tercih ettigi supurme saati
  / sikligini doner. Cold-start motorunu (``cold_start_engine``) yeniden kullanir.

Lamba parlakligi onerisi tamamen oda bazli oldugu icin frontend tarafinda
hesaplanir (bkz. ``frontend/lib/utils/brightness_advisor.dart``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.analytics.cold_start_engine import (
    EngineConfig,
    build_peer_group,
    load_and_preprocess_data,
)
from app.core.models import User

COLD_START_CSV = Path("app/analytics/processed_synapse_data.csv")

# Anket sutun adlari (processed_synapse_data.csv basliklari ile birebir).
_VACUUM_TIME_COL = "Eviniz genellikle günün hangi saatlerinde süpürülmeli?"
_VACUUM_FREQ_COL = "Günde kaç defa süpürge yapılmasını istersiniz?"


@lru_cache(maxsize=1)
def _load_dataset() -> pd.DataFrame:
    """Anket veri setini bir kez yukleyip on-isler (sonraki cagrilar cache'ten)."""
    return load_and_preprocess_data(COLD_START_CSV)


def _bmi(height_cm: float, weight_kg: float) -> float | None:
    if not height_cm or height_cm <= 0:
        return None
    return float(weight_kg) / ((float(height_cm) / 100.0) ** 2)


def _top_answer(peers: pd.DataFrame, column: str) -> dict[str, Any] | None:
    """Akran grubunda bir sutunun en sik cevabini paylasim oraniyla doner."""
    if column not in peers.columns:
        return None
    series = peers[column].dropna()
    series = series[series.astype(str).str.strip() != ""]
    if series.empty:
        return None
    counts = series.astype(str).value_counts()
    total = float(counts.sum())
    option = str(counts.index[0])
    count = int(counts.iloc[0])
    return {
        "option": option,
        "count": count,
        "share": round(count / total, 3) if total else 0.0,
    }


def recommend_vacuum_schedule(user: User) -> dict[str, Any] | None:
    """Kullanici icin robot supurge saati/sikligi onerisi.

    Profil eksikse (yas/boy/kilo/sehir/cinsiyet) ``None`` doner.
    """
    if (
        user.age is None
        or user.height is None
        or user.weight is None
        or not user.location
        or not user.gender
    ):
        return None

    bmi = _bmi(float(user.height), float(user.weight))
    if bmi is None:
        return None

    if not COLD_START_CSV.is_file():
        return None

    df = _load_dataset()
    profile = {
        "age": float(user.age),
        "gender": user.gender.strip(),
        "city": user.location.strip(),
        "bmi": bmi,
    }
    peers, tier = build_peer_group(df, profile, EngineConfig())
    if peers.empty:
        return None

    time_rec = _top_answer(peers, _VACUUM_TIME_COL)
    freq_rec = _top_answer(peers, _VACUUM_FREQ_COL)
    if time_rec is None and freq_rec is None:
        return None

    return {
        "recommended_time": time_rec["option"] if time_rec else None,
        "time_share": time_rec["share"] if time_rec else None,
        "recommended_frequency": freq_rec["option"] if freq_rec else None,
        "frequency_share": freq_rec["share"] if freq_rec else None,
        "peer_count": int(len(peers)),
        "peer_tier": tier,
    }

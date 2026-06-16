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

import re
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
from app.infrastructure.weather import normalize_city

COLD_START_CSV = Path("app/analytics/processed_synapse_data.csv")

# Anket sutun adlari (processed_synapse_data.csv basliklari ile birebir).
_VACUUM_TIME_COL = "Eviniz genellikle günün hangi saatlerinde süpürülmeli?"
_VACUUM_FREQ_COL = "Günde kaç defa süpürge yapılmasını istersiniz?"
_AC_SUMMER_COL = "Yazın klimanızı genellikle kaç dereceye ayarlarsınız? (Örn: 24)"

_ROOM_LABELS = ("Study Room", "Standard Room", "Rest Room")

# Sehir + oda tipine gore baz AC sicakligi (C).
_CITY_ROOM_TEMPS: dict[str, dict[str, int]] = {
    "izmir": {"Study Room": 24, "Standard Room": 25, "Rest Room": 26},
    "istanbul": {"Study Room": 23, "Standard Room": 24, "Rest Room": 25},
    "ankara": {"Study Room": 26, "Standard Room": 27, "Rest Room": 28},
}


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


def _parse_temp_range(value: str) -> float | None:
    """'22-24' -> 23.0, '24' -> 24.0."""
    nums = [int(x) for x in re.findall(r"\d+", str(value))]
    if not nums:
        return None
    if len(nums) == 1:
        return float(nums[0])
    return (nums[0] + nums[1]) / 2.0


def _normalize_room_label(room: str | None) -> str:
    if not room or not str(room).strip():
        return "Standard Room"
    label = str(room).strip()
    if label in _ROOM_LABELS:
        return label
    lower = label.casefold()
    if any(k in lower for k in ("study", "çalış", "calis", "office", "ofis")):
        return "Study Room"
    if any(k in lower for k in ("rest", "dinlen", "yatak", "bedroom", "sleep")):
        return "Rest Room"
    return "Standard Room"


def _peer_ac_median(user: User, *, city: str | None = None) -> tuple[float | None, int]:
    """Anket akran grubundan yaz klimasi tercihinin orta sicakligini doner."""
    peer_city = (city or user.location or "").strip()
    if (
        user.age is None
        or user.height is None
        or user.weight is None
        or not peer_city
        or not user.gender
        or not COLD_START_CSV.is_file()
    ):
        return None, 0

    bmi = _bmi(float(user.height), float(user.weight))
    if bmi is None:
        return None, 0

    df = _load_dataset()
    profile = {
        "age": float(user.age),
        "gender": user.gender.strip(),
        "city": peer_city,
        "bmi": bmi,
    }
    peers, _tier = build_peer_group(df, profile, EngineConfig())
    if peers.empty or _AC_SUMMER_COL not in peers.columns:
        return None, 0

    values: list[float] = []
    for raw in peers[_AC_SUMMER_COL].dropna().astype(str):
        parsed = _parse_temp_range(raw)
        if parsed is not None:
            values.append(parsed)
    if not values:
        ac_rec = _top_answer(peers, _AC_SUMMER_COL)
        if ac_rec:
            parsed = _parse_temp_range(ac_rec["option"])
            if parsed is not None:
                return parsed, int(len(peers))
        return None, int(len(peers))
    return sum(values) / len(values), int(len(peers))


def recommend_climate_settings(
    user: User, *, city: str | None = None
) -> dict[str, Any] | None:
    """Sehir + oda tipi baz sicakligi; profil varsa anket akranlariyla harmanlar.

  ``city`` verilirse (environment location) kullanici profili yerine o sehir
  baz alinir.
    """
    location = (city or user.location or "").strip()
    if not location:
        return None

    city_key = normalize_city(location)
    table = _CITY_ROOM_TEMPS.get(city_key, _CITY_ROOM_TEMPS["istanbul"])
    peer_mid, peer_count = _peer_ac_median(user, city=location)

    recommendations: dict[str, dict[str, Any]] = {}
    for room in _ROOM_LABELS:
        baseline = table[room]
        entry: dict[str, Any] = {
            "celsius": baseline,
            "baseline_celsius": baseline,
            "source": "city_room",
        }
        if peer_mid is not None:
            entry["peer_median_celsius"] = round(peer_mid)
        recommendations[room] = entry

    return {
        "city": city_key.title(),
        "recommendations": recommendations,
        "peer_count": peer_count,
        "peer_median_celsius": round(peer_mid, 1) if peer_mid is not None else None,
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

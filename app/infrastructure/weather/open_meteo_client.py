"""Open-Meteo client for live weather in the three supported cities.

Open-Meteo is free, key-less, generous. We keep a small in-process cache so
the dashboard can call this every refresh without hammering the API.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


# Limit cold-start to these 3 cities for now (matches register screen).
SUPPORTED_CITIES: dict[str, tuple[float, float]] = {
    "istanbul": (41.0082, 28.9784),
    "ankara": (39.9334, 32.8597),
    "izmir": (38.4237, 27.1428),
}

_DEFAULT_CITY = "istanbul"
_CACHE_TTL_SECONDS = 15 * 60  # 15 min
_API_URL = "https://api.open-meteo.com/v1/forecast"


class UnsupportedCity(ValueError):
    pass


@dataclass(frozen=True)
class WeatherSnapshot:
    city: str
    temperature_c: float
    weather_code: int
    is_day: bool
    condition: str
    summary: str
    tip: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_cache: dict[str, tuple[float, WeatherSnapshot]] = {}


def normalize_city(value: str | None) -> str:
    """Map a free-form location to one of SUPPORTED_CITIES (fallback: Istanbul)."""
    if not value:
        return _DEFAULT_CITY
    key = value.strip().casefold()
    # Strip diacritics for common Turkish spellings.
    key = (
        key.replace("ı", "i")
        .replace("İ", "i")
        .replace("ş", "s")
        .replace("Ş", "s")
        .replace("ç", "c")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ğ", "g")
    )
    for canonical in SUPPORTED_CITIES:
        if canonical in key:
            return canonical
    return _DEFAULT_CITY


def _condition_from_code(code: int, is_day: bool) -> tuple[str, str]:
    """Map a WMO weather code to (condition, plain-English summary)."""
    if code == 0:
        label = "Clear"
        summary = "Clear sky" if is_day else "Clear night"
    elif code in (1, 2):
        label = "Partly cloudy"
        summary = "Mostly clear with some clouds"
    elif code == 3:
        label = "Cloudy"
        summary = "Overcast skies"
    elif code in (45, 48):
        label = "Fog"
        summary = "Foggy"
    elif code in (51, 53, 55, 56, 57):
        label = "Drizzle"
        summary = "Light drizzle"
    elif code in (61, 63, 65):
        label = "Rain"
        summary = "Rainy"
    elif code in (66, 67):
        label = "Freezing rain"
        summary = "Freezing rain"
    elif code in (71, 73, 75, 77):
        label = "Snow"
        summary = "Snowy"
    elif code in (80, 81, 82):
        label = "Rain showers"
        summary = "Rain showers"
    elif code in (85, 86):
        label = "Snow showers"
        summary = "Snow showers"
    elif code in (95, 96, 99):
        label = "Thunderstorm"
        summary = "Thunderstorm"
    else:
        label = "Mild"
        summary = "Mild weather"
    return label, summary


def _tip_for(condition: str, temperature_c: float) -> str:
    """Return a short, English suggestion based on condition + temperature."""
    if condition == "Thunderstorm":
        return "Storm warning — stay indoors if you can."
    if condition in ("Rain", "Drizzle", "Rain showers"):
        return "Rainy — grab an umbrella before heading out."
    if condition == "Freezing rain":
        return "Freezing rain — slippery roads, take it slow."
    if condition in ("Snow", "Snow showers"):
        return "Snowy — warm layers and careful steps."
    if condition == "Fog":
        return "Foggy — drive and walk carefully."
    if temperature_c < 8:
        return "Cold day — grab a jacket and a scarf."
    if condition in ("Clear", "Partly cloudy") and temperature_c >= 28:
        return "Hot and sunny — sunglasses, hat, and plenty of water."
    if condition == "Clear" and 18 <= temperature_c < 28:
        return "Sunny and pleasant — great day for a walk."
    if condition in ("Partly cloudy", "Cloudy"):
        return "Mostly cloudy — a light layer should be enough."
    return "Mild day — perfect for your usual routine."


def _fetch(city: str) -> WeatherSnapshot:
    lat, lon = SUPPORTED_CITIES[city]
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code,is_day,wind_speed_10m",
        "timezone": "auto",
    }
    response = requests.get(_API_URL, params=params, timeout=8)
    response.raise_for_status()
    payload = response.json()
    current = payload.get("current") or {}
    temperature = float(current.get("temperature_2m", 0.0))
    code = int(current.get("weather_code", 0))
    is_day = bool(int(current.get("is_day", 1)))
    condition, summary = _condition_from_code(code, is_day)
    tip = _tip_for(condition, temperature)
    return WeatherSnapshot(
        city=city,
        temperature_c=round(temperature, 1),
        weather_code=code,
        is_day=is_day,
        condition=condition,
        summary=summary,
        tip=tip,
        raw=payload,
    )


def get_current_weather(city: str | None) -> WeatherSnapshot:
    """Fetch (or return cached) current weather for `city`.

    Unknown cities are mapped to Istanbul (the project's default).
    """
    canonical = normalize_city(city)
    if canonical not in SUPPORTED_CITIES:
        raise UnsupportedCity(canonical)

    now = time.monotonic()
    cached = _cache.get(canonical)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        snapshot = _fetch(canonical)
    except Exception:
        logger.exception("Open-Meteo fetch failed for %s", canonical)
        if cached:
            return cached[1]
        raise

    _cache[canonical] = (now, snapshot)
    return snapshot

"""Weather providers for Synapse (Open-Meteo)."""

from app.infrastructure.weather.open_meteo_client import (
    SUPPORTED_CITIES,
    UnsupportedCity,
    WeatherSnapshot,
    get_current_weather,
    normalize_city,
)

__all__ = [
    "SUPPORTED_CITIES",
    "UnsupportedCity",
    "WeatherSnapshot",
    "get_current_weather",
    "normalize_city",
]

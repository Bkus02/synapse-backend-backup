"""
Synapse — merkezi uygulama ayarları.

Tüm ayarlar tek bir `Settings` sınıfından okunur. `.env` dosyası
(`pydantic-settings`) ve ortam değişkenleri otomatik yüklenir.

Kullanım:
    from app.core.settings import settings

    print(settings.database_url)
    print(settings.sunrise_hour)

`@lru_cache` ile tek bir instance paylaşılır; test sırasında
`get_settings.cache_clear()` ile yeniden okunabilir.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tek kaynak konfigürasyon."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Uygulama ---
    app_name: str = "Synapse Backend"
    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Veritabanı ---
    database_url: str = (
        "postgresql://postgres:postgres@localhost:5433/postgres"
    )

    # --- CORS ---
    # Virgülle ayrılmış liste. Boşsa default localhost regex'i kullanılır.
    cors_origins: str = ""

    # --- Decision engine / analytics ---
    sequence_decay_lambda: float = Field(default=0.0077, ge=0.0)
    sunrise_hour: int = Field(default=6, ge=0, le=23)
    sunset_hour: int = Field(default=19, ge=0, le=23)
    pre_sunset_light_penalty: float = Field(default=0.65, ge=0.0, le=1.0)

    # --- Recommendation lifecycle ---
    recommendation_max_age_minutes: int = Field(default=5, ge=1)

    # --- Habit matrix scheduler ---
    habit_matrix_rebuild_hour: int = Field(default=3, ge=0, le=23)

    # --- Auth / JWT (Sprint B) ---
    jwt_secret_key: str = "CHANGE_ME_DEV_SECRET_DO_NOT_USE_IN_PROD"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=60 * 24, ge=1)

    # --- Tuya / Smart Life (cloud lamp) --------------------------------------
    tuya_access_id: str = ""
    tuya_access_secret: str = ""
    tuya_device_id: str = ""
    # EU project: https://openapi.tuyaeu.com | US: https://openapi.tuyaus.com
    tuya_api_endpoint: str = "https://openapi.tuyaeu.com"

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Tek instance — testte `get_settings.cache_clear()` ile sıfırlanır."""
    return Settings()


settings = get_settings()

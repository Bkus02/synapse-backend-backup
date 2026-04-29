"""
PostgreSQL bağlantısı ve SQLModel oturum (session) yönetimi.

Bağlantı adresi örneği:
    postgresql://postgres:ŞİFREN@localhost:5433/postgres

Şifreyi repoya yazma: proje kökünde `.env` içinde `DATABASE_URL` tanımla.
"""

from collections.abc import Generator

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlmodel import Session, create_engine


class _DbSettings(BaseSettings):
    """Uygulama ayarları (.env veya ortam değişkeni)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # .env örneği:
    # DATABASE_URL=postgresql://postgres:ŞİFREN@localhost:5433/postgres
    database_url: str = "postgresql://postgres:postgres@localhost:5433/postgres"


_settings = _DbSettings()

# SQLModel / SQLAlchemy motoru
engine = create_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
)


def get_session() -> Generator[Session, None, None]:
    """
    Veritabanı oturumu jeneratörü (FastAPI `Depends` ile kullanım için uygun).

    Örnek:
        def endpoint(session: Session = Depends(get_session)):
            ...
    """
    with Session(engine) as session:
        yield session

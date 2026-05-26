"""
PostgreSQL bağlantısı ve SQLModel oturum (session) yönetimi.

Bağlantı dizesi `app.core.settings.Settings.database_url` üzerinden okunur.
`.env` örneği:
    DATABASE_URL=postgresql://postgres:ŞİFREN@localhost:5433/postgres
"""

from collections.abc import Generator

from sqlmodel import Session, create_engine

from app.core.settings import settings

# SQLModel / SQLAlchemy motoru
engine = create_engine(
    settings.database_url,
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

from sqlalchemy import text
from sqlmodel import Session

from app.db.database import engine

with Session(engine) as s:
    rows = s.exec(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    ).all()
    for r in rows:
        print(r[0])

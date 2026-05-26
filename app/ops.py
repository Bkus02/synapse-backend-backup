from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlmodel import Session, SQLModel

# `SQLModel.metadata` doluluğu için tüm model modüllerini import et.
import app.core.models  # noqa: F401
import app.models.habit_matrix  # noqa: F401
from app.analytics.synthetic_behavior_generator import (
    export_synthetic_csv,
    generate_synthetic_behavior_logs,
    insert_synthetic_into_db,
)
from app.application.services import smart_home_service
from app.core.logging_config import configure_logging
from app.db.database import engine

configure_logging()
logger = logging.getLogger(__name__)


def apply_sql_migrations(migrations_dir: str | Path = "migrations") -> list[str]:
    """Migration dosyalarını alfabetik sırada uygular.

    Dosya içeriği `psycopg2` raw cursor ile çalıştırılır; bu sayede
    `DO $$ … $$` PL/pgSQL bloklarındaki dolar ayraçları korunur ve
    birden fazla deyim tek `execute` çağrısında geçer.
    """
    mig_path = Path(migrations_dir)
    if not mig_path.is_dir():
        raise FileNotFoundError(f"Migration klasoru bulunamadi: {mig_path}")

    files = sorted(mig_path.glob("*.sql"))
    applied: list[str] = []
    raw = engine.raw_connection()
    try:
        for file in files:
            sql_text = file.read_text(encoding="utf-8")
            if not sql_text.strip():
                continue
            with raw.cursor() as cur:
                cur.execute(sql_text)
            raw.commit()
            logger.info("migration uygulandi: %s", file.name)
            applied.append(file.name)
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
    return applied


def bootstrap_db() -> dict[str, int]:
    """SQLModel metadata'sından tüm tabloları (yoksa) oluşturur.

    SQLite/testte veya hızlı dev ortamında migration sırası yerine
    tek satırla şemayı kurmaya yarar. PG'de migration tercih edilmelidir.
    """
    SQLModel.metadata.create_all(engine)
    tables = list(SQLModel.metadata.tables.keys())
    logger.info("bootstrap-db tamamlandi: %s tablo", len(tables))
    return {"tables_created_or_existing": len(tables)}


def rebuild_habit_matrix() -> dict[str, int]:
    with Session(engine) as session:
        return smart_home_service.rebuild_habit_matrix(session)


def _cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Synapse operasyon komutlari")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("apply-migrations", help="migrations/*.sql dosyalarini sirayla uygula")
    m.add_argument("--dir", default="migrations", help="Migration klasoru")

    sub.add_parser(
        "bootstrap-db",
        help="SQLModel metadata'sindan tablolari olustur (dev/test fallback)",
    )

    sub.add_parser("rebuild-habit-matrix", help="HabitMatrix tablosunu bastan olustur")

    s = sub.add_parser("generate-synthetic-data", help="Synthetic behavior logs uret")
    s.add_argument("--start-date", default="2025-01-01")
    s.add_argument("--end-date", default="2025-12-31")
    s.add_argument("--anomaly-rate", type=float, default=0.04)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--output", default="data/synthetic_behavior_logs.csv")
    s.add_argument("--to-db", action="store_true")
    return p


def main() -> None:
    args = _cli().parse_args()
    if args.cmd == "apply-migrations":
        applied = apply_sql_migrations(args.dir)
        print("Uygulanan migrationlar:")
        for name in applied:
            print(f"- {name}")
        return
    if args.cmd == "bootstrap-db":
        out = bootstrap_db()
        print(
            f"bootstrap-db: {out['tables_created_or_existing']} tablo metadata'da."
        )
        return
    if args.cmd == "rebuild-habit-matrix":
        out = rebuild_habit_matrix()
        print(f"users_processed={out['users_processed']} rules_upserted={out['rules_upserted']}")
        return
    if args.cmd == "generate-synthetic-data":
        df = generate_synthetic_behavior_logs(
            start_date=args.start_date,
            end_date=args.end_date,
            anomaly_rate=args.anomaly_rate,
            seed=args.seed,
        )
        out = export_synthetic_csv(
            args.output,
            start_date=args.start_date,
            end_date=args.end_date,
            anomaly_rate=args.anomaly_rate,
            seed=args.seed,
        )
        print(f"Synthetic CSV created: {out} rows={len(df)}")
        if args.to_db:
            inserted = insert_synthetic_into_db(df)
            print(f"Inserted into DB: {inserted} rows")
        return


if __name__ == "__main__":
    main()


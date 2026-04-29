from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

from app.application.services import smart_home_service
from app.analytics.synthetic_behavior_generator import (
    export_synthetic_csv,
    generate_synthetic_behavior_logs,
    insert_synthetic_into_db,
)
from app.db.database import engine


def apply_sql_migrations(migrations_dir: str | Path = "migrations") -> list[str]:
    mig_path = Path(migrations_dir)
    if not mig_path.is_dir():
        raise FileNotFoundError(f"Migration klasoru bulunamadi: {mig_path}")

    files = sorted(mig_path.glob("*.sql"))
    applied: list[str] = []
    with Session(engine) as session:
        for file in files:
            sql_text = file.read_text(encoding="utf-8")
            if not sql_text.strip():
                continue
            session.exec(text(sql_text))
            session.commit()
            applied.append(file.name)
    return applied


def rebuild_habit_matrix() -> dict[str, int]:
    with Session(engine) as session:
        return smart_home_service.rebuild_habit_matrix(session)


def _cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Synapse operasyon komutlari")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("apply-migrations", help="migrations/*.sql dosyalarini sirayla uygula")
    m.add_argument("--dir", default="migrations", help="Migration klasoru")

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


"""Quick verification of demo seed state."""

import sys

from sqlalchemy import text
from sqlmodel import Session

from app.db.database import engine

# Windows cmd defaults to cp1254 — force UTF-8 so we can print arrows etc.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def main() -> None:
    with Session(engine) as s:
        users = s.exec(
            text(
                "SELECT id, email, age, weight, height "
                "FROM users WHERE email LIKE 'test%@gmail.com' ORDER BY email"
            )
        ).all()
        print(f"\n=== {len(users)} test users ===")
        for u in users:
            print(f"  {u[0]:8s}  {u[1]:25s} age={u[2]}  {u[3]}kg / {u[4]}cm")

        print("\n=== daily streaks ===")
        rows = s.exec(
            text(
                "SELECT u.email, d.current_streak, d.max_streak, d.last_qualifying_date "
                "FROM user_daily_streaks d JOIN users u ON u.id = d.user_id "
                "WHERE u.email LIKE 'test%@gmail.com' "
                "ORDER BY d.current_streak DESC NULLS LAST"
            )
        ).all()
        for r in rows:
            print(
                f"  {r[0]:25s} streak={r[1]:>3}  max={r[2]:>3}  last={r[3]}"
            )

        print("\n=== habits per user (Active Habits card) ===")
        rows = s.exec(
            text(
                "SELECT u.email, h.name, h.probability_score, h.is_active "
                "FROM habits h JOIN users u ON u.id = h.user_id "
                "WHERE u.email LIKE 'test%@gmail.com' "
                "ORDER BY u.email, h.is_active DESC, h.probability_score DESC"
            )
        ).all()
        last = None
        for r in rows:
            email, name, prob, active = r
            if email != last:
                print(f"\n  {email}:")
                last = email
            flag = "[ACTIVE]  " if active else "[inactive]"
            print(f"    {flag}  {prob}  {name}")

        print("\n=== row counts ===")
        for tbl in (
            "behavior_logs",
            "positive_advice_logs",
            "user_daily_streaks",
            "habits",
            "habit_matrix",
            "positive_advices",
        ):
            c = s.exec(text(f"SELECT count(*) FROM {tbl}")).scalar()
            print(f"  {tbl:25s} = {c}")


if __name__ == "__main__":
    main()

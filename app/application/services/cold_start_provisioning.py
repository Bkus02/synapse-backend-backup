from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.analytics.cold_start_engine import ColdStartEngine
from app.core.models import Recommendation, User

COLD_START_CSV = Path("app/analytics/processed_synapse_data.csv")


def _user_profile_for_cold_start(user: User, gender: str) -> dict[str, Any] | None:
    if user.age is None or user.height is None or user.weight is None or not user.location:
        return None
    if not gender.strip():
        return None
    return {
        "age": int(user.age),
        "gender": gender.strip(),
        "city": user.location.strip(),
        "height": int(user.height),
        "weight": int(user.weight),
    }


def provision_cold_start_defaults(
    user: User,
    session: Session,
    *,
    gender: str,
    save_recommendation: Any,
) -> int:
    """
    Yeni kullanici icin demografik peer-group tabanli varsayilan onerileri olusturur.
    save_recommendation: smart_home_service.save_recommendation (dongusel import onleme).
    """
    profile = _user_profile_for_cold_start(user, gender)
    if profile is None:
        return 0
    if not COLD_START_CSV.is_file():
        return 0

    engine = ColdStartEngine(csv_path=COLD_START_CSV)
    catalog = engine.generate_initial_catalog(profile)
    if not catalog:
        return 0

    created = 0
    for question, answer in catalog.items():
        save_recommendation(
            user.id,
            {
                "type": "COLD_START_DEFAULT",
                "trigger": "COLD_START",
                "target": str(answer),
                "context": str(question),
                "final_confidence": 0.55,
            },
            session,
        )
        created += 1
    return created


def list_cold_start_recommendations(user_id: str, session: Session) -> list[Recommendation]:
    rows = list(
        session.exec(
            select(Recommendation).where(
                Recommendation.user_id == user_id,
                Recommendation.recommendation_type == "COLD_START_DEFAULT",
            )
        )
    )
    return rows

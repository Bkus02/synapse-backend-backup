from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import current_user, current_user_id
from app.api.schemas import (
    DailyActivityDay,
    DailyActivityResponse,
    UserCreate,
    UserPublic,
    UserUpdate,
)
from app.application.services import device_recommendation_service, smart_home_service
from app.application.services.recommendation_catalog import (
    describe_profile,
    pick_advices,
)
from app.core.models import User
from app.db.database import get_session
from app.infrastructure.weather import get_current_weather, normalize_city

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserPublic])
def list_users(
    user: User = Depends(current_user),
) -> list[UserPublic]:
    """Sprint B: token zorunlu; yalnızca oturum açmış kullanıcıyı döndürür. Tercih: GET /auth/me."""
    return [
        UserPublic(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            height=user.height,
            weight=user.weight,
            age=user.age,
            location=user.location,
            avatar_key=user.avatar_key,
        )
    ]


@router.post("", response_model=User)
def create_user(payload: UserCreate, session: Session = Depends(get_session)) -> User:
    """Yeni kullanıcı kaydı (public). Parola sunucu tarafında bcrypt ile hashlenir."""
    return smart_home_service.create_user(payload, session)


@router.patch("/{user_id}", response_model=User)
def patch_user(
    user_id: str,
    payload: UserUpdate,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> User:
    """Sprint B: Bearer token zorunlu; yalnızca kendi profilinizi güncelleyebilirsiniz."""
    if token_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sadece kendi profilinizi guncelleyebilirsiniz.",
        )
    return smart_home_service.update_user(user_id, payload, session)


@router.get("/{user_id}/personalized-advices")
def get_personalized_advices(
    user_id: str,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Return the 4 advice cards curated for this user's BMI x age."""
    if user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sadece kendi tavsiyelerinizi gorebilirsiniz.",
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    profile = describe_profile(
        height_cm=user.height,
        weight_kg=user.weight,
        age=user.age,
    )
    advices = pick_advices(
        bmi=profile["bmi"] if isinstance(profile["bmi"], float) else None,
        age=user.age,
    )
    # Best-effort weather; never block advices if Open-Meteo is unreachable.
    city = normalize_city(user.location)
    weather: dict[str, object] | None = None
    try:
        weather = get_current_weather(city).to_dict()
    except Exception:
        weather = None
    return {
        "user_id": user_id,
        "profile": profile,
        "city": city,
        "weather": weather,
        "advices": advices,
    }


@router.get("/{user_id}/vacuum-recommendation")
def get_vacuum_recommendation(
    user_id: str,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Robot supurge kullanim saati/sikligi onerisi (demografik peer-matching).

    Kullanicinin yas/cinsiyet/sehir/BMI bilgisiyle anket veri setindeki en yakin
    akran grubunu bulup en cok tercih edilen supurme zamanini doner. Profil
    eksikse ``{"available": false}`` doner.
    """
    if user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sadece kendi onerilerinizi gorebilirsiniz.",
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    rec = device_recommendation_service.recommend_vacuum_schedule(user)
    if rec is None:
        return {"available": False}
    return {"available": True, **rec}


@router.get("/{user_id}/daily-activity", response_model=DailyActivityResponse)
def get_daily_activity(
    user_id: str,
    days: int = Query(10, ge=1, le=60, description="Number of trailing days."),
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> DailyActivityResponse:
    """Return the trailing daily activity log used by the dashboard streak gene.

    Token kullanıcısı yalnızca kendi aktivite logunu görebilir. Bir gün için
    "active" = o günde en az bir BehaviorLog kaydı olması.
    """
    if user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sadece kendi aktivite logunuzu gorebilirsiniz.",
        )
    raw = smart_home_service.get_daily_activity(user_id, session, days=days)
    return DailyActivityResponse(
        user_id=raw["user_id"],
        days=[DailyActivityDay(**d) for d in raw["days"]],
        weekly_streak_count=raw["weekly_streak_count"],
    )

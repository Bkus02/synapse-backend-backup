from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import current_user_id, current_user_id_optional
from app.api.schemas import (
    DailyActivityDay,
    DailyActivityResponse,
    UserCreate,
    UserUpdate,
)
from app.application.services import smart_home_service
from app.core.models import User
from app.db.database import get_session

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[User])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return smart_home_service.list_users(session)


@router.post("", response_model=User)
def create_user(payload: UserCreate, session: Session = Depends(get_session)) -> User:
    """Yeni kullanıcı kaydı (public). Parola sunucu tarafında bcrypt ile hashlenir."""
    return smart_home_service.create_user(payload, session)


@router.patch("/{user_id}", response_model=User)
def patch_user(
    user_id: str,
    payload: UserUpdate,
    session: Session = Depends(get_session),
    token_user_id: str | None = Depends(current_user_id_optional),
) -> User:
    """
    Kullanıcıyı güncelle.

    - Authorization header'da geçerli Bearer token varsa: yalnızca
      kendi profilini güncelleyebilir; yol parametresi eşleşmezse 403.
    - Token yoksa (Sprint F öncesi geri uyum): istek doğrudan uygulanır.
    """
    if token_user_id is not None and token_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sadece kendi profilinizi guncelleyebilirsiniz.",
        )
    return smart_home_service.update_user(user_id, payload, session)


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

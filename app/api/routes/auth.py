from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import current_user
from app.api.schemas import LoginRequest, LoginResponse, UserPublic
from app.application.services import smart_home_service
from app.core.models import User
from app.core.security import create_access_token
from app.core.settings import settings
from app.db.database import get_session

router = APIRouter(prefix="/auth", tags=["Auth"])


def _to_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        height=user.height,
        weight=user.weight,
        age=user.age,
        location=user.location,
        avatar_key=user.avatar_key,
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest, session: Session = Depends(get_session)
) -> LoginResponse:
    user = smart_home_service.login_user(payload, session)
    token = create_access_token(subject=user.id or "")
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_to_public(user),
    )


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(current_user)) -> UserPublic:
    """Token doğrulanmış aktif kullanıcı (geçerli Bearer gerektirir)."""
    return _to_public(user)

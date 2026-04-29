from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.schemas import UserCreate, UserUpdate
from app.application.services import smart_home_service
from app.core.models import User
from app.db.database import get_session

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[User])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return smart_home_service.list_users(session)


@router.post("", response_model=User)
def create_user(payload: UserCreate, session: Session = Depends(get_session)) -> User:
    return smart_home_service.create_user(payload, session)


@router.patch("/{user_id}", response_model=User)
def patch_user(
    user_id: str,
    payload: UserUpdate,
    session: Session = Depends(get_session),
) -> User:
    return smart_home_service.update_user(user_id, payload, session)

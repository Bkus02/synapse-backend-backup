from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.schemas import LoginRequest
from app.application.services import smart_home_service
from app.core.models import User
from app.db.database import get_session

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=User)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> User:
    return smart_home_service.login_user(payload, session)

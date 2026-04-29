from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.schemas import AddUserToEnvironmentRequest, EnvironmentCreate
from app.application.services import smart_home_service
from app.core.models import Environment, UserEnvironment
from app.db.database import get_session

router = APIRouter(prefix="/environments", tags=["Environments"])


@router.get("", response_model=list[Environment])
def list_environments(session: Session = Depends(get_session)) -> list[Environment]:
    return smart_home_service.list_environments(session)


@router.post("", response_model=Environment)
def create_environment(
    payload: EnvironmentCreate, session: Session = Depends(get_session)
) -> Environment:
    return smart_home_service.create_environment(payload, session)


@router.delete("/{environment_id}")
def delete_environment(environment_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    return smart_home_service.delete_environment(environment_id, session)


@router.post("/{environment_id}/add-user", response_model=UserEnvironment)
def add_user_to_environment(
    environment_id: str,
    payload: AddUserToEnvironmentRequest,
    session: Session = Depends(get_session),
) -> UserEnvironment:
    return smart_home_service.add_user_to_environment(environment_id, payload.user_id, session)

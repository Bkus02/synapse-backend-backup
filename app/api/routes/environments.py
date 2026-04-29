from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.schemas import (
    AddUserToEnvironmentRequest,
    AdminUserBody,
    EnvironmentCreate,
    EnvironmentMemberOut,
    JoinEnvironmentRequest,
    JoinRequestOut,
    SuggestedEnvironmentId,
)
from app.application.services import smart_home_service
from app.core.models import Environment, User, UserEnvironment
from app.db.database import get_session

router = APIRouter(prefix="/environments", tags=["Environments"])


def _join_request_out(req, session: Session) -> JoinRequestOut:
    user = session.get(User, req.user_id)
    return JoinRequestOut(
        id=req.id,
        environment_id=req.environment_id,
        user_id=req.user_id,
        requester_name=user.full_name if user else None,
        requester_avatar_key=user.avatar_key if user else None,
        created_at=req.created_at,
    )


@router.get("/suggest-id", response_model=SuggestedEnvironmentId)
def suggest_environment_id(session: Session = Depends(get_session)) -> SuggestedEnvironmentId:
    return SuggestedEnvironmentId(id=smart_home_service.suggest_next_environment_id(session))


@router.get("/for-user/{user_id}", response_model=list[Environment])
def list_environments_for_user(
    user_id: str, session: Session = Depends(get_session)
) -> list[Environment]:
    return smart_home_service.list_environments_for_user(user_id, session)


@router.get("", response_model=list[Environment])
def list_environments(session: Session = Depends(get_session)) -> list[Environment]:
    return smart_home_service.list_environments(session)


@router.post("", response_model=Environment)
def create_environment(
    payload: EnvironmentCreate, session: Session = Depends(get_session)
) -> Environment:
    return smart_home_service.create_environment(payload, session)


@router.get("/{environment_id}/members", response_model=list[EnvironmentMemberOut])
def get_environment_members(
    environment_id: str, session: Session = Depends(get_session)
) -> list[EnvironmentMemberOut]:
    raw = smart_home_service.list_environment_members(environment_id, session)
    return [EnvironmentMemberOut.model_validate(row) for row in raw]


@router.get("/{environment_id}/join-requests", response_model=list[JoinRequestOut])
def get_join_requests(
    environment_id: str,
    admin_user_id: str = Query(..., description="Environment admin user id"),
    session: Session = Depends(get_session),
) -> list[JoinRequestOut]:
    rows = smart_home_service.list_join_requests(environment_id, admin_user_id, session)
    return [_join_request_out(row, session) for row in rows]


@router.post("/{environment_id}/join-requests", response_model=JoinRequestOut)
def post_join_request(
    environment_id: str,
    payload: JoinEnvironmentRequest,
    session: Session = Depends(get_session),
) -> JoinRequestOut:
    req = smart_home_service.create_join_request(environment_id, payload.user_id, session)
    return _join_request_out(req, session)


@router.post(
    "/{environment_id}/join-requests/{request_id}/approve",
    response_model=UserEnvironment,
)
def approve_join_request(
    environment_id: str,
    request_id: int,
    body: AdminUserBody,
    session: Session = Depends(get_session),
) -> UserEnvironment:
    return smart_home_service.approve_join_request(
        environment_id, request_id, body.admin_user_id, session
    )


@router.post("/{environment_id}/join-requests/{request_id}/reject")
def reject_join_request(
    environment_id: str,
    request_id: int,
    body: AdminUserBody,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    return smart_home_service.reject_join_request(
        environment_id, request_id, body.admin_user_id, session
    )


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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import current_user_id
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
    user_id: str,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[Environment]:
    if user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sadece kendi environment listenizi gorebilirsiniz.",
        )
    return smart_home_service.list_environments_for_user(user_id, session)


@router.get("", response_model=list[Environment])
def list_environments(
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[Environment]:
    return smart_home_service.list_environments_for_user(token_user_id, session)


@router.post("", response_model=Environment)
def create_environment(
    payload: EnvironmentCreate,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> Environment:
    if payload.admin_id and payload.admin_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_id token user_id ile eslesmeli.",
        )
    payload.admin_id = token_user_id
    return smart_home_service.create_environment(payload, session)


@router.get("/{environment_id}/members", response_model=list[EnvironmentMemberOut])
def get_environment_members(
    environment_id: str,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[EnvironmentMemberOut]:
    smart_home_service.require_environment_access(token_user_id, environment_id, session)
    raw = smart_home_service.list_environment_members(environment_id, session)
    return [EnvironmentMemberOut.model_validate(row) for row in raw]


@router.get("/{environment_id}/streaks")
def get_environment_streaks(
    environment_id: str,
    days: int = Query(10, ge=1, le=60, description="Number of trailing days."),
    limit: int | None = Query(
        None,
        ge=1,
        le=50,
        description="Optional max members to return (top N by streak).",
    ),
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    """Per-member weekly streak in an environment (sorted by streak desc)."""
    smart_home_service.require_environment_access(
        token_user_id, environment_id, session
    )
    rows = smart_home_service.list_environment_streaks(
        environment_id, session, days=days
    )
    if limit is not None:
        rows = rows[:limit]
    return rows


@router.get("/{environment_id}/join-requests", response_model=list[JoinRequestOut])
def get_join_requests(
    environment_id: str,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[JoinRequestOut]:
    rows = smart_home_service.list_join_requests(environment_id, token_user_id, session)
    return [_join_request_out(row, session) for row in rows]


@router.post("/{environment_id}/join-requests", response_model=JoinRequestOut)
def post_join_request(
    environment_id: str,
    payload: JoinEnvironmentRequest,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> JoinRequestOut:
    if payload.user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="payload.user_id token user_id ile eslesmeli.",
        )
    req = smart_home_service.create_join_request(environment_id, token_user_id, session)
    return _join_request_out(req, session)


@router.post(
    "/{environment_id}/join-requests/{request_id}/approve",
    response_model=UserEnvironment,
)
def approve_join_request(
    environment_id: str,
    request_id: int,
    body: AdminUserBody,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> UserEnvironment:
    if body.admin_user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_user_id token user_id ile eslesmeli.",
        )
    return smart_home_service.approve_join_request(
        environment_id, request_id, token_user_id, session
    )


@router.post("/{environment_id}/join-requests/{request_id}/reject")
def reject_join_request(
    environment_id: str,
    request_id: int,
    body: AdminUserBody,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if body.admin_user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_user_id token user_id ile eslesmeli.",
        )
    return smart_home_service.reject_join_request(
        environment_id, request_id, token_user_id, session
    )


@router.delete("/{environment_id}")
def delete_environment(
    environment_id: str,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    smart_home_service.require_environment_admin(token_user_id, environment_id, session)
    return smart_home_service.delete_environment(environment_id, session)


@router.delete("/{environment_id}/members/{user_id}")
def remove_environment_member(
    environment_id: str,
    user_id: str,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    # Self-leave is allowed for any member; removing someone else needs admin.
    if token_user_id != user_id:
        smart_home_service.require_environment_admin(
            token_user_id, environment_id, session
        )
    return smart_home_service.remove_user_from_environment(
        environment_id, user_id, session
    )


@router.post("/{environment_id}/add-user", response_model=UserEnvironment)
def add_user_to_environment(
    environment_id: str,
    payload: AddUserToEnvironmentRequest,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> UserEnvironment:
    smart_home_service.require_environment_admin(token_user_id, environment_id, session)
    return smart_home_service.add_user_to_environment(environment_id, payload.user_id, session)


@router.post("/{environment_id}/invite")
def invite_user_to_environment(
    environment_id: str,
    payload: AddUserToEnvironmentRequest,
    token_user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Admin, bir kullaniciyi ID'sine gore davet eder.

    Hedef kullaniciya bir bildirim gonderilir; kullanici onaylarsa environment'e
    katilir (bkz. notification_service.confirm — kind=environment_invite).
    """
    return smart_home_service.invite_user_to_environment(
        environment_id, token_user_id, payload.user_id, session
    )

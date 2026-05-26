from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import current_user_id
from app.api.schemas import DeviceCreate
from app.application.services import smart_home_service
from app.core.models import Device
from app.db.database import get_session

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[Device])
def list_devices(
    environment_id: str | None = Query(
        None, description="Required: environment id filter (token user must be a member)."
    ),
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[Device]:
    if environment_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="environment_id zorunlu.",
        )
    return smart_home_service.list_devices_for_environment(environment_id, user_id, session)


@router.post("", response_model=Device)
def create_device(
    payload: DeviceCreate,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> Device:
    return smart_home_service.create_device_authenticated(payload, user_id, session)


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    return smart_home_service.delete_device_authenticated(device_id, user_id, session)

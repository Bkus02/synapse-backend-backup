from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.schemas import DeviceCreate
from app.application.services import smart_home_service
from app.core.models import Device
from app.db.database import get_session

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[Device])
def list_devices(
    environment_id: str = Query(
        ..., description="Environment id (H + 7 chars) to list devices for."
    ),
    user_id: str = Query(
        ..., description="Caller user id; must be environment member or admin."
    ),
    session: Session = Depends(get_session),
) -> list[Device]:
    return smart_home_service.list_devices_for_environment(
        environment_id, user_id, session
    )


@router.post("", response_model=Device)
def create_device(
    payload: DeviceCreate,
    user_id: str = Query(
        ..., description="Caller user id; must be environment member or admin."
    ),
    session: Session = Depends(get_session),
) -> Device:
    return smart_home_service.create_device_authenticated(payload, user_id, session)


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    user_id: str = Query(
        ..., description="Caller user id; must be environment member or admin."
    ),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    return smart_home_service.delete_device_authenticated(device_id, user_id, session)

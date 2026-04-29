from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.schemas import DeviceCreate
from app.application.services import smart_home_service
from app.core.models import Device
from app.db.database import get_session

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[Device])
def list_devices(
    environment_id: str | None = Query(None, description="Optional environment id filter."),
    user_id: str | None = Query(None, description="Required when environment_id is provided."),
    session: Session = Depends(get_session),
) -> list[Device]:
    if environment_id is not None:
        if user_id is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="environment_id ile user_id zorunlu.")
        return smart_home_service.list_devices_for_environment(environment_id, user_id, session)
    return smart_home_service.list_devices(session)


@router.post("", response_model=Device)
def create_device(
    payload: DeviceCreate,
    user_id: str | None = Query(None, description="Optional caller user id for access check."),
    session: Session = Depends(get_session),
) -> Device:
    if user_id is not None:
        return smart_home_service.create_device_authenticated(payload, user_id, session)
    return smart_home_service.create_device(payload, session)


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    user_id: str | None = Query(None, description="Optional caller user id for access check."),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if user_id is not None:
        return smart_home_service.delete_device_authenticated(device_id, user_id, session)
    return smart_home_service.delete_device(device_id, session)

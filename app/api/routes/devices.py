from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.schemas import DeviceCreate
from app.application.services import smart_home_service
from app.core.models import Device
from app.db.database import get_session

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=list[Device])
def list_devices(session: Session = Depends(get_session)) -> list[Device]:
    return smart_home_service.list_devices(session)


@router.post("", response_model=Device)
def create_device(payload: DeviceCreate, session: Session = Depends(get_session)) -> Device:
    return smart_home_service.create_device(payload, session)


@router.delete("/{device_id}")
def delete_device(device_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    return smart_home_service.delete_device(device_id, session)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import current_user_id
<<<<<<< Updated upstream
from app.api.schemas import DeviceCreate, DeviceUpdate
=======
from app.api.schemas import DeviceCreate, DevicePatch
>>>>>>> Stashed changes
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


@router.patch("/{device_id}", response_model=Device)
def patch_device(
    device_id: int,
<<<<<<< Updated upstream
    payload: DeviceUpdate,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> Device:
    return smart_home_service.patch_device(device_id, user_id, payload, session)
=======
    payload: DevicePatch,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> Device:
    """
    Sprint D: cihazı aç/kapa simülasyonu.

    `status` güncellenir, `behavior_logs` kaydı oluşturulur ve inference arka planda çalışır.
  """
    if payload.status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status alani zorunlu (simulasyon icin).",
        )
    device, log = smart_home_service.set_device_status_authenticated(
        device_id,
        user_id,
        payload.status,
        session,
        current_value=payload.current_value,
    )
    background_tasks.add_task(
        smart_home_service.run_inference_for_behavior_log_background, log.id
    )
    return device
>>>>>>> Stashed changes


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    return smart_home_service.delete_device_authenticated(device_id, user_id, session)

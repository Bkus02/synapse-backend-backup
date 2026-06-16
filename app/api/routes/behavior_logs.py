from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import current_user_id
from app.api.schemas import BehaviorLogCreate, HabitSequenceResponse
from app.application.services import smart_home_service
from app.core.models import BehaviorLog, Device
from app.db.database import get_session

router = APIRouter(prefix="/behavior-logs", tags=["BehaviorLogs"])


@router.get("", response_model=list[BehaviorLog])
def list_behavior_logs(
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[BehaviorLog]:
    rows = smart_home_service.list_behavior_logs(session)
    return [row for row in rows if row.user_id == user_id]


@router.post("", response_model=BehaviorLog)
def create_behavior_log(
    payload: BehaviorLogCreate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> BehaviorLog:
    if payload.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="payload.user_id token user_id ile eslesmeli.",
        )
    device = session.get(Device, payload.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device bulunamadi.")
    smart_home_service.require_environment_access(user_id, device.environment_id, session)

    log = smart_home_service.create_behavior_log(payload, session)
    background_tasks.add_task(
        smart_home_service.run_inference_for_behavior_log_background, log.id
    )
    return log


@router.delete("/{log_id}")
def delete_behavior_log(
    log_id: int,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    log = session.get(BehaviorLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="BehaviorLog bulunamadi.")
    if log.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sadece kendi BehaviorLog kaydinizi silebilirsiniz.",
        )
    return smart_home_service.delete_behavior_log(log_id, session)


@router.get("/sequences", response_model=list[HabitSequenceResponse])
def mine_behavior_sequences(
    window_minutes: int = Query(15, ge=1, le=180),
    min_confidence: float = Query(0.50, ge=0.0, le=1.0),
    min_support: int = Query(2, ge=1),
    _user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[HabitSequenceResponse]:
    return smart_home_service.mine_behavior_sequences(
        session,
        window_minutes=window_minutes,
        min_confidence=min_confidence,
        min_support=min_support,
    )


@router.post("/rebuild-habit-matrix")
def rebuild_habit_matrix(
    _user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    return smart_home_service.rebuild_habit_matrix(session)



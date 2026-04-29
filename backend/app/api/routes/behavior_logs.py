from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.schemas import BehaviorLogCreate
from app.application.services import smart_home_service
from app.core.models import BehaviorLog
from app.db.database import get_session

router = APIRouter(prefix="/behavior-logs", tags=["BehaviorLogs"])


@router.get("", response_model=list[BehaviorLog])
def list_behavior_logs(session: Session = Depends(get_session)) -> list[BehaviorLog]:
    return smart_home_service.list_behavior_logs(session)


@router.post("", response_model=BehaviorLog)
def create_behavior_log(
    payload: BehaviorLogCreate, session: Session = Depends(get_session)
) -> BehaviorLog:
    return smart_home_service.create_behavior_log(payload, session)


@router.delete("/{log_id}")
def delete_behavior_log(log_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    return smart_home_service.delete_behavior_log(log_id, session)

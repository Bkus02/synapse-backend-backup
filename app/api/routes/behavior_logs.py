from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlmodel import Session

from app.api.schemas import BehaviorLogCreate, HabitSequenceResponse
from app.application.services import smart_home_service
from app.core.models import BehaviorLog
from app.db.database import engine, get_session

router = APIRouter(prefix="/behavior-logs", tags=["BehaviorLogs"])


@router.get("", response_model=list[BehaviorLog])
def list_behavior_logs(session: Session = Depends(get_session)) -> list[BehaviorLog]:
    return smart_home_service.list_behavior_logs(session)


@router.post("", response_model=BehaviorLog)
def create_behavior_log(
    payload: BehaviorLogCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> BehaviorLog:
    log = smart_home_service.create_behavior_log(payload, session)
    background_tasks.add_task(_run_inference_and_notify, log.id)
    return log


@router.delete("/{log_id}")
def delete_behavior_log(log_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    return smart_home_service.delete_behavior_log(log_id, session)


@router.get("/sequences", response_model=list[HabitSequenceResponse])
def mine_behavior_sequences(
    window_minutes: int = Query(15, ge=1, le=180),
    min_confidence: float = Query(0.50, ge=0.0, le=1.0),
    min_support: int = Query(2, ge=1),
    session: Session = Depends(get_session),
) -> list[HabitSequenceResponse]:
    return smart_home_service.mine_behavior_sequences(
        session,
        window_minutes=window_minutes,
        min_confidence=min_confidence,
        min_support=min_support,
    )


@router.post("/rebuild-habit-matrix")
def rebuild_habit_matrix(session: Session = Depends(get_session)) -> dict[str, int]:
    return smart_home_service.rebuild_habit_matrix(session)


def _run_inference_and_notify(log_id: int | None) -> None:
    if log_id is None:
        return
    with Session(engine) as task_session:
        decision = smart_home_service.run_inference_for_behavior_log(log_id, task_session)
        if decision:
            print(f"AI Onerisi Hazirlandi: {decision.get('message')}")

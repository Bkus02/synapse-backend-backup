from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.schemas import HabitCreate
from app.application.services import smart_home_service
from app.core.models import Habit
from app.db.database import get_session

router = APIRouter(prefix="/habits", tags=["Habits"])


@router.get("", response_model=list[Habit])
def list_habits(session: Session = Depends(get_session)) -> list[Habit]:
    return smart_home_service.list_habits(session)


@router.post("", response_model=Habit)
def create_habit(payload: HabitCreate, session: Session = Depends(get_session)) -> Habit:
    return smart_home_service.create_habit(payload, session)


@router.delete("/{habit_id}")
def delete_habit(habit_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    return smart_home_service.delete_habit(habit_id, session)

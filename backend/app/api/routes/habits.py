from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.schemas import HabitCreate, HabitUpdate
from app.application.services import smart_home_service
from app.core.models import Habit
from app.db.database import get_session

router = APIRouter(prefix="/habits", tags=["Habits"])


@router.get("", response_model=list[Habit])
def list_habits(
    user_id: str = Query(..., description="Return habits for this user only."),
    session: Session = Depends(get_session),
) -> list[Habit]:
    return smart_home_service.list_habits_for_user(user_id, session)


@router.post("", response_model=Habit)
def create_habit(
    payload: HabitCreate,
    user_id: str = Query(
        ..., description="Must match user_id in body (caller identity check)."
    ),
    session: Session = Depends(get_session),
) -> Habit:
    if payload.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="user_id query must match payload.user_id.",
        )
    return smart_home_service.create_habit(payload, session)


@router.patch("/{habit_id}", response_model=Habit)
def patch_habit(
    habit_id: int,
    payload: HabitUpdate,
    user_id: str = Query(..., description="Owner user id."),
    session: Session = Depends(get_session),
) -> Habit:
    return smart_home_service.patch_habit(habit_id, user_id, payload, session)


@router.delete("/{habit_id}")
def delete_habit(
    habit_id: int,
    user_id: str = Query(..., description="Owner user id."),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    return smart_home_service.delete_habit_authenticated(habit_id, user_id, session)

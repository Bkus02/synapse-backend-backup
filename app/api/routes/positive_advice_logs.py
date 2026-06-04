"""REST endpoints for logging positive-advice completions and reading streaks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.deps import current_user_id
from app.application.services import positive_advice_service
from app.application.services.recommendation_catalog import ADVICE_CATALOG
from app.core.models import PositiveAdviceLog
from app.db.database import get_session

router = APIRouter(prefix="/positive-advices", tags=["Positive Advices"])


class AdviceLogBody(BaseModel):
    advice_key: str = Field(..., description="ADVICE_CATALOG anahtarı.")
    duration_minutes: int = Field(default=0, ge=0, le=24 * 60)
    completed_at: datetime | None = Field(
        default=None, description="Boşsa server zamanı (UTC) kullanılır."
    )


class AdviceLogResponse(BaseModel):
    id: int
    user_id: str
    advice_key: str
    advice_title: str
    category: str
    completed_at: datetime
    duration_minutes: int

    @classmethod
    def from_model(cls, log: PositiveAdviceLog) -> "AdviceLogResponse":
        return cls(
            id=log.id or 0,
            user_id=log.user_id,
            advice_key=log.advice_key,
            advice_title=log.advice_title,
            category=str(log.category),
            completed_at=log.completed_at,
            duration_minutes=log.duration_minutes,
        )


@router.post("/logs", response_model=AdviceLogResponse, status_code=status.HTTP_201_CREATED)
def create_log(
    body: AdviceLogBody,
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> AdviceLogResponse:
    if body.advice_key not in ADVICE_CATALOG:
        raise HTTPException(
            status_code=400, detail=f"Bilinmeyen advice_key: {body.advice_key}"
        )
    log = positive_advice_service.log_advice_completion(
        user_id=user_id,
        advice_key=body.advice_key,
        duration_minutes=body.duration_minutes,
        completed_at=body.completed_at,
        session=session,
    )
    return AdviceLogResponse.from_model(log)


@router.get("/logs", response_model=list[AdviceLogResponse])
def list_logs(
    limit: int = Query(default=100, ge=1, le=500),
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> list[AdviceLogResponse]:
    rows = positive_advice_service.list_advice_logs(
        user_id, session=session, limit=limit
    )
    return [AdviceLogResponse.from_model(r) for r in rows]


@router.get("/streak")
def get_streak(
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return positive_advice_service.get_daily_streak(user_id, session)


@router.post("/recompute-streak")
def recompute_streak(
    user_id: str = Depends(current_user_id),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    positive_advice_service.recompute_daily_streak(user_id, session)
    return positive_advice_service.get_daily_streak(user_id, session)

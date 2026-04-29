from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.schemas import RecommendationResponse, RecommendationStatusUpdateResponse
from app.application.services import smart_home_service
from app.core.models import RecommendationStatus
from app.db.database import get_session

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/active", response_model=RecommendationResponse | None)
def get_active_recommendation(
    user_id: str = Query(...),
    session: Session = Depends(get_session),
) -> RecommendationResponse | None:
    row = smart_home_service.get_latest_pending_recommendation(user_id, session)
    if row is None:
        return None
    return RecommendationResponse(
        id=row.id,
        user_id=row.user_id,
        type=row.recommendation_type,
        trigger=f"{row.trigger_device}_{row.action}",
        target=f"{row.target_device}_{row.action}",
        context=row.context,
        final_confidence=float(row.confidence),
        status=row.status.value,
        created_at=row.created_at,
    )


@router.post("/{recommendation_id}/accept", response_model=RecommendationStatusUpdateResponse)
def accept_recommendation(
    recommendation_id: str,
    session: Session = Depends(get_session),
) -> RecommendationStatusUpdateResponse:
    rec = smart_home_service.update_recommendation_status(
        recommendation_id, RecommendationStatus.Accepted, session
    )
    return RecommendationStatusUpdateResponse(id=rec.id, status=rec.status.value)


@router.post("/{recommendation_id}/reject", response_model=RecommendationStatusUpdateResponse)
def reject_recommendation(
    recommendation_id: str,
    session: Session = Depends(get_session),
) -> RecommendationStatusUpdateResponse:
    rec = smart_home_service.update_recommendation_status(
        recommendation_id, RecommendationStatus.Rejected, session
    )
    smart_home_service.penalize_habit_matrix_from_rejection(recommendation_id, session)
    return RecommendationStatusUpdateResponse(id=rec.id, status=rec.status.value)


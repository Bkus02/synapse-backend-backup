from fastapi import APIRouter, Depends, HTTPException, Query, statusfrom sqlmodel import Sessionfrom app.api.deps import current_user, current_user_id_optional, resolve_effective_user_idfrom app.api.schemas import RecommendationResponse, RecommendationStatusUpdateResponsefrom app.application.services import smart_home_servicefrom app.core.models import Recommendation, RecommendationStatus, Userfrom app.db.database import get_sessionrouter = APIRouter(prefix="/recommendations", tags=["Recommendations"])


def _to_response(row: Recommendation) -> RecommendationResponse:
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


@router.get("/active", response_model=RecommendationResponse | None)
def get_active_recommendation(
    user_id: str | None = Query(None),
    token_user_id: str | None = Depends(current_user_id_optional),
    session: Session = Depends(get_session),
) -> RecommendationResponse | None:
    effective = resolve_effective_user_id(user_id, token_user_id)
    row = smart_home_service.get_latest_pending_recommendation(effective, session)
    if row is None:
        return None
    return _to_response(row)


def _require_owned_recommendation(
    recommendation_id: str,
    user: User,
    session: Session,
) -> Recommendation:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation bulunamadi.")
    if rec.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu recommendation size ait degil.",
        )
    return rec


@router.post("/{recommendation_id}/accept", response_model=RecommendationStatusUpdateResponse)
def accept_recommendation(
    recommendation_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RecommendationStatusUpdateResponse:
    _require_owned_recommendation(recommendation_id, user, session)
    rec = smart_home_service.update_recommendation_status(
        recommendation_id, RecommendationStatus.Accepted, session
    )
    return RecommendationStatusUpdateResponse(id=rec.id, status=rec.status.value)


@router.post("/{recommendation_id}/reject", response_model=RecommendationStatusUpdateResponse)
def reject_recommendation(
    recommendation_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RecommendationStatusUpdateResponse:
    _require_owned_recommendation(recommendation_id, user, session)
    rec = smart_home_service.update_recommendation_status(
        recommendation_id, RecommendationStatus.Rejected, session
    )
    smart_home_service.penalize_habit_matrix_from_rejection(recommendation_id, session)
    return RecommendationStatusUpdateResponse(id=rec.id, status=rec.status.value)

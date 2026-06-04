"""Live weather endpoint for the 3 supported cities."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import current_user_id_optional
from app.infrastructure.weather import (
    SUPPORTED_CITIES,
    UnsupportedCity,
    get_current_weather,
    normalize_city,
)

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("/cities")
def list_cities() -> list[dict[str, object]]:
    return [
        {"key": key, "label": key.title(), "lat": lat, "lon": lon}
        for key, (lat, lon) in SUPPORTED_CITIES.items()
    ]


@router.get("/current")
def current_weather(
    city: str | None = Query(
        default=None,
        description="One of istanbul/ankara/izmir. Defaults to the caller's profile city (Istanbul fallback).",
    ),
    _user_id: str | None = Depends(current_user_id_optional),
) -> dict[str, object]:
    target = normalize_city(city)
    try:
        snapshot = get_current_weather(target)
    except UnsupportedCity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported city. Use one of: istanbul, ankara, izmir.",
        )
    except Exception as exc:  # network failure, etc.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Weather provider unavailable: {exc}",
        ) from exc
    return snapshot.to_dict()

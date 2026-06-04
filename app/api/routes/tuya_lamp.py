"""Tuya Smart Life lamp control (cloud API)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import current_user_id
from app.infrastructure.devices import tuya_client

router = APIRouter(prefix="/integrations/tuya/lamp", tags=["Tuya Lamp"])


class BrightnessBody(BaseModel):
    value: int = Field(ge=0, le=100, description="Brightness 0–100 %")


def _tuya_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, tuya_client.TuyaNotConfiguredError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    if isinstance(exc, tuya_client.TuyaApiError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Tuya request failed: {exc}",
    )


@router.get("/configured")
def lamp_configured(_user_id: str = Depends(current_user_id)) -> dict[str, bool]:
    return {"configured": tuya_client.is_configured()}


@router.get("/status")
def lamp_status(_user_id: str = Depends(current_user_id)) -> dict:
    try:
        return tuya_client.get_lamp_status()
    except Exception as exc:
        raise _tuya_http_error(exc) from exc


@router.post("/on")
def lamp_on(_user_id: str = Depends(current_user_id)) -> dict:
    try:
        return tuya_client.lamp_on()
    except Exception as exc:
        raise _tuya_http_error(exc) from exc


@router.post("/off")
def lamp_off(_user_id: str = Depends(current_user_id)) -> dict:
    try:
        return tuya_client.lamp_off()
    except Exception as exc:
        raise _tuya_http_error(exc) from exc


@router.post("/brightness")
def lamp_brightness(
    body: BrightnessBody,
    _user_id: str = Depends(current_user_id),
) -> dict:
    try:
        return tuya_client.lamp_set_brightness(body.value)
    except Exception as exc:
        raise _tuya_http_error(exc) from exc

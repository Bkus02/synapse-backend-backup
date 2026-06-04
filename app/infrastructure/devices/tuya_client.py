"""Tuya Cloud Open API — Smart Life linked devices."""

from __future__ import annotations

import logging
from typing import Any

from tuya_connector import TuyaOpenAPI

from app.core.settings import settings

logger = logging.getLogger(__name__)

# Common DP codes for RGB/RGBCW bulbs (Smart Life / Tuya).
_SWITCH_CODES = ("switch_led", "switch", "switch_1", "switch_2")
_BRIGHTNESS_CODES = ("bright_value_v2", "bright_value")


class TuyaNotConfiguredError(RuntimeError):
    """Missing TUYA_* env vars."""


class TuyaApiError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def is_configured() -> bool:
    return bool(
        settings.tuya_access_id.strip()
        and settings.tuya_access_secret.strip()
        and settings.tuya_device_id.strip()
    )


def _unwrap(response: dict[str, Any]) -> Any:
    if not response.get("success"):
        raise TuyaApiError(
            str(response.get("msg") or "Tuya API error"),
            code=response.get("code"),
        )
    return response.get("result")


def _api() -> TuyaOpenAPI:
    if not is_configured():
        raise TuyaNotConfiguredError(
            "Tuya is not configured. Set TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, "
            "and TUYA_DEVICE_ID in .env (see .env.example)."
        )
    client = TuyaOpenAPI(
        settings.tuya_api_endpoint.rstrip("/"),
        settings.tuya_access_id.strip(),
        settings.tuya_access_secret.strip(),
    )
    client.connect()
    return client


def _device_id() -> str:
    return settings.tuya_device_id.strip()


def _status_list(api: TuyaOpenAPI, device_id: str) -> list[dict[str, Any]]:
    raw = _unwrap(api.get(f"/v1.0/devices/{device_id}/status"))
    if isinstance(raw, list):
        return raw
    return []


def _pick_code(status: list[dict[str, Any]], candidates: tuple[str, ...]) -> str | None:
    present = {str(item.get("code")) for item in status}
    for code in candidates:
        if code in present:
            return code
    return None


def _send_commands(commands: list[dict[str, Any]]) -> dict[str, Any]:
    api = _api()
    device_id = _device_id()
    _unwrap(
        api.post(
            f"/v1.0/devices/{device_id}/commands",
            {"commands": commands},
        )
    )
    logger.info("tuya commands device=%s commands=%s", device_id, commands)
    return {"device_id": device_id, "commands": commands}


def get_lamp_status() -> dict[str, Any]:
    """Cloud status + parsed on/brightness when DP codes are known."""
    api = _api()
    device_id = _device_id()
    info = _unwrap(api.get(f"/v1.0/devices/{device_id}"))
    status = _status_list(api, device_id)

    switch_code = _pick_code(status, _SWITCH_CODES)
    brightness_code = _pick_code(status, _BRIGHTNESS_CODES)

    parsed: dict[str, Any] = {
        "online": bool(info.get("online")) if isinstance(info, dict) else None,
        "name": info.get("name") if isinstance(info, dict) else None,
        "switch_code": switch_code,
        "brightness_code": brightness_code,
        "is_on": None,
        "brightness_percent": None,
    }

    for item in status:
        code = str(item.get("code"))
        value = item.get("value")
        if switch_code and code == switch_code:
            parsed["is_on"] = bool(value)
        if brightness_code and code == brightness_code:
            try:
                numeric = int(value)
                # Tuya bulbs often use 10–1000; map to 0–100 %.
                parsed["brightness_percent"] = max(
                    0, min(100, round((numeric - 10) / 990 * 100))
                )
            except (TypeError, ValueError):
                parsed["brightness_percent"] = None

    return {
        "device_id": device_id,
        "info": info,
        "status": status,
        "parsed": parsed,
    }


def lamp_on() -> dict[str, Any]:
    api = _api()
    device_id = _device_id()
    status = _status_list(api, device_id)
    code = _pick_code(status, _SWITCH_CODES) or "switch_led"
    return _send_commands([{"code": code, "value": True}])


def lamp_off() -> dict[str, Any]:
    api = _api()
    device_id = _device_id()
    status = _status_list(api, device_id)
    code = _pick_code(status, _SWITCH_CODES) or "switch_led"
    return _send_commands([{"code": code, "value": False}])


def lamp_set_brightness(percent: int) -> dict[str, Any]:
    """Set brightness 0–100 %. Turns lamp on if needed."""
    percent = max(0, min(100, percent))
    api = _api()
    device_id = _device_id()
    status = _status_list(api, device_id)
    switch_code = _pick_code(status, _SWITCH_CODES) or "switch_led"
    bright_code = _pick_code(status, _BRIGHTNESS_CODES) or "bright_value"
    # Tuya range is typically 10–1000 (not 0).
    tuya_value = max(10, min(1000, round(10 + (percent / 100) * 990)))
    commands = [
        {"code": switch_code, "value": True},
        {"code": bright_code, "value": tuya_value},
    ]
    result = _send_commands(commands)
    result["brightness_percent"] = percent
    result["tuya_brightness"] = tuya_value
    return result

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyDetected:
    """Cihaz kullanim suresi k esigini astiginda yayinlanan domain event."""

    user_id: str
    device_id: int
    device_label: str
    action: str
    current_minutes: float
    average_minutes: float
    k_threshold: float
    confidence: float

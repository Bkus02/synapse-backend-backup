from __future__ import annotations

from typing import Protocol


class EventPublisher(Protocol):
    def publish(self, event: object) -> None:
        """Domain event'ini dis dunyaya (log, mesaj kuyrugu, test collector) iletir."""

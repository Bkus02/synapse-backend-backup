from __future__ import annotations


class InMemoryEventPublisher:
    """Test ve yerel gelistirme icin bellek ici event collector."""

    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)

    def clear(self) -> None:
        self.events.clear()

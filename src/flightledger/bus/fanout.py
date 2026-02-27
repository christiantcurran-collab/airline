from __future__ import annotations

from typing import Iterable

from flightledger.models.canonical import CanonicalEvent


class FanoutBus:
    def __init__(self, buses: Iterable[object]) -> None:
        self._buses = list(buses)

    def publish(self, event: CanonicalEvent) -> None:
        for bus in self._buses:
            bus.publish(event)

    def publish_many(self, events: list[CanonicalEvent]) -> None:
        for event in events:
            self.publish(event)

    def close(self) -> None:
        for bus in self._buses:
            close = getattr(bus, "close", None)
            if callable(close):
                close()


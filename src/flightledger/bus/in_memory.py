from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from flightledger.bus.routing import EVENT_TOPIC_MAP
from flightledger.models.canonical import CanonicalEvent


class InMemoryBus:
    def __init__(self) -> None:
        self.topics: dict[str, list[CanonicalEvent]] = defaultdict(list)

    def publish(self, event: CanonicalEvent) -> None:
        topic = EVENT_TOPIC_MAP[event.event_type]
        self.topics[topic].append(event)

    def publish_many(self, events: Iterable[CanonicalEvent]) -> None:
        for event in events:
            self.publish(event)

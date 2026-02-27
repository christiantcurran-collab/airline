from __future__ import annotations

import json
from typing import Iterable

from kafka import KafkaProducer

from flightledger.bus.routing import EVENT_TOPIC_MAP
from flightledger.models.canonical import CanonicalEvent


class KafkaBus:
    def __init__(
        self,
        bootstrap_servers: str,
        client_id: str = "flightledger-producer",
        producer: KafkaProducer | None = None,
    ) -> None:
        self._owns_producer = producer is None
        self._producer = producer or KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            linger_ms=10,
            acks="all",
            value_serializer=lambda payload: json.dumps(payload).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8"),
        )

    def publish(self, event: CanonicalEvent) -> None:
        topic = EVENT_TOPIC_MAP[event.event_type]
        payload = event.model_dump(mode="json")
        self._producer.send(topic, key=event.ticket_number, value=payload)

    def publish_many(self, events: Iterable[CanonicalEvent]) -> None:
        for event in events:
            self.publish(event)
        self._producer.flush()

    def close(self) -> None:
        if self._owns_producer:
            self._producer.flush()
            self._producer.close()


from __future__ import annotations

from flightledger.bus.factory import build_transport_bus_from_env
from flightledger.bus.kafka import KafkaBus
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, str]]] = []
        self.flush_count = 0
        self.closed = False

    def send(self, topic: str, key: str, value: dict[str, str]) -> None:
        self.sent.append((topic, key, value))

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.closed = True


def test_kafka_bus_publishes_event_to_expected_topic() -> None:
    producer = FakeProducer()
    bus = KafkaBus(bootstrap_servers="127.0.0.1:9092", producer=producer)  # type: ignore[arg-type]
    event = CanonicalEvent(
        source_system=SourceSystem.PSS,
        event_type=CanonicalEventType.TICKET_ISSUED,
        ticket_number="125000000001",
    )

    bus.publish_many([event])

    assert len(producer.sent) == 1
    topic, key, value = producer.sent[0]
    assert topic == "ticket.issued"
    assert key == "125000000001"
    assert value["ticket_number"] == "125000000001"
    assert producer.flush_count == 1
    assert producer.closed is False


def test_factory_returns_none_for_memory_backend(monkeypatch) -> None:
    monkeypatch.setenv("FLIGHTLEDGER_BUS_BACKEND", "memory")
    assert build_transport_bus_from_env() is None


def test_factory_builds_kafka_bus(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class DummyKafkaBus:
        def __init__(self, bootstrap_servers: str, client_id: str) -> None:
            captured["bootstrap_servers"] = bootstrap_servers
            captured["client_id"] = client_id

    monkeypatch.setenv("FLIGHTLEDGER_BUS_BACKEND", "kafka")
    monkeypatch.setenv("FLIGHTLEDGER_KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    monkeypatch.setenv("FLIGHTLEDGER_KAFKA_CLIENT_ID", "flightledger-test")
    monkeypatch.setattr("flightledger.bus.factory.KafkaBus", DummyKafkaBus)

    _ = build_transport_bus_from_env()

    assert captured == {
        "bootstrap_servers": "localhost:19092",
        "client_id": "flightledger-test",
    }


def test_factory_rejects_unknown_backend(monkeypatch) -> None:
    monkeypatch.setenv("FLIGHTLEDGER_BUS_BACKEND", "redis")
    try:
        build_transport_bus_from_env()
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "Unsupported FLIGHTLEDGER_BUS_BACKEND" in str(exc)

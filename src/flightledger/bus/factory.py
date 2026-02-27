from __future__ import annotations

import os

from flightledger.bus.kafka import KafkaBus


def build_transport_bus_from_env() -> KafkaBus | None:
    backend = os.getenv("FLIGHTLEDGER_BUS_BACKEND", "memory").strip().lower()
    if backend == "memory":
        return None
    if backend == "kafka":
        bootstrap_servers = os.getenv("FLIGHTLEDGER_KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
        client_id = os.getenv("FLIGHTLEDGER_KAFKA_CLIENT_ID", "flightledger-producer")
        return KafkaBus(bootstrap_servers=bootstrap_servers, client_id=client_id)
    raise ValueError("Unsupported FLIGHTLEDGER_BUS_BACKEND. Use 'memory' or 'kafka'.")


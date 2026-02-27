from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flightledger.adapters import (
    DcsStreamAdapter,
    GdsXmlAdapter,
    InterlineRestAdapter,
    OtaWebhookAdapter,
    PssCsvAdapter,
)
from flightledger.adapters.base import Adapter
from flightledger.bus import FanoutBus, InMemoryBus, build_transport_bus_from_env


@dataclass(frozen=True)
class SourceChannel:
    channel_id: str
    name: str
    protocol: str
    data_format: str
    filename: str
    adapter_cls: type[Adapter]


SOURCE_CHANNELS = [
    SourceChannel(
        channel_id="reservation_pss",
        name="Reservation (PSS)",
        protocol="SFTP Batch",
        data_format="CSV",
        filename="pss_tickets.csv",
        adapter_cls=PssCsvAdapter,
    ),
    SourceChannel(
        channel_id="departure_control_dcs",
        name="Departure Control (DCS)",
        protocol="WebSocket Streaming",
        data_format="JSON",
        filename="dcs_coupon_flown.json",
        adapter_cls=DcsStreamAdapter,
    ),
    SourceChannel(
        channel_id="gds_agent_settlement",
        name="GDS/Agent Settlements",
        protocol="SFTP",
        data_format="XML",
        filename="gds_settlements.xml",
        adapter_cls=GdsXmlAdapter,
    ),
    SourceChannel(
        channel_id="ota_partners",
        name="OTA Partners",
        protocol="REST + Webhook",
        data_format="JSON",
        filename="ota_webhook.json",
        adapter_cls=OtaWebhookAdapter,
    ),
    SourceChannel(
        channel_id="interline_partners",
        name="Interline Partners",
        protocol="REST API",
        data_format="JSON",
        filename="interline_claims.json",
        adapter_cls=InterlineRestAdapter,
    ),
]


def ingest_demo(data_dir: Path) -> tuple[InMemoryBus, list[dict[str, Any]]]:
    snapshot_bus = InMemoryBus()
    transport_bus = build_transport_bus_from_env()
    bus = snapshot_bus if transport_bus is None else FanoutBus([snapshot_bus, transport_bus])
    channels: list[dict[str, Any]] = []

    try:
        for source in SOURCE_CHANNELS:
            file_path = data_dir / source.filename
            payload = file_path.read_text(encoding="utf-8")
            adapter = source.adapter_cls()
            events = adapter.parse(payload)
            bus.publish_many(events)
            channels.append(
                {
                    "channel_id": source.channel_id,
                    "name": source.name,
                    "protocol": source.protocol,
                    "format": source.data_format,
                    "file_name": source.filename,
                    "record_count": len(events),
                    "raw_payload": payload,
                }
            )
    finally:
        close = getattr(bus, "close", None)
        if callable(close):
            close()

    return snapshot_bus, channels


def run_demo(data_dir: Path) -> InMemoryBus:
    bus, _channels = ingest_demo(data_dir)
    return bus


if __name__ == "__main__":
    data = Path(__file__).resolve().parents[2] / "data" / "mock"
    demo_bus = run_demo(data)
    for topic, events in sorted(demo_bus.topics.items()):
        print(f"{topic}: {len(events)} event(s)")

from pathlib import Path

from flightledger.adapters import (
    DcsStreamAdapter,
    GdsXmlAdapter,
    InterlineRestAdapter,
    OtaWebhookAdapter,
    PssCsvAdapter,
)
from flightledger.models.canonical import CanonicalEventType, SourceSystem


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "mock"


def test_pss_csv_adapter_parses_ticket_events() -> None:
    payload = (DATA_DIR / "pss_tickets.csv").read_text(encoding="utf-8")
    events = PssCsvAdapter().parse(payload)
    assert len(events) == 200
    assert events[0].source_system == SourceSystem.PSS
    assert events[0].event_type == CanonicalEventType.TICKET_ISSUED
    assert events[1].event_type == CanonicalEventType.TICKET_REISSUED


def test_dcs_stream_adapter_parses_coupon_flown() -> None:
    payload = (DATA_DIR / "dcs_coupon_flown.json").read_text(encoding="utf-8")
    events = DcsStreamAdapter().parse(payload)
    assert len(events) == 100
    assert events[0].source_system == SourceSystem.DCS
    assert events[0].event_type == CanonicalEventType.COUPON_FLOWN


def test_gds_xml_adapter_parses_settlement_due() -> None:
    payload = (DATA_DIR / "gds_settlements.xml").read_text(encoding="utf-8")
    events = GdsXmlAdapter().parse(payload)
    assert len(events) == 100
    assert events[0].source_system == SourceSystem.GDS
    assert events[0].event_type == CanonicalEventType.SETTLEMENT_DUE


def test_ota_webhook_adapter_parses_booking_modified() -> None:
    payload = (DATA_DIR / "ota_webhook.json").read_text(encoding="utf-8")
    events = OtaWebhookAdapter().parse(payload)
    assert len(events) == 100
    assert events[0].source_system == SourceSystem.OTA
    assert events[0].event_type == CanonicalEventType.BOOKING_MODIFIED


def test_interline_adapter_parses_claims() -> None:
    payload = (DATA_DIR / "interline_claims.json").read_text(encoding="utf-8")
    events = InterlineRestAdapter().parse(payload)
    assert len(events) == 100
    assert events[0].source_system == SourceSystem.INTERLINE
    assert events[0].event_type == CanonicalEventType.INTERLINE_CLAIM

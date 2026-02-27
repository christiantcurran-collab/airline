from datetime import datetime, timezone
from decimal import Decimal

from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem
from flightledger.stores.ticket_lifecycle import TicketLifecycleStore


def _event(event_id: str, event_type: CanonicalEventType, occurred_at: datetime) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        occurred_at=occurred_at,
        source_system=SourceSystem.PSS if event_type != CanonicalEventType.COUPON_FLOWN else SourceSystem.DCS,
        event_type=event_type,
        ticket_number="125000000001",
        coupon_number=1,
        gross_amount=Decimal("100.00"),
        currency="USD",
    )


def test_ticket_store_replays_current_state() -> None:
    store = TicketLifecycleStore()
    store.reset()
    store.append(_event("evt-1", CanonicalEventType.TICKET_ISSUED, datetime(2026, 3, 1, tzinfo=timezone.utc)))
    store.append(_event("evt-2", CanonicalEventType.TICKET_REISSUED, datetime(2026, 3, 2, tzinfo=timezone.utc)))
    store.append(_event("evt-3", CanonicalEventType.COUPON_FLOWN, datetime(2026, 3, 3, tzinfo=timezone.utc)))

    state = store.get_current_state("125000000001")
    assert state.status == "flown"
    assert state.event_count == 3
    assert state.coupon_statuses[1] == "flown"


def test_ticket_store_state_at_timestamp() -> None:
    store = TicketLifecycleStore()
    store.reset()
    store.append(_event("evt-a", CanonicalEventType.TICKET_ISSUED, datetime(2026, 3, 1, tzinfo=timezone.utc)))
    store.append(_event("evt-b", CanonicalEventType.TICKET_REISSUED, datetime(2026, 3, 2, tzinfo=timezone.utc)))
    store.append(_event("evt-c", CanonicalEventType.COUPON_FLOWN, datetime(2026, 3, 3, tzinfo=timezone.utc)))

    state = store.get_state_at("125000000001", datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc))
    assert state.status == "reissued"
    assert state.event_count == 2


def test_ticket_store_duplicate_event_is_idempotent() -> None:
    store = TicketLifecycleStore()
    store.reset()
    event = _event("evt-x", CanonicalEventType.TICKET_ISSUED, datetime(2026, 3, 1, tzinfo=timezone.utc))
    store.append(event)
    store.append(event)
    history = store.get_history("125000000001")
    assert len(history) == 1


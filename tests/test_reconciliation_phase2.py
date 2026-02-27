from datetime import datetime, timezone
from decimal import Decimal

from flightledger.matching.coupon_matcher import CouponMatcher
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem
from flightledger.recon.reconciliation import ReconciliationEngine
from flightledger.stores.ticket_lifecycle import TicketLifecycleStore


def _event(
    event_id: str,
    event_type: CanonicalEventType,
    source: SourceSystem,
    ticket: str,
    amount: Decimal | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        occurred_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        source_system=source,
        event_type=event_type,
        ticket_number=ticket,
        coupon_number=1,
        gross_amount=amount,
    )


def test_reconciliation_matched_flow() -> None:
    store = TicketLifecycleStore()
    store.reset()
    store.append(_event("i1", CanonicalEventType.TICKET_ISSUED, SourceSystem.PSS, "125000000301", Decimal("100")))
    store.append(_event("f1", CanonicalEventType.COUPON_FLOWN, SourceSystem.DCS, "125000000301"))
    store.append(
        _event("s1", CanonicalEventType.SETTLEMENT_DUE, SourceSystem.GDS, "125000000301", Decimal("100.00"))
    )

    engine = ReconciliationEngine(store, CouponMatcher(store))
    summary = engine.run_full_recon()
    assert summary.total_matched == 1
    assert summary.total_breaks == 0


def test_reconciliation_fare_mismatch_break() -> None:
    store = TicketLifecycleStore()
    store.reset()
    store.append(_event("i2", CanonicalEventType.TICKET_ISSUED, SourceSystem.PSS, "125000000302", Decimal("100")))
    store.append(_event("f2", CanonicalEventType.COUPON_FLOWN, SourceSystem.DCS, "125000000302"))
    store.append(
        _event("s2", CanonicalEventType.SETTLEMENT_DUE, SourceSystem.GDS, "125000000302", Decimal("95.00"))
    )

    engine = ReconciliationEngine(store, CouponMatcher(store))
    engine.run_full_recon()
    breaks = engine.get_breaks(status="unresolved", break_type="fare_mismatch")
    assert len(breaks) == 1


def test_reconciliation_missing_settlement_break() -> None:
    store = TicketLifecycleStore()
    store.reset()
    store.append(_event("i3", CanonicalEventType.TICKET_ISSUED, SourceSystem.PSS, "125000000303", Decimal("120")))
    store.append(_event("f3", CanonicalEventType.COUPON_FLOWN, SourceSystem.DCS, "125000000303"))

    engine = ReconciliationEngine(store, CouponMatcher(store))
    engine.run_full_recon()
    breaks = engine.get_breaks(status="unresolved", break_type="missing_settlement")
    assert len(breaks) == 1


def test_reconciliation_rounding_tolerance_auto_resolved() -> None:
    store = TicketLifecycleStore()
    store.reset()
    store.append(_event("i4", CanonicalEventType.TICKET_ISSUED, SourceSystem.PSS, "125000000304", Decimal("100.000")))
    store.append(_event("f4", CanonicalEventType.COUPON_FLOWN, SourceSystem.DCS, "125000000304"))
    store.append(
        _event("s4", CanonicalEventType.SETTLEMENT_DUE, SourceSystem.GDS, "125000000304", Decimal("99.995"))
    )

    engine = ReconciliationEngine(store, CouponMatcher(store))
    summary = engine.run_full_recon()
    assert summary.total_matched == 1
    assert summary.total_breaks == 0


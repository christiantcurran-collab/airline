from datetime import datetime, timezone

from flightledger.matching.coupon_matcher import CouponMatcher
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem
from flightledger.stores.ticket_lifecycle import TicketLifecycleStore


def _issued(ticket: str, coupon: int) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=f"iss-{ticket}-{coupon}",
        occurred_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        source_system=SourceSystem.PSS,
        event_type=CanonicalEventType.TICKET_ISSUED,
        ticket_number=ticket,
        coupon_number=coupon,
    )


def _flown(ticket: str, coupon: int) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=f"flw-{ticket}-{coupon}",
        occurred_at=datetime(2026, 3, 2, tzinfo=timezone.utc),
        source_system=SourceSystem.DCS,
        event_type=CanonicalEventType.COUPON_FLOWN,
        ticket_number=ticket,
        coupon_number=coupon,
    )


def test_coupon_matcher_all_matched() -> None:
    store = TicketLifecycleStore()
    store.reset()
    for index in range(1, 6):
        ticket = f"1250000000{index:02d}"
        store.append(_issued(ticket, 1))
        store.append(_flown(ticket, 1))

    matcher = CouponMatcher(store)
    result = matcher.run_matching()
    assert result.matched == 5
    assert result.unmatched_issued == 0
    assert result.unmatched_flown == 0


def test_coupon_matcher_unmatched_issued() -> None:
    store = TicketLifecycleStore()
    store.reset()
    for index in range(1, 6):
        ticket = f"1250000001{index:02d}"
        store.append(_issued(ticket, 1))
        if index <= 3:
            store.append(_flown(ticket, 1))

    matcher = CouponMatcher(store)
    result = matcher.run_matching()
    assert result.matched == 3
    assert result.unmatched_issued == 2
    assert result.unmatched_flown == 0


def test_coupon_matcher_unmatched_flown() -> None:
    store = TicketLifecycleStore()
    store.reset()
    for index in range(1, 6):
        ticket = f"1250000002{index:02d}"
        if index <= 3:
            store.append(_issued(ticket, 1))
        store.append(_flown(ticket, 1))

    matcher = CouponMatcher(store)
    result = matcher.run_matching()
    assert result.matched == 3
    assert result.unmatched_issued == 0
    assert result.unmatched_flown == 2


def test_coupon_matcher_age_suspense() -> None:
    store = TicketLifecycleStore()
    store.reset()
    store.append(_issued("125999999001", 1))

    matcher = CouponMatcher(store)
    matcher.run_matching()
    matcher.age_suspense()
    matcher.age_suspense()
    suspense_items = matcher.get_suspense_items()

    assert len(suspense_items) == 1
    assert suspense_items[0]["days_in_suspense"] == 2


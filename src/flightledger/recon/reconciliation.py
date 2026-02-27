from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flightledger.db.repositories import ReconRepository
from flightledger.matching.coupon_matcher import CouponMatcher
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType
from flightledger.stores.ticket_lifecycle import TicketLifecycleStore


@dataclass
class BreakClassification:
    break_type: str | None
    severity: str
    status: str
    resolution: str


@dataclass
class ReconSummary:
    total_matched: int
    total_breaks: int
    breaks_by_type: dict[str, int]
    breaks_by_severity: dict[str, int]


class ReconciliationEngine:
    def __init__(
        self,
        ticket_store: TicketLifecycleStore,
        matcher: CouponMatcher,
        repository: ReconRepository | None = None,
    ) -> None:
        self.ticket_store = ticket_store
        self.matcher = matcher
        self.repository = repository or ReconRepository()

    def reset(self) -> None:
        self.repository.reset()

    def classify_break(
        self,
        ticket_number: str,
        our_amount: Decimal | None,
        their_amount: Decimal | None,
        flown_exists: bool = True,
        duplicate_lift: bool = False,
        settlement_exists: bool = True,
    ) -> BreakClassification:
        if duplicate_lift:
            return BreakClassification("duplicate_lift", "high", "break", "unresolved")
        if not flown_exists:
            return BreakClassification("timing", "low", "break", "unresolved")
        if not settlement_exists:
            return BreakClassification("missing_settlement", "high", "break", "unresolved")
        if our_amount is None or their_amount is None:
            return BreakClassification("missing_settlement", "high", "break", "unresolved")

        difference = (our_amount - their_amount).copy_abs()
        if difference < Decimal("0.01"):
            return BreakClassification(None, "low", "matched", "auto_resolved")
        severity = "high" if difference >= Decimal("10") else "medium"
        return BreakClassification("fare_mismatch", severity, "break", "unresolved")

    def run_full_recon(self) -> ReconSummary:
        self.repository.reset()
        self.matcher.run_matching()
        now_iso = datetime.now(timezone.utc).isoformat()

        issued_events = self.ticket_store.get_events_by_type(
            [CanonicalEventType.TICKET_ISSUED, CanonicalEventType.TICKET_REISSUED]
        )
        flown_events = self.ticket_store.get_events_by_type([CanonicalEventType.COUPON_FLOWN])
        settlement_events = self.ticket_store.get_events_by_type(
            [CanonicalEventType.SETTLEMENT_DUE, CanonicalEventType.INTERLINE_CLAIM]
        )

        issued_by_key = {(evt.ticket_number, evt.coupon_number): evt for evt in issued_events if evt.coupon_number is not None}
        flown_by_key = defaultdict(list)
        for event in flown_events:
            if event.coupon_number is not None:
                flown_by_key[(event.ticket_number, event.coupon_number)].append(event)
        settlement_by_key = {
            (evt.ticket_number, evt.coupon_number): evt for evt in settlement_events if evt.coupon_number is not None
        }

        total_matched = 0
        total_breaks = 0
        breaks_by_type: Counter[str] = Counter()
        breaks_by_severity: Counter[str] = Counter()

        for key, issued in issued_by_key.items():
            flown_list = flown_by_key.get(key, [])
            flown = flown_list[0] if flown_list else None
            settlement = settlement_by_key.get(key)
            duplicate_lift = len(flown_list) > 1

            our_amount = issued.gross_amount
            their_amount = settlement.gross_amount if settlement else None
            classification = self.classify_break(
                ticket_number=issued.ticket_number,
                our_amount=our_amount,
                their_amount=their_amount,
                flown_exists=bool(flown),
                duplicate_lift=duplicate_lift,
                settlement_exists=settlement is not None,
            )
            difference = None
            if our_amount is not None and their_amount is not None:
                difference = our_amount - their_amount

            row = {
                "id": str(uuid4()),
                "ticket_number": issued.ticket_number,
                "coupon_number": issued.coupon_number,
                "recon_type": "three_way",
                "status": classification.status,
                "break_type": classification.break_type,
                "severity": classification.severity,
                "our_amount": float(our_amount) if our_amount is not None else None,
                "their_amount": float(their_amount) if their_amount is not None else None,
                "difference": float(difference) if difference is not None else None,
                "resolution": classification.resolution,
                "resolution_notes": "Rounded below tolerance." if classification.resolution == "auto_resolved" else None,
                "created_at": now_iso,
                "resolved_at": now_iso if classification.resolution == "auto_resolved" else None,
            }
            self.repository.insert(row)

            if classification.status == "matched":
                total_matched += 1
            else:
                total_breaks += 1
                if classification.break_type:
                    breaks_by_type[classification.break_type] += 1
                breaks_by_severity[classification.severity] += 1

        return ReconSummary(
            total_matched=total_matched,
            total_breaks=total_breaks,
            breaks_by_type=dict(breaks_by_type),
            breaks_by_severity=dict(breaks_by_severity),
        )

    def get_breaks(self, status: str = "unresolved", break_type: str | None = None) -> list[dict[str, Any]]:
        return self.repository.get_breaks(status=status, break_type=break_type)

    def resolve_break(self, break_id: str, resolution: str, notes: str) -> None:
        self.repository.resolve(break_id, resolution, notes)


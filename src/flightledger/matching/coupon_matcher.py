from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flightledger.db.repositories import CouponMatchRepository
from flightledger.models.canonical import CanonicalEventType
from flightledger.stores.ticket_lifecycle import TicketLifecycleStore


@dataclass
class MatchResult:
    matched: int
    unmatched_issued: int
    unmatched_flown: int


class CouponMatcher:
    def __init__(
        self,
        ticket_store: TicketLifecycleStore,
        repository: CouponMatchRepository | None = None,
    ) -> None:
        self.ticket_store = ticket_store
        self.repository = repository or CouponMatchRepository()

    def reset(self) -> None:
        self.repository.reset()

    def run_matching(self) -> MatchResult:
        self.repository.reset()
        issued_events = self.ticket_store.get_events_by_type(
            [CanonicalEventType.TICKET_ISSUED, CanonicalEventType.TICKET_REISSUED]
        )
        flown_events = self.ticket_store.get_events_by_type([CanonicalEventType.COUPON_FLOWN])

        issued_by_key: dict[tuple[str, int], Any] = {}
        flown_by_key: dict[tuple[str, int], Any] = {}

        for event in issued_events:
            if event.coupon_number is None:
                continue
            issued_by_key[(event.ticket_number, event.coupon_number)] = event

        for event in flown_events:
            if event.coupon_number is None:
                continue
            flown_by_key[(event.ticket_number, event.coupon_number)] = event

        matched = 0
        unmatched_issued = 0
        unmatched_flown = 0

        all_keys = set(issued_by_key.keys()) | set(flown_by_key.keys())
        for ticket_number, coupon_number in sorted(all_keys):
            issued = issued_by_key.get((ticket_number, coupon_number))
            flown = flown_by_key.get((ticket_number, coupon_number))
            status = "matched"
            if issued and flown:
                matched += 1
            elif issued and not flown:
                status = "unmatched_issued"
                unmatched_issued += 1
            else:
                status = "unmatched_flown"
                unmatched_flown += 1

            row = {
                "ticket_number": ticket_number,
                "coupon_number": coupon_number,
                "status": status,
                "issued_event_id": self.ticket_store.get_persisted_event_row_id(issued.event_id) if issued else None,
                "flown_event_id": self.ticket_store.get_persisted_event_row_id(flown.event_id) if flown else None,
                "issued_at": issued.occurred_at.isoformat() if issued else None,
                "flown_at": flown.occurred_at.isoformat() if flown else None,
                "matched_at": datetime.now(timezone.utc).isoformat() if status == "matched" else None,
                "days_in_suspense": 0,
                "notes": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.repository.upsert(row)

        for row in self.repository.all_rows():
            if row["status"] in {"unmatched_issued", "unmatched_flown"} and int(row.get("days_in_suspense", 0)) > 30:
                row["status"] = "suspense"
                self.repository.upsert(row)

        return MatchResult(
            matched=matched,
            unmatched_issued=unmatched_issued,
            unmatched_flown=unmatched_flown,
        )

    def get_suspense_items(self, min_age_days: int = 0) -> list[dict[str, Any]]:
        rows = self.repository.get_suspense(min_age_days)
        return sorted(rows, key=lambda row: int(row.get("days_in_suspense", 0)), reverse=True)

    def age_suspense(self) -> int:
        aged = 0
        for row in self.repository.all_rows():
            if row["status"] in {"unmatched_issued", "unmatched_flown", "suspense"}:
                row["days_in_suspense"] = int(row.get("days_in_suspense", 0)) + 1
                if row["days_in_suspense"] > 30:
                    row["status"] = "suspense"
                if row["days_in_suspense"] > 90:
                    row["notes"] = "Escalation required (>90 days)."
                row["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.repository.upsert(row)
                aged += 1
        return aged

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flightledger.db.repositories import TicketCurrentStateRepository, TicketEventRepository
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType


@dataclass
class TicketState:
    ticket_number: str
    status: str = "unknown"
    current_amount: Decimal | None = None
    coupon_statuses: dict[int, str] = field(default_factory=dict)
    last_modified: datetime | None = None
    pnr: str | None = None
    passenger_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    currency: str | None = None
    event_count: int = 0
    last_event_type: str | None = None


def _to_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _event_from_row(row: dict[str, Any]) -> CanonicalEvent:
    payload = row["payload"]
    payload = {**payload}
    payload.setdefault("event_id", str(payload.get("event_id") or row.get("id") or uuid4()))
    payload.setdefault("occurred_at", row.get("occurred_at"))
    return CanonicalEvent.model_validate(payload)


def _state_from_row(row: dict[str, Any]) -> TicketState:
    coupon_statuses = row.get("coupon_statuses") or {}
    normalized_coupon_statuses = {int(key): value for key, value in coupon_statuses.items()}
    last_modified = row.get("last_modified")
    return TicketState(
        ticket_number=row["ticket_number"],
        status=row.get("status", "unknown"),
        current_amount=Decimal(str(row["gross_amount"])) if row.get("gross_amount") is not None else None,
        coupon_statuses=normalized_coupon_statuses,
        last_modified=_to_datetime(last_modified) if last_modified else None,
        pnr=row.get("pnr"),
        passenger_name=row.get("passenger_name"),
        origin=row.get("origin"),
        destination=row.get("destination"),
        currency=row.get("currency"),
        event_count=int(row.get("event_count", 0)),
        last_event_type=row.get("last_event_type"),
    )


class TicketLifecycleStore:
    def __init__(
        self,
        event_repository: TicketEventRepository | None = None,
        state_repository: TicketCurrentStateRepository | None = None,
    ) -> None:
        self.event_repository = event_repository or TicketEventRepository()
        self.state_repository = state_repository or TicketCurrentStateRepository()

    def reset(self) -> None:
        self.event_repository.reset()
        self.state_repository.reset()

    def append(self, event: CanonicalEvent) -> None:
        existing = self.event_repository.find_by_event_id(event.event_id)
        if existing:
            return

        sequence = self.event_repository.next_sequence(event.ticket_number)
        row = {
            "id": str(uuid4()),
            "ticket_number": event.ticket_number,
            "event_sequence": sequence,
            "event_type": event.event_type.value,
            "source_system": event.source_system.value,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.model_dump(mode="json"),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        self.event_repository.insert(row)
        current_state = self._replay(self.event_repository.get_by_ticket(event.ticket_number), event.ticket_number)
        self.state_repository.upsert(self._to_state_row(current_state))

    def get_history(self, ticket_number: str) -> list[CanonicalEvent]:
        rows = self.event_repository.get_by_ticket(ticket_number)
        return [_event_from_row(row) for row in rows]

    def get_current_state(self, ticket_number: str) -> TicketState:
        snapshot = self.state_repository.get(ticket_number)
        if snapshot:
            return _state_from_row(snapshot)
        rows = self.event_repository.get_by_ticket(ticket_number)
        return self._replay(rows, ticket_number)

    def get_state_at(self, ticket_number: str, as_of: datetime) -> TicketState:
        rows = self.event_repository.get_by_ticket_at(ticket_number, as_of)
        return self._replay(rows, ticket_number)

    def get_events_by_type(self, event_types: list[CanonicalEventType]) -> list[CanonicalEvent]:
        rows = self.event_repository.get_by_event_types([item.value for item in event_types])
        return [_event_from_row(row) for row in rows]

    def all_events(self) -> list[CanonicalEvent]:
        rows = self.event_repository.all_rows()
        return [_event_from_row(row) for row in rows]

    def _replay(self, rows: list[dict[str, Any]], ticket_number: str) -> TicketState:
        state = TicketState(ticket_number=ticket_number)
        for row in rows:
            event = _event_from_row(row)
            state.event_count += 1
            state.last_event_type = event.event_type.value
            state.last_modified = event.occurred_at
            state.pnr = event.pnr or state.pnr
            state.passenger_name = event.passenger_name or state.passenger_name
            state.origin = event.origin or state.origin
            state.destination = event.destination or state.destination
            state.currency = event.currency or state.currency
            if event.gross_amount is not None:
                state.current_amount = event.gross_amount
            if event.coupon_number is not None and event.event_type in {
                CanonicalEventType.TICKET_ISSUED,
                CanonicalEventType.TICKET_REISSUED,
            }:
                state.coupon_statuses[event.coupon_number] = "issued"
            if event.event_type == CanonicalEventType.TICKET_ISSUED:
                state.status = "issued"
            elif event.event_type == CanonicalEventType.TICKET_REISSUED:
                state.status = "reissued"
            elif event.event_type == CanonicalEventType.TICKET_VOIDED:
                state.status = "voided"
            elif event.event_type == CanonicalEventType.COUPON_FLOWN:
                state.status = "flown"
                if event.coupon_number is not None:
                    state.coupon_statuses[event.coupon_number] = "flown"
            elif event.event_type == CanonicalEventType.REFUND_REQUESTED:
                state.status = "refunded"
            elif event.event_type == CanonicalEventType.BOOKING_MODIFIED and state.status == "unknown":
                state.status = "modified"
        return state

    @staticmethod
    def _to_state_row(state: TicketState) -> dict[str, Any]:
        return {
            "ticket_number": state.ticket_number,
            "status": state.status,
            "pnr": state.pnr,
            "passenger_name": state.passenger_name,
            "origin": state.origin,
            "destination": state.destination,
            "gross_amount": float(state.current_amount) if state.current_amount is not None else None,
            "currency": state.currency,
            "event_count": state.event_count,
            "last_event_type": state.last_event_type,
            "last_modified": state.last_modified.isoformat() if state.last_modified else None,
            "coupon_statuses": {str(key): value for key, value in state.coupon_statuses.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


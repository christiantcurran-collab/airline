from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from flightledger.db.repositories import AuditRepository


@dataclass
class AuditRecord:
    id: str
    timestamp: str
    action: str
    component: str
    ticket_number: str | None
    input_event_ids: list[str]
    output_reference: str | None
    detail: dict[str, Any]
    raw_source_hash: str | None


class AuditStore:
    def __init__(self, repository: AuditRepository | None = None) -> None:
        self.repository = repository or AuditRepository()

    def reset(self) -> None:
        self.repository.reset()

    def log(
        self,
        action: str,
        component: str,
        ticket_number: str | None = None,
        input_event_ids: list[str] | None = None,
        output_reference: str | None = None,
        detail: dict[str, Any] | None = None,
        raw_source_hash: str | None = None,
    ) -> AuditRecord:
        row = {
            "id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "component": component,
            "ticket_number": ticket_number,
            "input_event_ids": input_event_ids or [],
            "output_reference": output_reference,
            "detail": detail or {},
            "raw_source_hash": raw_source_hash,
        }
        stored = self.repository.insert(row)
        return AuditRecord(**stored)

    def get_lineage(self, output_reference: str) -> list[AuditRecord]:
        rows = self.repository.get_by_output_reference(output_reference)
        return [AuditRecord(**row) for row in rows]

    def get_history(self, ticket_number: str) -> list[AuditRecord]:
        rows = self.repository.get_by_ticket(ticket_number)
        return [AuditRecord(**row) for row in rows]


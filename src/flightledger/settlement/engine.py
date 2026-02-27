from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flightledger.audit.lineage import AuditStore
from flightledger.db.repositories import SettlementRepository


@dataclass
class Settlement:
    id: str
    ticket_number: str
    counterparty: str
    counterparty_type: str
    our_amount: Decimal
    their_amount: Decimal | None
    currency: str
    status: str
    created_at: str
    updated_at: str


class SettlementEngine:
    def __init__(self, repository: SettlementRepository | None = None, audit_store: AuditStore | None = None) -> None:
        self.repository = repository or SettlementRepository()
        self.audit_store = audit_store

    def reset(self) -> None:
        self.repository.reset()

    def calculate(self, ticket_number: str, counterparty: str, our_amount: Decimal) -> Settlement:
        now = datetime.now(timezone.utc).isoformat()
        row = self.repository.insert(
            {
                "id": str(uuid4()),
                "ticket_number": ticket_number,
                "counterparty": counterparty,
                "counterparty_type": "interline_partner",
                "our_amount": float(our_amount),
                "their_amount": None,
                "currency": "USD",
                "status": "calculated",
                "created_at": now,
                "updated_at": now,
            }
        )
        self._log_transition(row["id"], "none", "calculated", "calculate", {"our_amount": str(our_amount)})
        return self._to_settlement(row)

    def validate(self, settlement_id: str) -> Settlement:
        settlement = self._require(settlement_id)
        if settlement["status"] != "calculated":
            raise ValueError("Invalid transition: only 'calculated' can be validated")
        if Decimal(str(settlement["our_amount"])) <= 0:
            return self._to_settlement(settlement)
        self.repository.update_status(settlement_id, "validated")
        self._log_transition(settlement_id, "calculated", "validated", "validate", {})
        return self._to_settlement(self._require(settlement_id))

    def submit(self, settlement_id: str) -> Settlement:
        settlement = self._require(settlement_id)
        if settlement["status"] != "validated":
            raise ValueError("Invalid transition: only 'validated' can be submitted")
        self.repository.update_status(settlement_id, "submitted")
        self._log_transition(settlement_id, "validated", "submitted", "submit", {})
        return self._to_settlement(self._require(settlement_id))

    def confirm(self, settlement_id: str, their_amount: Decimal) -> Settlement:
        settlement = self._require(settlement_id)
        if settlement["status"] != "submitted":
            raise ValueError("Invalid transition: only 'submitted' can be confirmed")
        our_amount = Decimal(str(settlement["our_amount"]))
        status = "confirmed" if (our_amount - their_amount).copy_abs() < Decimal("0.01") else "disputed"
        self.repository.update_status(settlement_id, status, {"their_amount": float(their_amount)})
        self._log_transition(
            settlement_id,
            "submitted",
            status,
            "confirm",
            {"our_amount": str(our_amount), "their_amount": str(their_amount)},
        )
        return self._to_settlement(self._require(settlement_id))

    def reconcile(self, settlement_id: str) -> Settlement:
        settlement = self._require(settlement_id)
        if settlement["status"] != "confirmed":
            raise ValueError("Invalid transition: only 'confirmed' can be reconciled")
        self.repository.update_status(settlement_id, "reconciled")
        self._log_transition(settlement_id, "confirmed", "reconciled", "reconcile", {})
        return self._to_settlement(self._require(settlement_id))

    def compensate(self, settlement_id: str, reason: str) -> Settlement:
        settlement = self._require(settlement_id)
        if settlement["status"] == "compensated":
            return self._to_settlement(settlement)
        from_status = settlement["status"]
        self.repository.update_status(settlement_id, "compensated")
        self._log_transition(settlement_id, from_status, "compensated", "compensate", {"reason": reason})
        return self._to_settlement(self._require(settlement_id))

    def list_settlements(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = self.repository.list_all()
        if status:
            rows = [row for row in rows if row["status"] == status]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return rows

    def get_saga(self, settlement_id: str) -> list[dict[str, Any]]:
        return self.repository.get_saga_log(settlement_id)

    def _require(self, settlement_id: str) -> dict[str, Any]:
        row = self.repository.get(settlement_id)
        if not row:
            raise KeyError("Settlement not found")
        return row

    def _log_transition(
        self,
        settlement_id: str,
        from_status: str,
        to_status: str,
        action: str,
        detail: dict[str, Any],
    ) -> None:
        row = {
            "id": str(uuid4()),
            "settlement_id": settlement_id,
            "from_status": from_status,
            "to_status": to_status,
            "action": action,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.repository.insert_saga(row)
        if self.audit_store:
            self.audit_store.log(
                action=f"settlement_{action}",
                component="settlement_engine",
                output_reference=settlement_id,
                detail={"from_status": from_status, "to_status": to_status, **detail},
            )

    @staticmethod
    def _to_settlement(row: dict[str, Any]) -> Settlement:
        return Settlement(
            id=row["id"],
            ticket_number=row["ticket_number"],
            counterparty=row["counterparty"],
            counterparty_type=row["counterparty_type"],
            our_amount=Decimal(str(row["our_amount"])),
            their_amount=Decimal(str(row["their_amount"])) if row.get("their_amount") is not None else None,
            currency=row["currency"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


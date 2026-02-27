from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from flightledger.db.supabase_client import get_client


class StorageBackend(str, Enum):
    MEMORY = "memory"
    SUPABASE = "supabase"


def get_storage_backend() -> StorageBackend:
    raw = os.getenv("FLIGHTLEDGER_STORAGE_BACKEND", StorageBackend.MEMORY.value).strip().lower()
    if raw == StorageBackend.SUPABASE.value:
        return StorageBackend.SUPABASE
    return StorageBackend.MEMORY


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _MemoryState:
    ticket_events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ticket_current_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    coupon_matches: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)
    recon_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    dag_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    settlements: dict[str, dict[str, Any]] = field(default_factory=dict)
    settlement_saga_log: list[dict[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        self.ticket_events.clear()
        self.ticket_current_state.clear()
        self.coupon_matches.clear()
        self.recon_results.clear()
        self.audit_log.clear()
        self.dag_runs.clear()
        self.task_runs.clear()
        self.settlements.clear()
        self.settlement_saga_log.clear()


_MEMORY_STATE = _MemoryState()


class _BaseRepository:
    def __init__(self) -> None:
        self.backend = get_storage_backend()
        self.client = get_client() if self.backend == StorageBackend.SUPABASE else None


class TicketEventRepository(_BaseRepository):
    def reset(self) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.ticket_events.clear()
            return
        self.client.table("ticket_events").delete().neq("ticket_number", "").execute()

    def next_sequence(self, ticket_number: str) -> int:
        if self.backend == StorageBackend.MEMORY:
            history = _MEMORY_STATE.ticket_events.get(ticket_number, [])
            return len(history) + 1
        response = (
            self.client.table("ticket_events")
            .select("event_sequence")
            .eq("ticket_number", ticket_number)
            .order("event_sequence", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return 1
        return int(rows[0]["event_sequence"]) + 1

    def find_by_event_id(self, event_id: str) -> dict[str, Any] | None:
        if self.backend == StorageBackend.MEMORY:
            for rows in _MEMORY_STATE.ticket_events.values():
                for row in rows:
                    if row["payload"].get("event_id") == event_id:
                        return row
            return None
        response = (
            self.client.table("ticket_events")
            .select("*")
            .contains("payload", {"event_id": event_id})
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            ticket = row["ticket_number"]
            history = _MEMORY_STATE.ticket_events.setdefault(ticket, [])
            if any(existing["event_sequence"] == row["event_sequence"] for existing in history):
                raise ValueError("Duplicate ticket_number + event_sequence")
            history.append(row)
            history.sort(key=lambda item: item["event_sequence"])
            return row
        response = self.client.table("ticket_events").insert(row).execute()
        return (response.data or [row])[0]

    def get_by_ticket(self, ticket_number: str) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return list(_MEMORY_STATE.ticket_events.get(ticket_number, []))
        response = (
            self.client.table("ticket_events")
            .select("*")
            .eq("ticket_number", ticket_number)
            .order("event_sequence")
            .execute()
        )
        return response.data or []

    def get_by_ticket_at(self, ticket_number: str, as_of: datetime) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            cutoff = as_of.isoformat()
            return [
                row
                for row in _MEMORY_STATE.ticket_events.get(ticket_number, [])
                if row["occurred_at"] <= cutoff
            ]
        response = (
            self.client.table("ticket_events")
            .select("*")
            .eq("ticket_number", ticket_number)
            .lte("occurred_at", as_of.isoformat())
            .order("event_sequence")
            .execute()
        )
        return response.data or []

    def get_by_event_types(self, event_types: list[str]) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            rows: list[dict[str, Any]] = []
            for ticket_rows in _MEMORY_STATE.ticket_events.values():
                rows.extend([row for row in ticket_rows if row["event_type"] in event_types])
            return rows
        response = self.client.table("ticket_events").select("*").in_("event_type", event_types).execute()
        return response.data or []

    def all_rows(self) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            rows: list[dict[str, Any]] = []
            for ticket_rows in _MEMORY_STATE.ticket_events.values():
                rows.extend(ticket_rows)
            return rows
        response = self.client.table("ticket_events").select("*").execute()
        return response.data or []


class TicketCurrentStateRepository(_BaseRepository):
    def reset(self) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.ticket_current_state.clear()
            return
        self.client.table("ticket_current_state").delete().neq("ticket_number", "").execute()

    def upsert(self, row: dict[str, Any]) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.ticket_current_state[row["ticket_number"]] = row
            return
        self.client.table("ticket_current_state").upsert(row, on_conflict="ticket_number").execute()

    def get(self, ticket_number: str) -> dict[str, Any] | None:
        if self.backend == StorageBackend.MEMORY:
            return _MEMORY_STATE.ticket_current_state.get(ticket_number)
        response = (
            self.client.table("ticket_current_state")
            .select("*")
            .eq("ticket_number", ticket_number)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None


class CouponMatchRepository(_BaseRepository):
    def reset(self) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.coupon_matches.clear()
            return
        self.client.table("coupon_matches").delete().neq("ticket_number", "").execute()

    def upsert(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            key = (row["ticket_number"], int(row["coupon_number"]))
            if "id" not in row:
                row = {**row, "id": str(uuid4())}
            _MEMORY_STATE.coupon_matches[key] = row
            return row
        response = self.client.table("coupon_matches").upsert(row, on_conflict="ticket_number,coupon_number").execute()
        return (response.data or [row])[0]

    def all_rows(self) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return list(_MEMORY_STATE.coupon_matches.values())
        response = self.client.table("coupon_matches").select("*").execute()
        return response.data or []

    def get_suspense(self, min_age: int) -> list[dict[str, Any]]:
        rows = self.all_rows()
        return [
            row
            for row in rows
            if row["status"] in {"suspense", "unmatched_issued", "unmatched_flown"}
            and int(row.get("days_in_suspense", 0)) >= min_age
        ]


class ReconRepository(_BaseRepository):
    def reset(self) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.recon_results.clear()
            return
        self.client.table("recon_results").delete().neq("ticket_number", "").execute()

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            if "id" not in row:
                row = {**row, "id": str(uuid4())}
            _MEMORY_STATE.recon_results[row["id"]] = row
            return row
        response = self.client.table("recon_results").insert(row).execute()
        return (response.data or [row])[0]

    def all_rows(self) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return list(_MEMORY_STATE.recon_results.values())
        response = self.client.table("recon_results").select("*").execute()
        return response.data or []

    def get_breaks(self, status: str = "unresolved", break_type: str | None = None) -> list[dict[str, Any]]:
        rows = [row for row in self.all_rows() if row["status"] == "break"]
        if status:
            rows = [row for row in rows if row.get("resolution") == status]
        if break_type:
            rows = [row for row in rows if row.get("break_type") == break_type]
        return rows

    def resolve(self, break_id: str, resolution: str, notes: str) -> None:
        if self.backend == StorageBackend.MEMORY:
            if break_id not in _MEMORY_STATE.recon_results:
                raise KeyError("Break not found")
            row = _MEMORY_STATE.recon_results[break_id]
            row["resolution"] = resolution
            row["resolution_notes"] = notes
            row["resolved_at"] = _now_iso()
            return
        self.client.table("recon_results").update(
            {"resolution": resolution, "resolution_notes": notes, "resolved_at": _now_iso()}
        ).eq("id", break_id).execute()


class AuditRepository(_BaseRepository):
    def reset(self) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.audit_log.clear()
            return
        self.client.table("audit_log").delete().neq("action", "").execute()

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            if "id" not in row:
                row = {**row, "id": str(uuid4())}
            _MEMORY_STATE.audit_log.append(row)
            _MEMORY_STATE.audit_log.sort(key=lambda item: item["timestamp"])
            return row
        response = self.client.table("audit_log").insert(row).execute()
        return (response.data or [row])[0]

    def get_by_ticket(self, ticket_number: str) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return [row for row in _MEMORY_STATE.audit_log if row.get("ticket_number") == ticket_number]
        response = (
            self.client.table("audit_log")
            .select("*")
            .eq("ticket_number", ticket_number)
            .order("timestamp")
            .execute()
        )
        return response.data or []

    def get_by_output_reference(self, output_reference: str) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return [row for row in _MEMORY_STATE.audit_log if row.get("output_reference") == output_reference]
        response = (
            self.client.table("audit_log")
            .select("*")
            .eq("output_reference", output_reference)
            .order("timestamp")
            .execute()
        )
        return response.data or []


class DagRunRepository(_BaseRepository):
    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            if "id" not in row:
                row = {**row, "id": str(uuid4())}
            _MEMORY_STATE.dag_runs[row["id"]] = row
            return row
        response = self.client.table("dag_runs").insert(row).execute()
        return (response.data or [row])[0]

    def update(self, run_id: str, values: dict[str, Any]) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.dag_runs[run_id].update(values)
            return
        self.client.table("dag_runs").update(values).eq("id", run_id).execute()

    def get(self, run_id: str) -> dict[str, Any] | None:
        if self.backend == StorageBackend.MEMORY:
            return _MEMORY_STATE.dag_runs.get(run_id)
        response = self.client.table("dag_runs").select("*").eq("id", run_id).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None


class TaskRunRepository(_BaseRepository):
    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            if "id" not in row:
                row = {**row, "id": str(uuid4())}
            _MEMORY_STATE.task_runs[row["id"]] = row
            return row
        response = self.client.table("task_runs").insert(row).execute()
        return (response.data or [row])[0]

    def update(self, task_run_id: str, values: dict[str, Any]) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.task_runs[task_run_id].update(values)
            return
        self.client.table("task_runs").update(values).eq("id", task_run_id).execute()

    def get_by_run(self, dag_run_id: str) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return [row for row in _MEMORY_STATE.task_runs.values() if row["dag_run_id"] == dag_run_id]
        response = self.client.table("task_runs").select("*").eq("dag_run_id", dag_run_id).execute()
        return response.data or []


class SettlementRepository(_BaseRepository):
    def reset(self) -> None:
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.settlements.clear()
            _MEMORY_STATE.settlement_saga_log.clear()
            return
        self.client.table("settlement_saga_log").delete().neq("action", "").execute()
        self.client.table("settlements").delete().neq("ticket_number", "").execute()

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            if "id" not in row:
                row = {**row, "id": str(uuid4())}
            _MEMORY_STATE.settlements[row["id"]] = row
            return row
        response = self.client.table("settlements").insert(row).execute()
        return (response.data or [row])[0]

    def update_status(self, settlement_id: str, new_status: str, extra: dict[str, Any] | None = None) -> None:
        payload = {"status": new_status, "updated_at": _now_iso()}
        if extra:
            payload.update(extra)
        if self.backend == StorageBackend.MEMORY:
            _MEMORY_STATE.settlements[settlement_id].update(payload)
            return
        self.client.table("settlements").update(payload).eq("id", settlement_id).execute()

    def get(self, settlement_id: str) -> dict[str, Any] | None:
        if self.backend == StorageBackend.MEMORY:
            return _MEMORY_STATE.settlements.get(settlement_id)
        response = self.client.table("settlements").select("*").eq("id", settlement_id).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def list_all(self) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return list(_MEMORY_STATE.settlements.values())
        response = self.client.table("settlements").select("*").execute()
        return response.data or []

    def insert_saga(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.backend == StorageBackend.MEMORY:
            if "id" not in row:
                row = {**row, "id": str(uuid4())}
            _MEMORY_STATE.settlement_saga_log.append(row)
            _MEMORY_STATE.settlement_saga_log.sort(key=lambda item: item["timestamp"])
            return row
        response = self.client.table("settlement_saga_log").insert(row).execute()
        return (response.data or [row])[0]

    def get_saga_log(self, settlement_id: str) -> list[dict[str, Any]]:
        if self.backend == StorageBackend.MEMORY:
            return [row for row in _MEMORY_STATE.settlement_saga_log if row["settlement_id"] == settlement_id]
        response = (
            self.client.table("settlement_saga_log")
            .select("*")
            .eq("settlement_id", settlement_id)
            .order("timestamp")
            .execute()
        )
        return response.data or []


def reset_memory_backend() -> None:
    _MEMORY_STATE.reset()


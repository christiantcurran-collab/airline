from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any

from flightledger.audit.lineage import AuditStore
from flightledger.db.repositories import DagRunRepository, TaskRunRepository, get_storage_backend, reset_memory_backend
from flightledger.bus.in_memory import InMemoryBus
from flightledger.matching.coupon_matcher import CouponMatcher
from flightledger.models.canonical import CanonicalEventType
from flightledger.orchestrator.dag import DAG, DAGRunner, Task
from flightledger.pipeline import SOURCE_CHANNELS, SourceChannel, ingest_demo
from flightledger.recon.reconciliation import ReconciliationEngine, ReconSummary
from flightledger.simulation import FlightSimulationEngine
from flightledger.settlement.engine import SettlementEngine
from flightledger.stores.ticket_lifecycle import TicketLifecycleStore, TicketState


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


class FlightLedgerRuntime:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.audit = AuditStore()
        self.ticket_store = TicketLifecycleStore()
        self.matcher = CouponMatcher(self.ticket_store)
        self.recon = ReconciliationEngine(self.ticket_store, self.matcher)
        self.settlement = SettlementEngine(audit_store=self.audit)
        self.simulation = FlightSimulationEngine(ticket_store=self.ticket_store, audit_store=self.audit)
        self.dag_run_repo = DagRunRepository()
        self.task_run_repo = TaskRunRepository()
        self._last_bus = None
        self._last_channels: list[dict[str, Any]] = []
        self._last_recon_summary = ReconSummary(total_matched=0, total_breaks=0, breaks_by_type={}, breaks_by_severity={})
        self._seeded = False
        self._seed_lock = Lock()
        self._dags = self._build_dags()

    def refresh(self, force: bool = True) -> None:
        with self._seed_lock:
            if self._seeded and not force:
                return
            if get_storage_backend().value == "memory":
                reset_memory_backend()
                self.dag_run_repo = DagRunRepository()
                self.task_run_repo = TaskRunRepository()

            # Reset in dependency order for Supabase FK safety.
            # coupon_matches references ticket_events, so matcher must reset before ticket_store.
            self.settlement.reset()
            self.recon.reset()
            self.matcher.reset()
            self.ticket_store.reset()
            self.audit.reset()
            self._seeded = False
            self._ingest_pipeline()
            self._run_matching_recon()
            self._bootstrap_settlements()
            self._seeded = True

    def ensure_seeded(self) -> None:
        if self._seeded:
            return
        if get_storage_backend().value == "supabase" and self._hydrate_from_existing_supabase():
            return
        self.refresh(force=False)

    def dashboard_payload(self, refresh: bool = False) -> dict[str, Any]:
        if refresh:
            self.refresh(force=True)
        else:
            self.ensure_seeded()
        topics: dict[str, Any] = {}
        total_events = 0
        for topic, events in sorted(self._last_bus.topics.items()):
            serialized = [event.model_dump(mode="json") for event in events]
            topics[topic] = {"count": len(serialized), "events": serialized}
            total_events += len(serialized)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bus_backend": os.getenv("FLIGHTLEDGER_BUS_BACKEND", "memory").strip().lower(),
            "storage_backend": os.getenv("FLIGHTLEDGER_STORAGE_BACKEND", "memory").strip().lower(),
            "total_channels": len(self._last_channels),
            "total_topics": len(topics),
            "total_events": total_events,
            "channels": self._last_channels,
            "topics": topics,
        }

    def ticket_history(self, ticket_number: str) -> list[dict[str, Any]]:
        self.ensure_seeded()
        return [event.model_dump(mode="json") for event in self.ticket_store.get_history(ticket_number)]

    def ticket_detail(self, ticket_number: str) -> dict[str, Any]:
        self.ensure_seeded()
        state = self.ticket_store.get_current_state(ticket_number)
        history = self.ticket_history(ticket_number)
        return {
            "ticket_number": ticket_number,
            "state": self._serialize_state(state),
            "history": history,
        }

    def matching_summary(self) -> dict[str, Any]:
        self.ensure_seeded()
        rows = self.matcher.repository.all_rows()
        matched = len([row for row in rows if row["status"] == "matched"])
        unmatched_issued = len([row for row in rows if row["status"] == "unmatched_issued"])
        unmatched_flown = len([row for row in rows if row["status"] == "unmatched_flown"])
        suspense = len([row for row in rows if row["status"] == "suspense"])
        return {
            "matched": matched,
            "unmatched_issued": unmatched_issued,
            "unmatched_flown": unmatched_flown,
            "suspense": suspense,
            "total": len(rows),
        }

    def matching_suspense(self, min_age_days: int = 0) -> list[dict[str, Any]]:
        self.ensure_seeded()
        return self.matcher.get_suspense_items(min_age_days)

    def recon_summary(self) -> dict[str, Any]:
        self.ensure_seeded()
        return asdict(self._last_recon_summary)

    def recon_breaks(self, status: str = "unresolved", break_type: str | None = None) -> list[dict[str, Any]]:
        self.ensure_seeded()
        return self.recon.get_breaks(status=status, break_type=break_type)

    def resolve_break(self, break_id: str, resolution: str, notes: str) -> None:
        self.ensure_seeded()
        self.recon.resolve_break(break_id, resolution, notes)
        self.audit.log(
            action="break_resolved",
            component="reconciliation",
            output_reference=break_id,
            detail={"resolution": resolution, "notes": notes},
        )

    def ticket_audit_history(self, ticket_number: str) -> list[dict[str, Any]]:
        self.ensure_seeded()
        return [asdict(record) for record in self.audit.get_history(ticket_number)]

    def get_dags(self) -> list[dict[str, Any]]:
        return [
            {
                "name": dag.name,
                "tasks": [{"name": task.name, "depends_on": task.depends_on} for task in dag.tasks],
            }
            for dag in self._dags.values()
        ]

    def run_dag(self, dag_name: str) -> dict[str, Any]:
        self.ensure_seeded()
        dag = self._dags.get(dag_name)
        if not dag:
            raise KeyError("Unknown DAG")
        runner = DAGRunner(
            dag=dag,
            audit_store=self.audit,
            dag_repo=self.dag_run_repo,
            task_repo=self.task_run_repo,
        )
        result = runner.run()
        return {
            "run_id": result.run_id,
            "dag_name": result.dag_name,
            "status": result.status,
            "task_results": [asdict(task) for task in result.task_results],
        }

    def get_dag_run(self, run_id: str) -> dict[str, Any] | None:
        stub_runner = DAGRunner(
            dag=list(self._dags.values())[0],
            audit_store=self.audit,
            dag_repo=self.dag_run_repo,
            task_repo=self.task_run_repo,
        )
        return stub_runner.get_run(run_id)

    def settlements(self, status: str | None = None) -> list[dict[str, Any]]:
        self.ensure_seeded()
        return self.settlement.list_settlements(status=status)

    def settlement_saga(self, settlement_id: str) -> list[dict[str, Any]]:
        self.ensure_seeded()
        return self.settlement.get_saga(settlement_id)

    def simulation_state(self) -> dict[str, Any]:
        self.ensure_seeded()
        return self.simulation.get_state()

    def simulation_generate_flight(self, seed: int | None = None) -> dict[str, Any]:
        self.ensure_seeded()
        return self.simulation.generate_flight(seed=seed)

    def simulation_process_bookings(self) -> dict[str, Any]:
        self.ensure_seeded()
        return self.simulation.process_bookings()

    def simulation_reset(self) -> dict[str, Any]:
        self.ensure_seeded()
        return self.simulation.reset()

    def passenger_walkthroughs(self) -> list[dict[str, Any]]:
        self.ensure_seeded()
        issued_events = self.ticket_store.get_events_by_type(
            [CanonicalEventType.TICKET_ISSUED, CanonicalEventType.TICKET_REISSUED]
        )
        matching_rows = self.matcher.repository.all_rows()
        recon_rows = self.recon.repository.all_rows()
        settlement_rows = self.settlement.list_settlements()

        matching_by_key = {
            (row.get("ticket_number"), int(row.get("coupon_number"))): row
            for row in matching_rows
            if row.get("ticket_number") and row.get("coupon_number") is not None
        }
        recon_by_key = {
            (row.get("ticket_number"), int(row.get("coupon_number"))): row
            for row in recon_rows
            if row.get("ticket_number") and row.get("coupon_number") is not None
        }

        passenger_index: dict[str, dict[str, Any]] = {}
        for event in sorted(issued_events, key=lambda item: (item.passenger_name or "", item.ticket_number, item.coupon_number or 0)):
            passenger_name = event.passenger_name or f"Passenger {event.ticket_number}"
            passenger = passenger_index.setdefault(
                passenger_name,
                {
                    "passenger_name": passenger_name,
                    "tickets": set(),
                    "sales_channels": set(),
                    "itinerary": [],
                },
            )
            passenger["tickets"].add(event.ticket_number)
            sales_channel = str(event.metadata.get("sales_channel") or "unknown")
            passenger["sales_channels"].add(sales_channel)
            key = (event.ticket_number, int(event.coupon_number or 0))
            matching_row = matching_by_key.get(key)
            recon_row = recon_by_key.get(key)
            passenger["itinerary"].append(
                {
                    "ticket_number": event.ticket_number,
                    "pnr": event.pnr,
                    "coupon_number": event.coupon_number,
                    "flight_date": event.flight_date.isoformat() if event.flight_date else None,
                    "flight_number": event.flight_number,
                    "origin": event.origin,
                    "destination": event.destination,
                    "marketing_carrier": event.marketing_carrier,
                    "operating_carrier": event.operating_carrier,
                    "gross_amount": _decimal_to_float(event.gross_amount),
                    "currency": event.currency,
                    "sales_channel": sales_channel,
                    "match_status": matching_row.get("status") if matching_row else "missing",
                    "recon_status": recon_row.get("status") if recon_row else "missing",
                    "recon_break_type": recon_row.get("break_type") if recon_row else None,
                }
            )

        walkthroughs: list[dict[str, Any]] = []
        for passenger_name in sorted(passenger_index.keys()):
            passenger = passenger_index[passenger_name]
            tickets = sorted(passenger["tickets"])
            itinerary = sorted(passenger["itinerary"], key=lambda leg: (leg["ticket_number"], leg["coupon_number"] or 0))
            sales_channels = sorted(passenger["sales_channels"])

            source_counter: Counter[str] = Counter()
            lifecycle_states: list[dict[str, Any]] = []
            audit_records = 0
            for ticket_number in tickets:
                history = self.ticket_store.get_history(ticket_number)
                for event in history:
                    source_counter[event.source_system.value] += 1
                state = self.ticket_store.get_current_state(ticket_number)
                lifecycle_states.append(
                    {
                        "ticket_number": ticket_number,
                        "status": state.status,
                        "event_count": state.event_count,
                        "last_event_type": state.last_event_type,
                    }
                )
                audit_records += len(self.audit.get_history(ticket_number))

            ticket_set = set(tickets)
            matching_for_passenger = [row for row in matching_rows if row.get("ticket_number") in ticket_set]
            matching_counter = Counter(str(row.get("status")) for row in matching_for_passenger)
            recon_for_passenger = [row for row in recon_rows if row.get("ticket_number") in ticket_set]
            recon_breaks = [row for row in recon_for_passenger if row.get("status") == "break"]
            recon_break_types = Counter(str(row.get("break_type")) for row in recon_breaks if row.get("break_type"))
            settlement_for_passenger = [row for row in settlement_rows if row.get("ticket_number") in ticket_set]
            settlement_counter = Counter(str(row.get("status")) for row in settlement_for_passenger)

            narrative = self._build_passenger_narrative(
                matched=int(matching_counter.get("matched", 0)),
                unmatched_issued=int(matching_counter.get("unmatched_issued", 0)),
                unmatched_flown=int(matching_counter.get("unmatched_flown", 0)),
                breaks=len(recon_breaks),
                settlements=len(settlement_for_passenger),
            )

            walkthroughs.append(
                {
                    "passenger_name": passenger_name,
                    "tickets": tickets,
                    "sales_channels": sales_channels,
                    "purchase_summary": self._build_purchase_summary(itinerary),
                    "itinerary": itinerary,
                    "steps": {
                        "ingestion": {
                            "issued_coupons": len(itinerary),
                            "source_events": dict(source_counter),
                        },
                        "lifecycle": {
                            "ticket_states": lifecycle_states,
                        },
                        "matching": {
                            "matched": int(matching_counter.get("matched", 0)),
                            "unmatched_issued": int(matching_counter.get("unmatched_issued", 0)),
                            "unmatched_flown": int(matching_counter.get("unmatched_flown", 0)),
                            "suspense": int(matching_counter.get("suspense", 0)),
                        },
                        "reconciliation": {
                            "matched": len([row for row in recon_for_passenger if row.get("status") == "matched"]),
                            "breaks": len(recon_breaks),
                            "break_types": dict(recon_break_types),
                        },
                        "settlement": {
                            "total": len(settlement_for_passenger),
                            "statuses": dict(settlement_counter),
                        },
                        "audit": {
                            "records": audit_records,
                        },
                    },
                    "narrative": narrative,
                    "result_meaning": self._build_result_meaning(
                        matched=int(matching_counter.get("matched", 0)),
                        unmatched_issued=int(matching_counter.get("unmatched_issued", 0)),
                        unmatched_flown=int(matching_counter.get("unmatched_flown", 0)),
                        breaks=len(recon_breaks),
                        settlement_statuses=dict(settlement_counter),
                    ),
                }
            )
        return walkthroughs

    def _ingest_pipeline(self) -> None:
        source_hash_cache: dict[str, str] = {}

        def on_event(event: Any, source: SourceChannel, payload: str) -> None:
            source_hash = source_hash_cache.get(source.channel_id)
            if source_hash is None:
                source_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                source_hash_cache[source.channel_id] = source_hash
                self.audit.log(
                    action="source_ingested",
                    component="adapter",
                    detail={
                        "channel_id": source.channel_id,
                        "source_name": source.name,
                        "protocol": source.protocol,
                        "format": source.data_format,
                    },
                    raw_source_hash=source_hash,
                )

            self.ticket_store.append(event)
            self.audit.log(
                action="ticket_event_appended",
                component="ticket_lifecycle_store",
                ticket_number=event.ticket_number,
                input_event_ids=[event.event_id],
                output_reference=event.event_id,
                detail={"event_type": event.event_type.value, "source_system": event.source_system.value},
                raw_source_hash=source_hash,
            )

        self._last_bus, self._last_channels = ingest_demo(self.data_dir, on_event=on_event)

    def _hydrate_from_existing_supabase(self) -> bool:
        try:
            events = self.ticket_store.all_events()
        except Exception:
            return False
        if not events:
            return False

        bus = InMemoryBus()
        for event in events:
            bus.publish(event)
        self._last_bus = bus

        # Raw source payloads are unavailable once data already lives in Supabase.
        # Keep channel metadata without payload text for dashboard continuity.
        self._last_channels = [
            {
                "channel_id": source.channel_id,
                "name": source.name,
                "protocol": source.protocol,
                "format": source.data_format,
                "file_name": source.filename,
                "record_count": 0,
                "raw_payload": "Loaded from persisted Supabase records (raw source payload not rehydrated).",
            }
            for source in SOURCE_CHANNELS
        ]

        recon_rows = self.recon.repository.all_rows()
        total_matched = len([row for row in recon_rows if row.get("status") == "matched"])
        breaks = [row for row in recon_rows if row.get("status") == "break"]
        breaks_by_type: dict[str, int] = {}
        breaks_by_severity: dict[str, int] = {}
        for row in breaks:
            break_type = row.get("break_type")
            severity = row.get("severity")
            if break_type:
                breaks_by_type[break_type] = breaks_by_type.get(break_type, 0) + 1
            if severity:
                breaks_by_severity[severity] = breaks_by_severity.get(severity, 0) + 1
        self._last_recon_summary = ReconSummary(
            total_matched=total_matched,
            total_breaks=len(breaks),
            breaks_by_type=breaks_by_type,
            breaks_by_severity=breaks_by_severity,
        )
        self._seeded = True
        return True

    def _run_matching_recon(self) -> None:
        matching = self.matcher.run_matching()
        self.audit.log(
            action="coupon_matching_completed",
            component="coupon_matcher",
            detail={
                "matched": matching.matched,
                "unmatched_issued": matching.unmatched_issued,
                "unmatched_flown": matching.unmatched_flown,
            },
        )
        self._last_recon_summary = self.recon.run_full_recon()
        self.audit.log(
            action="reconciliation_completed",
            component="reconciliation_engine",
            detail=asdict(self._last_recon_summary),
        )

    def _bootstrap_settlements(self) -> None:
        settlement_events = self.ticket_store.get_events_by_type(
            [CanonicalEventType.SETTLEMENT_DUE, CanonicalEventType.INTERLINE_CLAIM]
        )
        for index, event in enumerate(settlement_events):
            amount = event.gross_amount or Decimal("0")
            settlement = self.settlement.calculate(
                ticket_number=event.ticket_number,
                counterparty=event.metadata.get("partner_carrier") or event.metadata.get("gds") or "counterparty",
                our_amount=amount if amount > 0 else Decimal("1"),
            )
            settlement = self.settlement.validate(settlement.id)
            settlement = self.settlement.submit(settlement.id)
            if index % 8 == 0:
                their_amount = (amount if amount > 0 else Decimal("1")) + Decimal("5")
                settlement = self.settlement.confirm(settlement.id, their_amount=their_amount)
                self.settlement.compensate(settlement.id, reason="Disputed amount")
            else:
                settlement = self.settlement.confirm(settlement.id, their_amount=amount if amount > 0 else Decimal("1"))
                self.settlement.reconcile(settlement.id)

    def _serialize_state(self, state: TicketState) -> dict[str, Any]:
        return {
            "ticket_number": state.ticket_number,
            "status": state.status,
            "current_amount": _decimal_to_float(state.current_amount),
            "coupon_statuses": state.coupon_statuses,
            "last_modified": state.last_modified.isoformat() if state.last_modified else None,
            "pnr": state.pnr,
            "passenger_name": state.passenger_name,
            "origin": state.origin,
            "destination": state.destination,
            "currency": state.currency,
            "event_count": state.event_count,
            "last_event_type": state.last_event_type,
        }

    def _build_dags(self) -> dict[str, DAG]:
        month_end = DAG(
            name="month_end_close",
            tasks=[
                Task(name="ingest_all_feeds", depends_on=[], fn=lambda: {"channels": len(self._last_channels)}),
                Task(name="coupon_matching", depends_on=["ingest_all_feeds"], fn=lambda: self.matching_summary()),
                Task(name="reconciliation", depends_on=["coupon_matching"], fn=lambda: self.recon_summary()),
                Task(name="age_suspense", depends_on=["coupon_matching"], fn=lambda: {"aged": self.matcher.age_suspense()}),
                Task(name="generate_settlements", depends_on=["reconciliation"], fn=lambda: {"count": len(self.settlements())}),
                Task(name="resolve_breaks", depends_on=["reconciliation"], fn=lambda: {"open_breaks": len(self.recon_breaks())}),
                Task(
                    name="revenue_reports",
                    depends_on=["resolve_breaks", "generate_settlements"],
                    fn=lambda: {"report_id": f"RPT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"},
                ),
                Task(name="regulatory_filing", depends_on=["revenue_reports"], fn=lambda: {"status": "submitted"}),
            ],
        )
        return {month_end.name: month_end}

    @staticmethod
    def _build_passenger_narrative(
        matched: int,
        unmatched_issued: int,
        unmatched_flown: int,
        breaks: int,
        settlements: int,
    ) -> str:
        if breaks > 0:
            return f"{matched} coupon(s) matched, {breaks} recon break(s) need follow-up, {settlements} settlement item(s) created."
        if unmatched_issued > 0 or unmatched_flown > 0:
            return (
                f"{matched} coupon(s) matched with {unmatched_issued} unmatched issued and "
                f"{unmatched_flown} unmatched flown; review timing/data gaps."
            )
        return f"Clean flow: {matched} coupon(s) matched, no recon breaks, {settlements} settlement item(s) progressed."

    @staticmethod
    def _build_purchase_summary(itinerary: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_ticket: dict[str, dict[str, Any]] = {}
        for leg in itinerary:
            ticket_number = str(leg.get("ticket_number"))
            row = by_ticket.setdefault(
                ticket_number,
                {
                    "ticket_number": ticket_number,
                    "sales_channel": leg.get("sales_channel"),
                    "pnr": leg.get("pnr"),
                    "coupons": 0,
                    "total_paid": Decimal("0"),
                    "currency": leg.get("currency"),
                    "journey_legs": [],
                },
            )
            row["coupons"] += 1
            amount = leg.get("gross_amount")
            if amount is not None:
                row["total_paid"] += Decimal(str(amount))
            route = f"{leg.get('origin') or '---'}-{leg.get('destination') or '---'}"
            row["journey_legs"].append(route)

        summary: list[dict[str, Any]] = []
        for ticket_number in sorted(by_ticket.keys()):
            row = by_ticket[ticket_number]
            summary.append(
                {
                    "ticket_number": row["ticket_number"],
                    "pnr": row["pnr"],
                    "sales_channel": row["sales_channel"],
                    "coupons": row["coupons"],
                    "total_paid": _decimal_to_float(row["total_paid"]),
                    "currency": row["currency"],
                    "journey": " -> ".join(row["journey_legs"]),
                }
            )
        return summary

    @staticmethod
    def _build_result_meaning(
        matched: int,
        unmatched_issued: int,
        unmatched_flown: int,
        breaks: int,
        settlement_statuses: dict[str, int],
    ) -> list[str]:
        lines = [f"Matching: {matched} matched coupon(s)."]
        if unmatched_issued > 0:
            lines.append(f"Unmatched issued ({unmatched_issued}) means sold but no flown event yet (timing/no-show/capture gap).")
        if unmatched_flown > 0:
            lines.append(f"Unmatched flown ({unmatched_flown}) means flown event arrived without a matching issued coupon (data integrity issue).")
        if breaks > 0:
            lines.append(f"Reconciliation breaks ({breaks}) require investigation before close.")
        else:
            lines.append("Reconciliation clean: no breaks on this passenger's tickets.")

        reconciled = int(settlement_statuses.get("reconciled", 0))
        compensated = int(settlement_statuses.get("compensated", 0))
        disputed = int(settlement_statuses.get("disputed", 0))
        if reconciled > 0:
            lines.append(f"Settlements reconciled: {reconciled} item(s) confirmed by counterparties.")
        if compensated > 0 or disputed > 0:
            lines.append(
                f"Settlement exceptions: {disputed} disputed and {compensated} compensated; compensated means rollback after dispute."
            )
        return lines

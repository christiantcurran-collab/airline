from __future__ import annotations

import random
import string
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock
from typing import Any
from uuid import uuid4

from flightledger.audit.lineage import AuditStore
from flightledger.db.repositories import AuditRepository, TicketCurrentStateRepository, TicketEventRepository
from flightledger.models.canonical import CanonicalEvent, CanonicalEventType, SourceSystem
from flightledger.stores.ticket_lifecycle import TicketLifecycleStore

SIM_OUTPUT_REFERENCE = "simulation_state"
SIM_TICKET_PREFIX = "SIM-"


class FlightSimulationEngine:
    def __init__(self, ticket_store: TicketLifecycleStore, audit_store: AuditStore) -> None:
        self.ticket_store = ticket_store
        self.audit_store = audit_store
        self.event_repo = TicketEventRepository()
        self.state_repo = TicketCurrentStateRepository()
        self.audit_repo = AuditRepository()
        self._lock = Lock()
        self._state_cache: dict[str, Any] | None = None

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            state["database"] = self._db_snapshot()
            return state

    def generate_flight(self, seed: int | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            if int(state.get("phase_index", -1)) >= 0:
                state["database"] = self._db_snapshot()
                return state

            rng = random.Random(seed if seed is not None else int(datetime.now(timezone.utc).timestamp()))
            now = datetime.now(timezone.utc)
            flight = self._pick_flight(rng)
            departure_time = now + timedelta(hours=6)
            ticket_count = rng.randint(3, 5)

            tickets: list[dict[str, Any]] = []
            discrepancy_target = max(1, min(2, round(ticket_count * 0.3)))
            discrepancy_indexes = set(rng.sample(range(ticket_count), k=discrepancy_target))
            for index in range(ticket_count):
                tickets.append(self._generate_ticket(rng=rng, flight=flight, departure_time=departure_time, with_discrepancy=index in discrepancy_indexes))

            total_revenue = sum(Decimal(str(ticket["internal_total_amount"])) for ticket in tickets)
            total_coupons = sum(len(ticket["legs"]) for ticket in tickets)
            discrepancy_count = len([ticket for ticket in tickets if Decimal(str(ticket["discrepancy_amount"])) != Decimal("0")])

            operations = [
                {
                    "id": str(uuid4()),
                    "timestamp": now.isoformat(),
                    "phase": "phase_0_generate",
                    "component": "monte_carlo",
                    "title": "Monte Carlo Ticket Generation",
                    "message": f"Generated {ticket_count} tickets and {total_coupons} coupons for {flight['flight_number']} {flight['origin']}->{flight['destination']}.",
                    "snippet": {
                        "ticket_count": ticket_count,
                        "coupons": total_coupons,
                        "discrepancies": discrepancy_count,
                    },
                }
            ]

            new_state = {
                "simulation_id": state["simulation_id"],
                "simulated_time": now.isoformat(),
                "flight": {
                    **flight,
                    "departure_time": departure_time.isoformat(),
                },
                "phase_index": 0,
                "phase_name": "phase_0_generated",
                "phase_status": {
                    "generate_flight": "completed",
                    "process_bookings": "available",
                },
                "tickets": tickets,
                "operations": operations,
                "metrics": {
                    "tickets_generated": ticket_count,
                    "coupons_generated": total_coupons,
                    "potential_breaks": discrepancy_count,
                    "gross_revenue": float(total_revenue),
                    "bookings_processed": 0,
                    "events_appended": 0,
                },
                "last_action": "generate_flight",
            }
            self._save_state(new_state)
            new_state["database"] = self._db_snapshot()
            return new_state

    def process_bookings(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state()
            phase_index = int(state.get("phase_index", -1))
            if phase_index < 0:
                raise ValueError("Generate a flight first.")
            if phase_index >= 1:
                state["database"] = self._db_snapshot()
                return state

            operations = list(state.get("operations", []))
            tickets = state.get("tickets", [])
            events_appended = 0

            for ticket in tickets:
                for leg in ticket["legs"]:
                    raw_record = self._raw_source_example(ticket=ticket, leg=leg)
                    operations.append(
                        self._operation(
                            phase="phase_1_booking",
                            component="adapter",
                            title="Source Adapter",
                            message=f"{ticket['ticket_number']} normalized from {ticket['source_system']}.",
                            snippet=raw_record,
                        )
                    )

                    event = CanonicalEvent(
                        source_system=self._source_system(ticket["source_system"]),
                        event_type=CanonicalEventType.TICKET_ISSUED,
                        ticket_number=ticket["ticket_number"],
                        coupon_number=leg["coupon_number"],
                        pnr=ticket["pnr"],
                        passenger_name=ticket["passenger_name"],
                        marketing_carrier=leg["marketing_carrier"],
                        operating_carrier=leg["operating_carrier"],
                        flight_number=leg["flight_number"],
                        flight_date=leg["flight_date"],
                        origin=leg["origin"],
                        destination=leg["destination"],
                        currency=ticket["currency"],
                        gross_amount=Decimal(str(leg["internal_amount"])),
                        net_amount=(Decimal(str(leg["internal_amount"])) * Decimal("0.95")).quantize(Decimal("0.01")),
                        metadata={
                            "simulation_id": state["simulation_id"],
                            "simulation_phase": "phase_1_booking",
                            "source_vendor": ticket["source_vendor"],
                            "sales_channel": ticket["source_system"],
                        },
                    )

                    operations.append(
                        self._operation(
                            phase="phase_1_booking",
                            component="bus",
                            title="Message Bus",
                            message=f"Published TicketIssued for {event.ticket_number} coupon {event.coupon_number}.",
                            snippet={
                                "event_type": event.event_type.value,
                                "ticket_number": event.ticket_number,
                                "coupon_number": event.coupon_number,
                                "source_system": event.source_system.value,
                            },
                        )
                    )

                    self.ticket_store.append(event)
                    events_appended += 1

                    history = self.ticket_store.get_history(event.ticket_number)
                    operations.append(
                        self._operation(
                            phase="phase_1_booking",
                            component="event_store",
                            title="Ticket Lifecycle Store",
                            message=f"Appended event {len(history)} for {event.ticket_number}.",
                            snippet={"event_count": len(history), "ticket_number": event.ticket_number},
                        )
                    )

                    state_row = self.ticket_store.get_current_state(event.ticket_number)
                    operations.append(
                        self._operation(
                            phase="phase_1_booking",
                            component="cqrs_read_model",
                            title="CQRS Read Model",
                            message=f"Projected {event.ticket_number} status={state_row.status}.",
                            snippet={
                                "ticket_number": event.ticket_number,
                                "status": state_row.status,
                                "event_count": state_row.event_count,
                            },
                        )
                    )

                    self.audit_store.log(
                        action="simulation_booking_processed",
                        component="simulation_engine",
                        ticket_number=event.ticket_number,
                        input_event_ids=[event.event_id],
                        output_reference=state["simulation_id"],
                        detail={
                            "phase": "phase_1_booking",
                            "coupon_number": event.coupon_number,
                            "source_system": event.source_system.value,
                        },
                    )

            now = datetime.now(timezone.utc)
            new_state = {
                **state,
                "simulated_time": (now + timedelta(hours=2)).isoformat(),
                "phase_index": 1,
                "phase_name": "phase_1_bookings_processed",
                "phase_status": {
                    "generate_flight": "completed",
                    "process_bookings": "completed",
                },
                "operations": operations,
                "metrics": {
                    **state["metrics"],
                    "bookings_processed": len(tickets),
                    "events_appended": events_appended,
                },
                "last_action": "process_bookings",
            }
            self._save_state(new_state)
            new_state["database"] = self._db_snapshot()
            return new_state

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self.event_repo.delete_by_ticket_prefix(SIM_TICKET_PREFIX)
            self.state_repo.delete_by_ticket_prefix(SIM_TICKET_PREFIX)
            self._state_cache = self._default_state()
            self._save_state(self._state_cache)
            state = dict(self._state_cache)
            state["database"] = self._db_snapshot()
            return state

    def _load_state(self) -> dict[str, Any]:
        if self._state_cache is not None:
            return dict(self._state_cache)
        rows = self.audit_store.get_lineage(SIM_OUTPUT_REFERENCE)
        if not rows:
            self._state_cache = self._default_state()
            return dict(self._state_cache)

        latest = sorted(rows, key=lambda row: row.timestamp)[-1]
        detail = latest.detail or {}
        state = detail.get("state")
        if isinstance(state, dict):
            self._state_cache = state
            return dict(state)

        self._state_cache = self._default_state()
        return dict(self._state_cache)

    def _save_state(self, state: dict[str, Any]) -> None:
        self._state_cache = dict(state)
        self.audit_store.log(
            action="simulation_state_saved",
            component="simulation_engine",
            output_reference=SIM_OUTPUT_REFERENCE,
            detail={"state": state},
        )

    def _default_state(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "simulation_id": f"sim-{uuid4()}",
            "simulated_time": now,
            "flight": None,
            "phase_index": -1,
            "phase_name": "idle",
            "phase_status": {
                "generate_flight": "available",
                "process_bookings": "locked",
            },
            "tickets": [],
            "operations": [],
            "metrics": {
                "tickets_generated": 0,
                "coupons_generated": 0,
                "potential_breaks": 0,
                "gross_revenue": 0.0,
                "bookings_processed": 0,
                "events_appended": 0,
            },
            "last_action": None,
        }

    def _db_snapshot(self) -> dict[str, Any]:
        ticket_events = self.event_repo.all_rows()
        sim_ticket_events = [row for row in ticket_events if str(row.get("ticket_number", "")).startswith(SIM_TICKET_PREFIX)]
        ticket_states = self.state_repo.all_rows()
        sim_ticket_states = [row for row in ticket_states if str(row.get("ticket_number", "")).startswith(SIM_TICKET_PREFIX)]
        audit_rows = self.audit_repo.all_rows()
        simulation_audit = [
            row
            for row in audit_rows
            if str(row.get("ticket_number", "")).startswith(SIM_TICKET_PREFIX)
            or row.get("component") == "simulation_engine"
        ]

        source_breakdown = Counter()
        for row in sim_ticket_events:
            source_breakdown[str(row.get("source_system", "unknown"))] += 1

        sample_events = [
            {
                "ticket_number": row.get("ticket_number"),
                "event_type": row.get("event_type"),
                "event_sequence": row.get("event_sequence"),
            }
            for row in sorted(sim_ticket_events, key=lambda item: (item.get("ticket_number", ""), int(item.get("event_sequence", 0))))[:6]
        ]

        return {
            "tables": {
                "ticket_events": {"rows": len(ticket_events), "simulation_rows": len(sim_ticket_events)},
                "ticket_current_state": {"rows": len(ticket_states), "simulation_rows": len(sim_ticket_states)},
                "audit_log": {"rows": len(audit_rows), "simulation_rows": len(simulation_audit)},
            },
            "simulation_source_breakdown": dict(source_breakdown),
            "sample_events": sample_events,
        }

    @staticmethod
    def _pick_flight(rng: random.Random) -> dict[str, str]:
        flights = [
            {"carrier": "BA", "flight_number": "BA117", "origin": "LHR", "destination": "JFK"},
            {"carrier": "BA", "flight_number": "BA287", "origin": "LHR", "destination": "SFO"},
            {"carrier": "AA", "flight_number": "AA100", "origin": "JFK", "destination": "SFO"},
        ]
        return dict(rng.choice(flights))

    def _generate_ticket(
        self,
        rng: random.Random,
        flight: dict[str, str],
        departure_time: datetime,
        with_discrepancy: bool,
    ) -> dict[str, Any]:
        source_system = self._pick_weighted(
            rng=rng,
            weights=[
                ("pss_direct", 0.4),
                ("gds", 0.3),
                ("ota", 0.2),
                ("interline", 0.1),
            ],
        )
        cabin = self._pick_weighted(
            rng=rng,
            weights=[
                ("economy", 0.6),
                ("premium", 0.25),
                ("business", 0.15),
            ],
        )
        base_amount = self._sample_price(rng, cabin)
        discrepancy = Decimal("0")
        if with_discrepancy:
            discrepancy = Decimal(str(rng.randint(2, 15)))
            if rng.random() < 0.5:
                discrepancy *= Decimal("-1")

        vendor = self._vendor_for_source(rng, source_system)
        legs = [self._build_leg(flight=flight, coupon_number=1, amount=base_amount, departure_time=departure_time)]
        if rng.random() < 0.35:
            legs.append(
                self._build_leg(
                    flight={"carrier": "AA", "flight_number": "AA100", "origin": "JFK", "destination": "SFO"},
                    coupon_number=2,
                    amount=(base_amount * Decimal("0.55")).quantize(Decimal("0.01")),
                    departure_time=departure_time + timedelta(hours=8),
                )
            )

        internal_total = sum(Decimal(str(leg["internal_amount"])) for leg in legs)
        external_total = internal_total + discrepancy
        ticket_number = f"{SIM_TICKET_PREFIX}{datetime.now(timezone.utc).strftime('%m%d')}{rng.randint(100000, 999999)}"
        pnr = "".join(rng.choices(string.ascii_uppercase + string.digits, k=6))
        first_names = ["Ava", "Noah", "Mia", "Liam", "Zoe", "Omar", "Ethan", "Ivy", "Lucas", "Sofia"]
        last_names = ["Morgan", "Patel", "Chen", "Rossi", "Kim", "Ali", "Nguyen", "Ward", "Garcia", "Hughes"]
        passenger_name = f"{rng.choice(first_names)} {rng.choice(last_names)}"

        return {
            "ticket_number": ticket_number,
            "pnr": pnr,
            "passenger_name": passenger_name,
            "source_system": source_system,
            "source_vendor": vendor,
            "cabin_class": cabin,
            "currency": "GBP",
            "internal_total_amount": float(internal_total),
            "external_reported_amount": float(external_total),
            "discrepancy_amount": float(discrepancy),
            "legs": legs,
        }

    @staticmethod
    def _build_leg(flight: dict[str, str], coupon_number: int, amount: Decimal, departure_time: datetime) -> dict[str, Any]:
        return {
            "coupon_number": coupon_number,
            "flight_number": flight["flight_number"],
            "marketing_carrier": flight["carrier"],
            "operating_carrier": flight["carrier"],
            "origin": flight["origin"],
            "destination": flight["destination"],
            "flight_date": departure_time.date().isoformat(),
            "internal_amount": float(amount.quantize(Decimal("0.01"))),
        }

    @staticmethod
    def _pick_weighted(rng: random.Random, weights: list[tuple[str, float]]) -> str:
        roll = rng.random()
        cumulative = 0.0
        for value, weight in weights:
            cumulative += weight
            if roll <= cumulative:
                return value
        return weights[-1][0]

    @staticmethod
    def _sample_price(rng: random.Random, cabin: str) -> Decimal:
        if cabin == "business":
            mean, std_dev, floor, ceil = 4500, 900, 3000, 6000
        elif cabin == "premium":
            mean, std_dev, floor, ceil = 1800, 400, 1200, 2500
        else:
            mean, std_dev, floor, ceil = 600, 120, 400, 800

        sampled = rng.gauss(mean, std_dev)
        clamped = max(floor, min(ceil, sampled))
        return Decimal(str(round(clamped, 2)))

    @staticmethod
    def _vendor_for_source(rng: random.Random, source_system: str) -> str:
        if source_system == "pss_direct":
            return "ba.com"
        if source_system == "gds":
            return rng.choice(["amadeus", "sabre"])
        if source_system == "ota":
            return rng.choice(["expedia", "booking.com"])
        return rng.choice(["AA", "IB", "QR"])

    @staticmethod
    def _source_system(source_system: str) -> SourceSystem:
        if source_system == "pss_direct":
            return SourceSystem.PSS
        if source_system == "gds":
            return SourceSystem.GDS
        if source_system == "ota":
            return SourceSystem.OTA
        return SourceSystem.INTERLINE

    @staticmethod
    def _raw_source_example(ticket: dict[str, Any], leg: dict[str, Any]) -> dict[str, Any]:
        if ticket["source_system"] == "gds":
            return {
                "record_type": "gds_xml",
                "ticket_number": ticket["ticket_number"],
                "coupon_number": leg["coupon_number"],
                "gds": ticket["source_vendor"],
                "gross_amount": ticket["external_reported_amount"],
            }
        if ticket["source_system"] == "ota":
            return {
                "record_type": "ota_webhook_json",
                "ota": ticket["source_vendor"],
                "ticket_number": ticket["ticket_number"],
                "status": "confirmed",
            }
        if ticket["source_system"] == "interline":
            return {
                "record_type": "interline_rest_json",
                "partner_carrier": ticket["source_vendor"],
                "ticket_number": ticket["ticket_number"],
                "coupon_number": leg["coupon_number"],
            }
        return {
            "record_type": "pss_csv",
            "ticket_number": ticket["ticket_number"],
            "coupon_number": leg["coupon_number"],
            "fare_class": ticket["cabin_class"],
        }

    @staticmethod
    def _operation(phase: str, component: str, title: str, message: str, snippet: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "component": component,
            "title": title,
            "message": message,
            "snippet": snippet,
        }

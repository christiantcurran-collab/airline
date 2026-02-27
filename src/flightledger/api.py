from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from flightledger.runtime import FlightLedgerRuntime

app = FastAPI(title="FlightLedger API", version="0.1.0")


def _cors_origins() -> list[str]:
    raw = os.getenv("FLIGHTLEDGER_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    parsed = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if "*" in parsed:
        return ["*"]
    return parsed


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _mock_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "mock"


runtime = FlightLedgerRuntime(_mock_data_dir())


class ResolveBreakRequest(BaseModel):
    resolution: str
    notes: str


def build_dashboard_payload() -> dict[str, Any]:
    return runtime.dashboard_payload(refresh=False)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "flightledger-api", "status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard(refresh: bool = False) -> dict[str, Any]:
    return runtime.dashboard_payload(refresh=refresh)


@app.get("/api/tickets/{ticket_number}")
def get_ticket(ticket_number: str) -> dict[str, Any]:
    return runtime.ticket_detail(ticket_number)


@app.get("/api/tickets/{ticket_number}/history")
def get_ticket_history(ticket_number: str) -> list[dict[str, Any]]:
    return runtime.ticket_history(ticket_number)


@app.get("/api/matching/summary")
def get_matching_summary() -> dict[str, Any]:
    return runtime.matching_summary()


@app.get("/api/matching/suspense")
def get_matching_suspense(min_age_days: int = 0) -> list[dict[str, Any]]:
    return runtime.matching_suspense(min_age_days=min_age_days)


@app.get("/api/recon/summary")
def get_recon_summary() -> dict[str, Any]:
    return runtime.recon_summary()


@app.get("/api/recon/breaks")
def get_recon_breaks(status: str = "unresolved", break_type: str | None = None) -> list[dict[str, Any]]:
    return runtime.recon_breaks(status=status, break_type=break_type)


@app.post("/api/recon/breaks/{break_id}/resolve")
def resolve_recon_break(break_id: str, payload: ResolveBreakRequest) -> dict[str, str]:
    runtime.resolve_break(break_id=break_id, resolution=payload.resolution, notes=payload.notes)
    return {"status": "ok"}


@app.get("/api/audit/{ticket_number}")
def get_audit_history(ticket_number: str) -> list[dict[str, Any]]:
    return runtime.ticket_audit_history(ticket_number)


@app.get("/api/orchestrator/dags")
def get_dags() -> list[dict[str, Any]]:
    return runtime.get_dags()


@app.post("/api/orchestrator/run/{dag_name}")
def run_dag(dag_name: str) -> dict[str, Any]:
    try:
        return runtime.run_dag(dag_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/orchestrator/runs/{run_id}")
def get_dag_run(run_id: str) -> dict[str, Any]:
    run = runtime.get_dag_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/api/settlements")
def get_settlements(status: str | None = None) -> list[dict[str, Any]]:
    return runtime.settlements(status=status)


@app.get("/api/settlements/{settlement_id}/saga")
def get_settlement_saga(settlement_id: str) -> list[dict[str, Any]]:
    return runtime.settlement_saga(settlement_id)

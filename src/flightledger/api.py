from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from flightledger.pipeline import ingest_demo

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


def build_dashboard_payload() -> dict[str, Any]:
    bus, channels = ingest_demo(_mock_data_dir())
    topics: dict[str, Any] = {}
    total_events = 0

    for topic, events in sorted(bus.topics.items()):
        serialized_events = [event.model_dump(mode="json") for event in events]
        topics[topic] = {
            "count": len(serialized_events),
            "events": serialized_events,
        }
        total_events += len(serialized_events)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bus_backend": os.getenv("FLIGHTLEDGER_BUS_BACKEND", "memory").strip().lower(),
        "total_channels": len(channels),
        "total_topics": len(topics),
        "total_events": total_events,
        "channels": channels,
        "topics": topics,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    return build_dashboard_payload()

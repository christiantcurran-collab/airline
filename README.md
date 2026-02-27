# FlightLedger

Phase-1 + Phase-2 implementation based on `FLIGHTLEDGER_V1.md`:

- Canonical event model
- Five integration adapters (PSS, DCS, GDS, OTA, Interline)
- Local in-memory message bus simulation with topic fan-out
- Local FastAPI endpoint for dashboard data
- Local React dashboard frontend for interactive exploration
- Optional Kafka publishing backend for event bus
- Ticket lifecycle store (event sourcing + CQRS read model)
- Coupon matching engine (issued/flown/suspense)
- Reconciliation engine with break classification and resolution
- Audit and lineage store (append-only)
- DAG orchestrator (topological execution with skip-on-fail)
- Settlement engine (saga transitions + compensation)
- Memory/Supabase storage backend switch
- Mock source payloads and a runnable ingestion pipeline
- Unit tests for adapters and publishing behavior

## Quickstart

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
python -m flightledger.pipeline
```

Default bus backend is in-memory (`FLIGHTLEDGER_BUS_BACKEND=memory`).
Default storage backend is memory (`FLIGHTLEDGER_STORAGE_BACKEND=memory`).

## Supabase Setup

Run schema SQL in Supabase SQL editor:

- `sql/supabase_phase2_schema.sql`

Then configure:

```powershell
$env:FLIGHTLEDGER_STORAGE_BACKEND="supabase"
$env:SUPABASE_URL="https://<project>.supabase.co"
$env:SUPABASE_KEY="<anon-or-service-role-key>"
```

## Run Local Dashboard

Start API (Terminal 1):

```powershell
cd C:\Users\ccurr\Desktop\Airline
uvicorn flightledger.api:app --reload --port 8000
```

Start frontend (Terminal 2):

```powershell
cd C:\Users\ccurr\Desktop\Airline\frontend
npm.cmd install
npm.cmd run dev
```

Open:

- `http://127.0.0.1:5173`

## Enable Kafka Bus

Start local Kafka:

```powershell
cd C:\Users\ccurr\Desktop\Airline
docker compose -f docker-compose.kafka.yml up -d
```

Run API in Kafka mode:

```powershell
cd C:\Users\ccurr\Desktop\Airline
$env:FLIGHTLEDGER_BUS_BACKEND="kafka"
$env:FLIGHTLEDGER_KAFKA_BOOTSTRAP_SERVERS="127.0.0.1:9092"
uvicorn flightledger.api:app --reload --port 8000
```

In this mode, ingestion still returns local topic snapshots for the dashboard, and also publishes every canonical event to Kafka topics:

- `ticket.issued`
- `coupon.flown`
- `refund.requested`
- `settlement.due`
- `booking.modified`

## Deploy On Render

This repo includes a Render Blueprint at `render.yaml`:

- `flightledger-api` (Python web service)
- `flightledger-frontend` (static site)

Required env vars in Render:

- On `flightledger-api`:
  - `FLIGHTLEDGER_CORS_ORIGINS=<your-frontend-render-url>`
  - `FLIGHTLEDGER_STORAGE_BACKEND=memory` (or `supabase`)
  - `SUPABASE_URL` and `SUPABASE_KEY` when using Supabase
- On `flightledger-frontend`:
  - `VITE_API_BASE_URL=<your-api-render-url>`

Example:

- `FLIGHTLEDGER_CORS_ORIGINS=https://flightledger-frontend.onrender.com`
- `VITE_API_BASE_URL=https://flightledger-api.onrender.com`

## Repository Layout

- `src/flightledger/models/canonical.py`: Canonical record schema
- `src/flightledger/adapters/`: Source-specific normalization adapters
- `src/flightledger/bus/in_memory.py`: Topic publisher for local demo
- `src/flightledger/pipeline.py`: End-to-end ingestion demo
- `src/flightledger/stores/ticket_lifecycle.py`: Event sourcing + CQRS ticket store
- `src/flightledger/matching/coupon_matcher.py`: Coupon matching engine
- `src/flightledger/recon/reconciliation.py`: Reconciliation and break classification
- `src/flightledger/audit/lineage.py`: Append-only lineage store
- `src/flightledger/orchestrator/dag.py`: DAG orchestrator
- `src/flightledger/settlement/engine.py`: Settlement saga engine
- `src/flightledger/db/`: Storage backend + repositories (`memory` and `supabase`)
- `src/flightledger/api.py`: FastAPI endpoints for dashboard + Phase 2 panels
- `frontend/`: React + Vite dashboard UI
- `sql/supabase_phase2_schema.sql`: Supabase table definitions for Phase 2
- `data/mock/`: Example source payloads
- `tests/`: Unit tests

# FlightLedger

Phase-1 implementation based on `FLIGHTLEDGER_V1.md`:

- Canonical event model
- Five integration adapters (PSS, DCS, GDS, OTA, Interline)
- Local in-memory message bus simulation with topic fan-out
- Local FastAPI endpoint for dashboard data
- Local React dashboard frontend for interactive exploration
- Optional Kafka publishing backend for event bus
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
- `src/flightledger/api.py`: FastAPI dashboard endpoint (`/api/dashboard`)
- `frontend/`: React + Vite dashboard UI
- `data/mock/`: Example source payloads
- `tests/`: Unit tests

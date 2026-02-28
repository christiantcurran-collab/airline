from fastapi.testclient import TestClient

from flightledger.api import app


def test_phase2_endpoints_smoke() -> None:
    client = TestClient(app)

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    ticket_number = dashboard.json()["topics"]["ticket.issued"]["events"][0]["ticket_number"]

    ticket = client.get(f"/api/tickets/{ticket_number}")
    assert ticket.status_code == 200
    assert ticket.json()["ticket_number"] == ticket_number

    history = client.get(f"/api/tickets/{ticket_number}/history")
    assert history.status_code == 200
    assert isinstance(history.json(), list)

    matching_summary = client.get("/api/matching/summary")
    assert matching_summary.status_code == 200
    assert "matched" in matching_summary.json()

    matching_suspense = client.get("/api/matching/suspense")
    assert matching_suspense.status_code == 200

    recon_summary = client.get("/api/recon/summary")
    assert recon_summary.status_code == 200
    assert "total_breaks" in recon_summary.json()

    recon_breaks = client.get("/api/recon/breaks")
    assert recon_breaks.status_code == 200
    breaks = recon_breaks.json()
    if breaks:
        break_id = breaks[0]["id"]
        resolved = client.post(
            f"/api/recon/breaks/{break_id}/resolve",
            json={"resolution": "manually_resolved", "notes": "test"},
        )
        assert resolved.status_code == 200

    audit = client.get(f"/api/audit/{ticket_number}")
    assert audit.status_code == 200

    dags = client.get("/api/orchestrator/dags")
    assert dags.status_code == 200
    dag_name = dags.json()[0]["name"]
    run = client.post(f"/api/orchestrator/run/{dag_name}")
    assert run.status_code == 200
    run_id = run.json()["run_id"]
    run_status = client.get(f"/api/orchestrator/runs/{run_id}")
    assert run_status.status_code == 200

    settlements = client.get("/api/settlements")
    assert settlements.status_code == 200
    settlement_rows = settlements.json()
    if settlement_rows:
        saga = client.get(f"/api/settlements/{settlement_rows[0]['id']}/saga")
        assert saga.status_code == 200

    walkthroughs = client.get("/api/walkthroughs")
    assert walkthroughs.status_code == 200
    walkthrough_rows = walkthroughs.json()
    assert len(walkthrough_rows) == 6
    assert "purchase_summary" in walkthrough_rows[0]
    assert "result_meaning" in walkthrough_rows[0]

    simulation_state = client.get("/api/simulation/state")
    assert simulation_state.status_code == 200

    generated = client.post("/api/simulation/generate-flight")
    assert generated.status_code == 200
    assert generated.json()["phase_index"] >= 0

    processed = client.post("/api/simulation/process-bookings")
    assert processed.status_code == 200
    assert processed.json()["phase_index"] >= 1

    reset = client.post("/api/simulation/reset")
    assert reset.status_code == 200
    assert reset.json()["phase_index"] == -1

from flightledger.api import build_dashboard_payload


def test_build_dashboard_payload_contains_topics() -> None:
    payload = build_dashboard_payload()

    assert payload["bus_backend"] == "memory"
    assert payload["total_channels"] == 5
    assert payload["total_topics"] >= 1
    assert payload["total_events"] == 600
    assert len(payload["channels"]) == 5
    assert "ticket.issued" in payload["topics"]
    assert payload["topics"]["ticket.issued"]["count"] == 200

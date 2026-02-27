from pathlib import Path

from flightledger.pipeline import run_demo


def test_run_demo_publishes_all_topics() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data" / "mock"
    bus = run_demo(data_dir)

    assert len(bus.topics["ticket.issued"]) == 40
    assert len(bus.topics["coupon.flown"]) == 20
    assert len(bus.topics["settlement.due"]) == 40
    assert len(bus.topics["booking.modified"]) == 20

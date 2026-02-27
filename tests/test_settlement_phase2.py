from decimal import Decimal

import pytest

from flightledger.settlement.engine import SettlementEngine


def test_settlement_happy_path() -> None:
    engine = SettlementEngine()
    engine.reset()
    settlement = engine.calculate("125000000401", "AA", Decimal("150.00"))
    settlement = engine.validate(settlement.id)
    settlement = engine.submit(settlement.id)
    settlement = engine.confirm(settlement.id, Decimal("150.00"))
    settlement = engine.reconcile(settlement.id)
    assert settlement.status == "reconciled"


def test_settlement_dispute_flow() -> None:
    engine = SettlementEngine()
    engine.reset()
    settlement = engine.calculate("125000000402", "AA", Decimal("200.00"))
    settlement = engine.validate(settlement.id)
    settlement = engine.submit(settlement.id)
    settlement = engine.confirm(settlement.id, Decimal("195.00"))
    assert settlement.status == "disputed"


def test_settlement_compensate_from_disputed() -> None:
    engine = SettlementEngine()
    engine.reset()
    settlement = engine.calculate("125000000403", "AA", Decimal("200.00"))
    settlement = engine.validate(settlement.id)
    settlement = engine.submit(settlement.id)
    settlement = engine.confirm(settlement.id, Decimal("195.00"))
    settlement = engine.compensate(settlement.id, "Dispute unresolved")
    saga = engine.get_saga(settlement.id)
    assert settlement.status == "compensated"
    assert any(step["to_status"] == "compensated" for step in saga)


def test_settlement_invalid_transition() -> None:
    engine = SettlementEngine()
    engine.reset()
    settlement = engine.calculate("125000000404", "AA", Decimal("100.00"))
    with pytest.raises(ValueError):
        engine.confirm(settlement.id, Decimal("100.00"))


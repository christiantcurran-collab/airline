from flightledger.audit.lineage import AuditStore


def test_audit_history_ordering() -> None:
    store = AuditStore()
    store.reset()
    store.log(action="ingested", component="adapter", ticket_number="1251")
    store.log(action="matched", component="coupon_matcher", ticket_number="1251")
    store.log(action="reconciled", component="reconciliation", ticket_number="1251")

    history = store.get_history("1251")
    assert len(history) == 3
    assert [row.action for row in history] == ["ingested", "matched", "reconciled"]


def test_audit_lineage_lookup() -> None:
    store = AuditStore()
    store.reset()
    store.log(action="classified", component="reconciliation", output_reference="recon-1")
    store.log(action="resolved", component="reconciliation", output_reference="recon-1")
    lineage = store.get_lineage("recon-1")
    assert len(lineage) == 2


def test_audit_store_has_no_update_delete_methods() -> None:
    assert not hasattr(AuditStore, "update")
    assert not hasattr(AuditStore, "delete")


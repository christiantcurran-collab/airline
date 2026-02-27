import pytest

from flightledger.orchestrator.dag import DAG, DAGRunner, Task


def test_dag_execution_order_linear() -> None:
    dag = DAG(
        name="linear",
        tasks=[
            Task(name="A", depends_on=[], fn=lambda: {"ok": True}),
            Task(name="B", depends_on=["A"], fn=lambda: {"ok": True}),
            Task(name="C", depends_on=["B"], fn=lambda: {"ok": True}),
        ],
    )
    runner = DAGRunner(dag)
    assert runner.get_execution_order() == ["A", "B", "C"]


def test_dag_skip_downstream_on_failure() -> None:
    def fail() -> dict[str, str]:
        raise RuntimeError("boom")

    dag = DAG(
        name="failure",
        tasks=[
            Task(name="A", depends_on=[], fn=fail),
            Task(name="B", depends_on=["A"], fn=lambda: {"ok": True}),
            Task(name="C", depends_on=["B"], fn=lambda: {"ok": True}),
        ],
    )
    result = DAGRunner(dag).run()
    statuses = {task.task_name: task.status for task in result.task_results}
    assert statuses["A"] == "failed"
    assert statuses["B"] == "skipped"
    assert statuses["C"] == "skipped"


def test_dag_cycle_detection() -> None:
    dag = DAG(
        name="cycle",
        tasks=[
            Task(name="A", depends_on=["B"], fn=lambda: {"ok": True}),
            Task(name="B", depends_on=["A"], fn=lambda: {"ok": True}),
        ],
    )
    with pytest.raises(ValueError):
        DAGRunner(dag)


def test_dag_task_waits_for_two_dependencies() -> None:
    calls: list[str] = []

    dag = DAG(
        name="fanin",
        tasks=[
            Task(name="A", depends_on=[], fn=lambda: calls.append("A") or {"ok": True}),
            Task(name="B", depends_on=[], fn=lambda: calls.append("B") or {"ok": True}),
            Task(name="C", depends_on=["A", "B"], fn=lambda: calls.append("C") or {"ok": True}),
        ],
    )
    result = DAGRunner(dag).run()
    statuses = {task.task_name: task.status for task in result.task_results}
    assert statuses["C"] == "succeeded"
    assert set(calls[:2]) == {"A", "B"}
    assert calls[2] == "C"


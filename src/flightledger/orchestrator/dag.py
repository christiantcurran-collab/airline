from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from flightledger.audit.lineage import AuditStore
from flightledger.db.repositories import DagRunRepository, TaskRunRepository


@dataclass
class Task:
    name: str
    depends_on: list[str]
    fn: Callable[[], Any]


@dataclass
class DAG:
    name: str
    tasks: list[Task]


@dataclass
class TaskResult:
    task_name: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None


@dataclass
class DAGRunResult:
    run_id: str
    dag_name: str
    status: str
    task_results: list[TaskResult]


class DAGRunner:
    def __init__(
        self,
        dag: DAG,
        audit_store: AuditStore | None = None,
        dag_repo: DagRunRepository | None = None,
        task_repo: TaskRunRepository | None = None,
    ) -> None:
        self.dag = dag
        self.audit_store = audit_store
        self.dag_repo = dag_repo or DagRunRepository()
        self.task_repo = task_repo or TaskRunRepository()
        self._task_lookup = {task.name: task for task in dag.tasks}
        self._execution_order = self._validate_and_sort()

    def _validate_and_sort(self) -> list[str]:
        for task in self.dag.tasks:
            for dep in task.depends_on:
                if dep not in self._task_lookup:
                    raise ValueError(f"Task '{task.name}' depends on unknown task '{dep}'")

        visiting: set[str] = set()
        visited: set[str] = set()
        order: list[str] = []

        def dfs(task_name: str) -> None:
            if task_name in visiting:
                raise ValueError("Circular dependency detected in DAG")
            if task_name in visited:
                return
            visiting.add(task_name)
            task = self._task_lookup[task_name]
            for dep in task.depends_on:
                dfs(dep)
            visiting.remove(task_name)
            visited.add(task_name)
            order.append(task_name)

        for task in self.dag.tasks:
            dfs(task.name)
        return order

    def get_execution_order(self) -> list[str]:
        return list(self._execution_order)

    def run(self) -> DAGRunResult:
        now = datetime.now(timezone.utc).isoformat()
        dag_run = self.dag_repo.insert(
            {
                "id": str(uuid4()),
                "dag_name": self.dag.name,
                "status": "running",
                "started_at": now,
                "completed_at": None,
                "created_at": now,
            }
        )
        run_id = dag_run["id"]

        results: dict[str, TaskResult] = {}
        task_run_ids: dict[str, str] = {}
        for task_name in self._execution_order:
            row = self.task_repo.insert(
                {
                    "id": str(uuid4()),
                    "dag_run_id": run_id,
                    "task_name": task_name,
                    "status": "pending",
                    "depends_on": list(self._task_lookup[task_name].depends_on),
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                    "result": None,
                }
            )
            task_run_ids[task_name] = row["id"]
            results[task_name] = TaskResult(task_name=task_name, status="pending")

        for task_name in self._execution_order:
            task = self._task_lookup[task_name]
            dependencies = task.depends_on
            if any(results[dep].status in {"failed", "skipped"} for dep in dependencies):
                completed_at = datetime.now(timezone.utc).isoformat()
                results[task_name] = TaskResult(task_name=task_name, status="skipped", completed_at=completed_at)
                self.task_repo.update(task_run_ids[task_name], {"status": "skipped", "completed_at": completed_at})
                continue

            started_at = datetime.now(timezone.utc).isoformat()
            self.task_repo.update(task_run_ids[task_name], {"status": "running", "started_at": started_at})
            try:
                outcome = task.fn()
                completed_at = datetime.now(timezone.utc).isoformat()
                result_payload = outcome if isinstance(outcome, dict) else {"value": outcome}
                results[task_name] = TaskResult(
                    task_name=task_name,
                    status="succeeded",
                    started_at=started_at,
                    completed_at=completed_at,
                    result=result_payload,
                )
                self.task_repo.update(
                    task_run_ids[task_name],
                    {"status": "succeeded", "completed_at": completed_at, "result": result_payload},
                )
                if self.audit_store:
                    self.audit_store.log(
                        action="task_succeeded",
                        component="dag_runner",
                        output_reference=f"{run_id}:{task_name}",
                        detail={"dag_name": self.dag.name, "task_name": task_name, "result": result_payload},
                    )
            except Exception as exc:
                completed_at = datetime.now(timezone.utc).isoformat()
                results[task_name] = TaskResult(
                    task_name=task_name,
                    status="failed",
                    started_at=started_at,
                    completed_at=completed_at,
                    error_message=str(exc),
                )
                self.task_repo.update(
                    task_run_ids[task_name],
                    {"status": "failed", "completed_at": completed_at, "error_message": str(exc)},
                )
                if self.audit_store:
                    self.audit_store.log(
                        action="task_failed",
                        component="dag_runner",
                        output_reference=f"{run_id}:{task_name}",
                        detail={"dag_name": self.dag.name, "task_name": task_name, "error": str(exc)},
                    )

        final_status = "failed" if any(result.status == "failed" for result in results.values()) else "succeeded"
        completed_at = datetime.now(timezone.utc).isoformat()
        self.dag_repo.update(run_id, {"status": final_status, "completed_at": completed_at})
        return DAGRunResult(
            run_id=run_id,
            dag_name=self.dag.name,
            status=final_status,
            task_results=[results[name] for name in self._execution_order],
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.dag_repo.get(run_id)
        if not run:
            return None
        tasks = self.task_repo.get_by_run(run_id)
        tasks.sort(key=lambda row: row["task_name"])
        return {"run": run, "tasks": tasks}


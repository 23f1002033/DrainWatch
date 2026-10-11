from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Worker:
    id: str
    name: str


class WorkerDirectory(Protocol):
    def list_workers(self, tenant_id: str) -> list[Worker]: ...


class StaticDirectory:
    """Local and test directory. Production reads the Cognito field_worker group (M2)."""

    def __init__(self, workers: dict[str, list[Worker]]) -> None:
        self._workers = workers

    def list_workers(self, tenant_id: str) -> list[Worker]:
        return list(self._workers.get(tenant_id, []))


LOCAL_WORKERS = {
    "demo-campus": [Worker("fw-01", "Field Worker 01"), Worker("fw-02", "Field Worker 02")],
    "other-campus": [Worker("fw-91", "Field Worker 91")],
}

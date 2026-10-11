import itertools
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from api.app import create_app
from api.service import IncidentService
from api.settings import Settings
from auth.directory import LOCAL_WORKERS, StaticDirectory
from repo.dynamo import DynamoRepo, create_table
from repo.memory import InMemoryRepo
from repo.storage import StubSigner

DEMO = "demo-campus"
OTHER = "other-campus"


def staff(sub: str, groups: str, tenant: str = DEMO) -> dict[str, str]:
    return {"X-Stub-Sub": sub, "X-Stub-Groups": groups, "X-Stub-Tenant": tenant}


OP = staff("op-01", "operator")
FW1 = staff("fw-01", "field_worker")
FW2 = staff("fw-02", "field_worker")
OTHER_OP = staff("op-91", "operator", OTHER)
OTHER_FW = staff("fw-91", "field_worker", OTHER)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(params=["memory", "dynamo"])
def repo(request):
    if request.param == "memory":
        yield InMemoryRepo()
        return
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-south-1")
        create_table(client, "drainwatch-test")
        yield DynamoRepo(client, "drainwatch-test")


@pytest.fixture
def service(repo, clock) -> IncidentService:
    return IncidentService(
        repo, StaticDirectory(LOCAL_WORKERS), StubSigner(), frozenset({DEMO, OTHER}), clock
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="local", repo="memory", tenants=frozenset({DEMO, OTHER}))


@pytest.fixture
def client(service, settings) -> TestClient:
    return TestClient(create_app(service, settings), raise_server_exceptions=False)


_keys = itertools.count()


def report(client, tenant=DEMO, key=None, **body) -> str:
    payload = {"type": "waterlogging", "description": "Water near hostel gate", **body}
    key = key or f"key-{next(_keys):08d}"
    resp = client.post(
        f"/api/v1/public/{tenant}/incidents", json=payload, headers={"Idempotency-Key": key}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["reference"]


def find_by_reference(client, reference: str, headers=OP) -> dict:
    cursor = None
    while True:
        params = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        body = client.get("/api/v1/incidents", params=params, headers=headers).json()
        for item in body["items"]:
            if item["reference"] == reference:
                return item
        cursor = body["next_cursor"]
        if not cursor:
            raise AssertionError(f"{reference} not in queue")


def new_incident(client, tenant=DEMO, headers=OP, **body) -> dict:
    return find_by_reference(client, report(client, tenant, **body), headers)


def post(client, inc: dict, path: str, headers=OP, **body):
    body.setdefault("expected_version", inc["version"])
    return client.post(f"/api/v1/incidents/{inc['id']}/{path}", json=body, headers=headers)


def step(client, inc: dict, path: str, headers=OP, **body) -> dict:
    resp = post(client, inc, path, headers, **body)
    assert resp.status_code == 200, resp.text
    return resp.json()


PATH_TO = {
    "reported": [],
    "triaged": [("triage", OP, {"severity": "S2", "reason": "ponding near library"})],
}
PATH_TO["assigned"] = [
    *PATH_TO["triaged"],
    ("assignments", OP, {"worker_id": "fw-01", "reason": "nearest crew"}),
]
PATH_TO["in_progress"] = [*PATH_TO["assigned"], ("transitions", FW1, {"to": "in_progress"})]
PATH_TO["resolved"] = [
    *PATH_TO["in_progress"],
    ("transitions", FW1, {"to": "resolved", "note": "cleared silt from grate"}),
]
PATH_TO["closed"] = [*PATH_TO["resolved"], ("transitions", OP, {"to": "closed"})]


def incident_in(client, status: str) -> dict:
    inc = new_incident(client)
    for path, headers, body in PATH_TO[status]:
        inc = step(client, inc, path, headers, **body)
    assert inc["status"] == status
    return inc

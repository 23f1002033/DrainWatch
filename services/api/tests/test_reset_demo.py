import importlib.util
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from api.service import IncidentService
from domain.model import Actor, Member, Role, Severity
from repo.dynamo import DynamoRepo, create_table
from repo.storage import StubStore
from tests.conftest import DEMO, OTHER, FakeClock

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "reset_demo.py"
spec = importlib.util.spec_from_file_location("reset_demo", SCRIPT)
reset_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset_demo)

BODY = {"type": "waterlogging", "description": "water at gate"}


@pytest.fixture
def seeded():
    with mock_aws():
        db = boto3.client("dynamodb", region_name="ap-south-1")
        create_table(db, "dw")
        repo = DynamoRepo(db, "dw")
        clock = FakeClock()
        service = IncidentService(repo, StubStore(), frozenset({DEMO, OTHER}), clock)
        for tenant in (DEMO, OTHER):
            repo.put_member(Member(tenant, f"op-{tenant}", "Op", Role.OPERATOR))
            for n in range(30):
                service.report(tenant, f"{tenant}-key-{n:03d}", BODY)
        op = Actor(f"op-{DEMO}", Role.OPERATOR, DEMO)
        first = repo.list_incidents(DEMO, reset_demo_filter(), None, 1).items[0]
        service.triage(op, first.id, 1, Severity.S2, "ponding")
        yield repo


def reset_demo_filter():
    from repo.base import QueueFilter

    return QueueFilter()


def test_dry_run_counts_and_deletes_nothing(seeded, capsys):
    repo = seeded
    assert reset_demo.main([DEMO, "--table", "dw", "--dry-run"], ask=pytest.fail) == 0
    assert "30 incidents, 31 events, 30 idempotency" in capsys.readouterr().out
    assert len(repo.list_incidents(DEMO, reset_demo_filter(), None, 100).items) == 30


def test_wrong_confirmation_aborts(seeded):
    repo = seeded
    assert reset_demo.main([DEMO, "--table", "dw"], ask=lambda _: "yes") == 1
    assert len(repo.list_incidents(DEMO, reset_demo_filter(), None, 100).items) == 30


def test_reset_one_tenant_keeps_members_and_other_tenant(seeded):
    repo = seeded
    ids = [i.id for i in repo.list_incidents(DEMO, reset_demo_filter(), None, 100).items]
    assert reset_demo.main([DEMO, "--table", "dw"], ask=lambda _: DEMO) == 0
    assert repo.list_incidents(DEMO, reset_demo_filter(), None, 100).items == []
    assert all(repo.list_events(DEMO, i) == [] for i in ids)
    assert repo.get_idempotency(DEMO, f"{DEMO}-key-000", 0) is None
    assert [m.sub for m in repo.list_members(DEMO)] == [f"op-{DEMO}"]
    assert len(repo.list_incidents(OTHER, reset_demo_filter(), None, 100).items) == 30
    assert repo.get_idempotency(OTHER, f"{OTHER}-key-000", 0) is not None

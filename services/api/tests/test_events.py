import pytest

from domain.model import Event, Role
from repo.base import ConditionFailed
from tests.conftest import DEMO, FW1, OP, incident_in, step


def events(client, inc, headers=OP):
    resp = client.get(f"/api/v1/incidents/{inc['id']}/events", headers=headers)
    assert resp.status_code == 200
    return resp.json()["items"]


def test_events_only_grow_and_never_change(client):
    inc = incident_in(client, "assigned")
    before = events(client, inc)
    inc = step(client, inc, "transitions", FW1, to="in_progress")
    after = events(client, inc)
    assert after[: len(before)] == before
    assert len(after) == len(before) + 1
    last = after[-1]
    assert last["action"] == "start"
    assert last["actor_sub"] == "fw-01"
    assert last["actor_role"] == "field_worker"
    assert last["before"]["status"] == "assigned"
    assert last["after"]["status"] == "in_progress"
    assert last["ts"]


def test_failed_change_writes_no_event(client):
    inc = incident_in(client, "reported")
    count = len(events(client, inc))
    client.post(
        f"/api/v1/incidents/{inc['id']}/transitions",
        json={"to": "closed", "expected_version": inc["version"]},
        headers=OP,
    )
    client.post(
        f"/api/v1/incidents/{inc['id']}/triage",
        json={"severity": "S1", "reason": "x", "expected_version": 99},
        headers=OP,
    )
    assert len(events(client, inc)) == count


def test_repo_refuses_to_overwrite_an_event(client, service):
    inc = incident_in(client, "triaged")
    current = service.repo.get_incident(DEMO, inc["id"])
    existing = service.repo.list_events(DEMO, inc["id"])[-1]
    forged = Event(
        tenant_id=DEMO,
        incident_id=inc["id"],
        id=existing.id,
        actor_sub="attacker",
        actor_role=Role.OPERATOR,
        action="triage",
        before=None,
        after={"status": "closed"},
        ts=existing.ts,
    )
    bumped = current.with_changes(version=current.version + 1)
    with pytest.raises(ConditionFailed):
        service.repo.commit_change(bumped, current.version, current.status, forged)
    assert service.repo.list_events(DEMO, inc["id"])[-1] == existing
    assert service.repo.get_incident(DEMO, inc["id"]).version == current.version


def test_repo_has_no_event_mutation_methods(repo):
    names = {n for n in dir(repo) if not n.startswith("_")}
    assert not {n for n in names if "event" in n} - {"list_events"}


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_no_http_route_mutates_events(client, method):
    inc = incident_in(client, "reported")
    resp = client.request(method.upper(), f"/api/v1/incidents/{inc['id']}/events", headers=OP)
    assert resp.status_code == 405

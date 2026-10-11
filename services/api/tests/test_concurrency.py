import threading

import pytest

from domain.errors import VersionConflict
from domain.model import Actor, Role, Severity
from tests.conftest import DEMO, OP, incident_in, post

OPERATOR = Actor("op-01", Role.OPERATOR, DEMO)


class RaceRepo:
    """Holds every reader at a barrier so both requests see the same version."""

    def __init__(self, inner, parties: int):
        self._inner = inner
        self._barrier = threading.Barrier(parties)

    def get_incident(self, tenant_id, incident_id):
        found = self._inner.get_incident(tenant_id, incident_id)
        self._barrier.wait(timeout=5)
        return found

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.mark.parametrize("attempt", range(3))
@pytest.mark.parametrize("start", ["reported", "triaged"])
def test_concurrent_update_exactly_one_conflict(client, service, start, attempt):
    inc = incident_in(client, start)
    service.repo = RaceRepo(service.repo, parties=2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def triage(severity):
        try:
            service.triage(OPERATOR, inc["id"], inc["version"], severity, "race")
            result = "ok"
        except VersionConflict:
            result = "conflict"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=triage, args=(s,)) for s in (Severity.S1, Severity.S3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    service.repo = service.repo._inner

    assert sorted(outcomes) == ["conflict", "ok"]
    events = service.repo.list_events(DEMO, inc["id"])
    assert [e.action for e in events].count("triage") == (1 if start == "reported" else 2)
    stored = service.repo.get_incident(DEMO, inc["id"])
    assert stored.version == inc["version"] + 1
    assert len(events) == stored.version


def test_stale_version_is_409_over_http(client):
    inc = incident_in(client, "reported")
    first = post(client, inc, "triage", OP, severity="S2", reason="first")
    second = post(client, inc, "triage", OP, severity="S1", reason="second")
    assert first.status_code == 200
    assert second.status_code == 409
    err = second.json()["error"]
    assert err["code"] == "VERSION_CONFLICT"
    assert set(err) == {"code", "message", "request_id"}

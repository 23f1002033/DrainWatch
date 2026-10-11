import itertools

import pytest

from tests.conftest import FW1, OP, incident_in, post, step

STATUSES = ["reported", "triaged", "assigned", "in_progress", "resolved", "closed"]
LEGAL = {
    ("assigned", "in_progress"): FW1,
    ("in_progress", "resolved"): FW1,
    ("resolved", "closed"): OP,
    ("resolved", "in_progress"): OP,
    ("closed", "triaged"): OP,
}


@pytest.mark.parametrize("src,dst", list(itertools.product(STATUSES, STATUSES)))
def test_transition_endpoint_matrix(client, src, dst):
    inc = incident_in(client, src)
    actor = LEGAL.get((src, dst), OP)
    resp = post(client, inc, "transitions", actor, to=dst, note="checked on site")
    if (src, dst) in LEGAL:
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == dst
        assert resp.json()["version"] == inc["version"] + 1
    else:
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "ILLEGAL_TRANSITION"
        for retry_actor in (FW1,):
            again = post(client, inc, "transitions", retry_actor, to=dst, note="x")
            assert again.status_code == 409


@pytest.mark.parametrize("src", STATUSES)
def test_triage_endpoint_matrix(client, src):
    inc = incident_in(client, src)
    resp = post(client, inc, "triage", severity="S1", reason="near transformer")
    if src in ("reported", "triaged"):
        assert resp.status_code == 200
        assert resp.json()["severity"] == "S1"
    else:
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ILLEGAL_TRANSITION"


@pytest.mark.parametrize("src", STATUSES)
def test_assign_endpoint_matrix(client, src):
    inc = incident_in(client, src)
    resp = post(client, inc, "assignments", worker_id="fw-02", reason="rebalance")
    if src in ("triaged", "assigned"):
        assert resp.status_code == 200
        assert resp.json()["assigned_to"] == "fw-02"
    else:
        assert resp.status_code == 409


def test_full_lifecycle_with_failed_verification_and_reopen(client):
    inc = incident_in(client, "resolved")
    inc = step(client, inc, "transitions", OP, to="in_progress", note="water still pooling")
    inc = step(client, inc, "transitions", FW1, to="resolved", note="replaced grate")
    inc = step(client, inc, "transitions", OP, to="closed")
    inc = step(client, inc, "transitions", OP, to="triaged", note="flooded again")
    assert inc["assigned_to"] is None
    inc = step(client, inc, "assignments", OP, worker_id="fw-02", reason="fresh crew")
    assert inc["status"] == "assigned"

    events = client.get(f"/api/v1/incidents/{inc['id']}/events", headers=OP).json()["items"]
    assert [e["action"] for e in events] == [
        "report",
        "triage",
        "assign",
        "start",
        "resolve",
        "verification_failed",
        "resolve",
        "close",
        "reopen",
        "assign",
    ]
    assert [e["after"]["version"] for e in events] == list(range(1, 11))


@pytest.mark.parametrize(
    "path,body",
    [
        ("triage", {"severity": "S2"}),
        ("assignments", {"worker_id": "fw-01", "reason": "  "}),
    ],
)
def test_reason_required(client, path, body):
    inc = incident_in(client, "triaged" if path == "assignments" else "reported")
    resp = post(client, inc, path, **body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_resolve_needs_summary(client):
    inc = incident_in(client, "in_progress")
    resp = post(client, inc, "transitions", FW1, to="resolved")
    assert resp.status_code == 422


def test_assign_unknown_or_foreign_worker(client):
    inc = incident_in(client, "triaged")
    for worker in ("nobody", "fw-91"):
        resp = post(client, inc, "assignments", worker_id=worker, reason="x")
        assert resp.status_code == 422
        assert resp.json()["error"]["message"] == "unknown worker"

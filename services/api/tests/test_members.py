from domain.model import Member, Role
from tests.conftest import DEMO, FW1, OP, OTHER_OP, incident_in, post


def test_workers_come_from_member_items(client, service):
    names = {w["id"]: w["name"] for w in client.get("/api/v1/workers", headers=OP).json()["items"]}
    assert names == {"fw-01": "Field Worker 01", "fw-02": "Field Worker 02"}
    service.repo.put_member(Member(DEMO, "fw-03", "Field Worker 03", Role.FIELD_WORKER))
    ids = {w["id"] for w in client.get("/api/v1/workers", headers=OP).json()["items"]}
    assert ids == {"fw-01", "fw-02", "fw-03"}
    other = client.get("/api/v1/workers", headers=OTHER_OP).json()["items"]
    assert [w["id"] for w in other] == ["fw-91"]


def test_operator_member_cannot_be_assigned(client):
    inc = incident_in(client, "triaged")
    resp = post(client, inc, "assignments", OP, worker_id="op-01", reason="x")
    assert resp.status_code == 422


def test_new_member_can_be_assigned_and_start(client, service):
    service.repo.put_member(Member(DEMO, "fw-03", "Field Worker 03", Role.FIELD_WORKER))
    inc = incident_in(client, "triaged")
    inc = post(client, inc, "assignments", OP, worker_id="fw-03", reason="new hire").json()
    fw3 = {**FW1, "X-Stub-Sub": "fw-03"}
    assert post(client, inc, "transitions", fw3, to="in_progress").status_code == 200

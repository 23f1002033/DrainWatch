import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.settings import Settings
from auth.identity import actor_from_claims, claims_from_aws_event, parse_groups
from domain.errors import Forbidden, Unauthorized
from domain.model import Role
from tests.conftest import (
    FW1,
    FW2,
    OP,
    OTHER,
    OTHER_FW,
    OTHER_OP,
    incident_in,
    new_incident,
    post,
    staff,
)


def test_field_worker_cannot_use_operator_actions(client):
    inc = incident_in(client, "reported")
    assert post(client, inc, "triage", FW1, severity="S1", reason="r").status_code == 403
    triaged = incident_in(client, "triaged")
    resp = post(client, triaged, "assignments", FW1, worker_id="fw-01", reason="me")
    assert resp.status_code == 403
    resolved = incident_in(client, "resolved")
    assert post(client, resolved, "transitions", FW1, to="closed").status_code == 403
    assert client.get("/api/v1/workers", headers=FW1).status_code == 403


def test_operator_cannot_do_field_work(client):
    inc = incident_in(client, "assigned")
    resp = post(client, inc, "transitions", OP, to="in_progress")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_unassigned_field_worker_forbidden(client):
    inc = incident_in(client, "assigned")
    assert post(client, inc, "transitions", FW2, to="in_progress").status_code == 403
    resp = client.post(
        f"/api/v1/incidents/{inc['id']}/uploads",
        json={"content_type": "image/jpeg", "content_length": 100},
        headers=FW2,
    )
    assert resp.status_code == 403


def test_other_tenant_gets_404_everywhere(client):
    inc = incident_in(client, "assigned")
    base = f"/api/v1/incidents/{inc['id']}"
    for headers in (OTHER_OP, OTHER_FW):
        assert client.get(base, headers=headers).status_code == 404
        assert client.get(f"{base}/events", headers=headers).status_code == 404
        resp = post(client, inc, "transitions", headers, to="in_progress")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
    resp = post(client, inc, "assignments", OTHER_OP, worker_id="fw-91", reason="x")
    assert resp.status_code == 404
    up = client.post(
        f"{base}/uploads", json={"content_type": "image/png", "content_length": 1}, headers=OTHER_OP
    )
    assert up.status_code == 404


def test_unknown_id_and_other_tenant_look_the_same(client):
    inc = new_incident(client)
    missing = client.get("/api/v1/incidents/01J00000000000000000000000", headers=OTHER_OP)
    foreign = client.get(f"/api/v1/incidents/{inc['id']}", headers=OTHER_OP)
    assert missing.status_code == foreign.status_code == 404
    assert missing.json()["error"]["message"] == foreign.json()["error"]["message"]


def test_queue_and_workers_are_tenant_scoped(client):
    new_incident(client)
    other = new_incident(client, tenant=OTHER, headers=OTHER_OP)
    demo_items = client.get("/api/v1/incidents", headers=OP).json()["items"]
    other_items = client.get("/api/v1/incidents", headers=OTHER_OP).json()["items"]
    assert other["id"] not in {i["id"] for i in demo_items}
    assert [i["id"] for i in other_items] == [other["id"]]
    workers = client.get("/api/v1/workers", headers=OP).json()["items"]
    assert {w["id"] for w in workers} == {"fw-01", "fw-02"}


def test_cursor_from_other_tenant_does_not_cross(client):
    for _ in range(3):
        new_incident(client)
    new_incident(client, tenant=OTHER, headers=OTHER_OP)
    page = client.get("/api/v1/incidents", params={"limit": 1}, headers=OP).json()
    assert page["next_cursor"]
    crossed = client.get(
        "/api/v1/incidents", params={"cursor": page["next_cursor"]}, headers=OTHER_OP
    ).json()
    assert all(i["reference"] for i in crossed["items"])
    demo_ids = {i["id"] for i in client.get("/api/v1/incidents", headers=OP).json()["items"]}
    assert not demo_ids & {i["id"] for i in crossed["items"]}


def test_missing_identity_is_401(client):
    resp = client.get("/api/v1/incidents")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "headers",
    [staff("x", "reporter"), staff("x", ""), {"X-Stub-Sub": "x", "X-Stub-Groups": "operator"}],
)
def test_no_role_or_no_tenant_is_403(client, headers):
    assert client.get("/api/v1/incidents", headers=headers).status_code == 403


def test_stub_headers_ignored_outside_local(service):
    prod = TestClient(create_app(service, Settings(app_env="prod", tenants=frozenset({OTHER}))))
    assert prod.get("/api/v1/incidents", headers=OP).status_code == 401


def test_claims_come_from_api_gateway_jwt():
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "abc",
                        "cognito:groups": "[operator]",
                        "custom:tenant_id": "demo-campus",
                    }
                }
            }
        }
    }
    actor = actor_from_claims(claims_from_aws_event(event))
    assert (actor.sub, actor.role, actor.tenant_id) == ("abc", Role.OPERATOR, "demo-campus")
    assert parse_groups("[field_worker operator]") == {"field_worker", "operator"}
    assert parse_groups(["field_worker"]) == {"field_worker"}
    with pytest.raises(Unauthorized):
        actor_from_claims({})
    with pytest.raises(Forbidden):
        actor_from_claims({"sub": "a", "cognito:groups": "operator"})


def test_public_route_has_no_read(client):
    report_path = "/api/v1/public/demo-campus/incidents"
    assert client.get(report_path).status_code == 405
    inc = new_incident(client)
    assert client.get(f"{report_path}/{inc['id']}").status_code == 404


def test_public_unknown_tenant_404(client):
    resp = client.post(
        "/api/v1/public/no-such-campus/incidents",
        json={"type": "waterlogging", "description": "water"},
        headers={"Idempotency-Key": "abcdefgh1"},
    )
    assert resp.status_code == 404

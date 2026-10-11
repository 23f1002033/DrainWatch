from tests.conftest import FW1, OP, OTHER_FW, OTHER_OP, staff


def members(client, headers):
    return client.get("/api/v1/members", headers=headers)


def test_members_visible_to_both_roles(client):
    expected = [
        {"id": "fw-01", "name": "Field Worker 01", "role": "field_worker"},
        {"id": "fw-02", "name": "Field Worker 02", "role": "field_worker"},
        {"id": "op-01", "name": "Operator 01", "role": "operator"},
    ]
    for headers in (OP, FW1):
        resp = members(client, headers)
        assert resp.status_code == 200
        assert sorted(resp.json()["items"], key=lambda m: m["id"]) == expected


def test_members_are_tenant_scoped(client):
    for headers in (OTHER_OP, OTHER_FW):
        ids = {m["id"] for m in members(client, headers).json()["items"]}
        assert ids == {"op-91", "fw-91"}


def test_members_needs_identity_and_staff_role(client):
    assert client.get("/api/v1/members").status_code == 401
    assert members(client, staff("x", "reporter")).status_code == 403


def test_workers_unchanged(client):
    resp = client.get("/api/v1/workers", headers=OP).json()["items"]
    assert resp == [
        {"id": "fw-01", "name": "Field Worker 01"},
        {"id": "fw-02", "name": "Field Worker 02"},
    ]
    assert client.get("/api/v1/workers", headers=FW1).status_code == 403

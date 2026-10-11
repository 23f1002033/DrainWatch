from tests.conftest import OP


def test_error_envelope_on_validation(client):
    resp = client.post(
        "/api/v1/public/demo-campus/incidents",
        json={"type": "volcano", "description": "x"},
        headers={"Idempotency-Key": "abcdefgh12"},
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert set(err) == {"code", "message", "request_id"}
    assert err["request_id"] == resp.headers["X-Request-Id"]


def test_error_envelope_on_unknown_route(client):
    resp = client.get("/api/v1/nope", headers=OP)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_fields_rejected(client):
    resp = client.post(
        "/api/v1/public/demo-campus/incidents",
        json={"type": "waterlogging", "description": "water", "status": "closed"},
        headers={"Idempotency-Key": "abcdefgh13"},
    )
    assert resp.status_code == 422


def test_malformed_incident_id_is_404(client):
    assert client.get("/api/v1/incidents/not-a-ulid", headers=OP).status_code == 404

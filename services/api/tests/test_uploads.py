import boto3
import pytest
from moto import mock_aws

from repo.storage import MAX_UPLOAD_BYTES, S3Signer
from tests.conftest import DEMO, FW1, OP, incident_in, step


def presign(client, inc, headers=FW1, content_type="image/jpeg", size=1000):
    return client.post(
        f"/api/v1/incidents/{inc['id']}/uploads",
        json={"content_type": content_type, "content_length": size},
        headers=headers,
    )


def evidence(client, inc, key, kind, headers=FW1):
    return client.post(
        f"/api/v1/incidents/{inc['id']}/evidence", json={"key": key, "kind": kind}, headers=headers
    )


def test_before_and_after_evidence_flow(client):
    inc = incident_in(client, "assigned")
    up = presign(client, inc)
    assert up.status_code == 201
    body = up.json()
    assert body["key"].startswith(f"{DEMO}/incidents/{inc['id']}/")
    assert body["key"].endswith(".jpg")
    assert body["method"] == "PUT"
    assert body["headers"]["Content-Type"] == "image/jpeg"

    inc = evidence(client, inc, body["key"], "before").json()
    assert inc["evidence"][0]["kind"] == "before"
    inc = step(client, inc, "transitions", FW1, to="in_progress")
    after_key = presign(client, inc, content_type="image/webp").json()["key"]
    inc = evidence(client, inc, after_key, "after").json()
    assert [e["kind"] for e in inc["evidence"]] == ["before", "after"]

    events = client.get(f"/api/v1/incidents/{inc['id']}/events", headers=OP).json()["items"]
    added = [e for e in events if e["action"] == "add_evidence"]
    assert [e["after"]["evidence"]["key"] for e in added] == [body["key"], after_key]


def test_after_evidence_not_allowed_before_work_starts(client):
    inc = incident_in(client, "assigned")
    key = presign(client, inc).json()["key"]
    resp = evidence(client, inc, key, "after")
    assert resp.status_code == 409


def test_evidence_key_must_be_server_issued_for_this_incident(client):
    inc = incident_in(client, "assigned")
    other = incident_in(client, "assigned")
    foreign_key = presign(client, other).json()["key"]
    for key in (foreign_key, "evil.jpg", f"{DEMO}/incidents/{inc['id']}/../x.jpg"):
        resp = evidence(client, inc, key, "before")
        assert resp.status_code == 422, key


def test_duplicate_evidence_rejected(client):
    inc = incident_in(client, "assigned")
    key = presign(client, inc).json()["key"]
    assert evidence(client, inc, key, "before").status_code == 200
    assert evidence(client, inc, key, "before").status_code == 422


@pytest.mark.parametrize(
    "content_type,size",
    [
        ("image/gif", 10),
        ("application/pdf", 10),
        ("image/png", 0),
        ("image/png", MAX_UPLOAD_BYTES + 1),
    ],
)
def test_upload_limits(client, content_type, size):
    inc = incident_in(client, "assigned")
    resp = presign(client, inc, content_type=content_type, size=size)
    assert resp.status_code == 422


def test_operator_can_attach_evidence(client):
    inc = incident_in(client, "in_progress")
    key = presign(client, inc, headers=OP).json()["key"]
    assert evidence(client, inc, key, "after", headers=OP).status_code == 200


def test_s3_signer_signs_put_with_type_and_length():
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-south-1")
        signer = S3Signer(s3, "drainwatch-uploads")
        signed = signer.presign_put("t/incidents/x/a.jpg", "image/jpeg", 42)
    assert "drainwatch-uploads" in signed.url
    assert "X-Amz-Signature=" in signed.url
    assert "content-length" in signed.url.lower()
    assert "content-type" in signed.url.lower()

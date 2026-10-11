import base64
import json

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from repo.storage import MAX_UPLOAD_BYTES, S3Store, StoredObject
from tests.conftest import DEMO, FW1, OP, incident_in, step

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 1000


def presign(client, inc, headers=FW1, content_type="image/jpeg"):
    return client.post(
        f"/api/v1/incidents/{inc['id']}/uploads",
        json={"content_type": content_type},
        headers=headers,
    )


def upload(client, signed, data=JPEG, content_type=None):
    fields = dict(signed["fields"])
    if content_type:
        fields["Content-Type"] = content_type
    return client.post(
        "/_stub-upload", data=fields, files={"file": ("photo", data, fields["Content-Type"])}
    )


def presign_and_upload(client, inc, headers=FW1, content_type="image/jpeg", data=JPEG) -> str:
    signed = presign(client, inc, headers, content_type).json()
    assert upload(client, signed, data).status_code == 204
    return signed["key"]


def evidence(client, inc, key, kind, headers=FW1):
    return client.post(
        f"/api/v1/incidents/{inc['id']}/evidence", json={"key": key, "kind": kind}, headers=headers
    )


def test_presigned_post_shape(client):
    inc = incident_in(client, "assigned")
    resp = presign(client, inc)
    assert resp.status_code == 201
    body = resp.json()
    assert body["method"] == "POST"
    assert body["key"].startswith(f"{DEMO}/incidents/{inc['id']}/")
    assert body["key"].endswith(".jpg")
    assert body["fields"]["key"] == body["key"]
    assert body["fields"]["Content-Type"] == "image/jpeg"
    assert body["max_bytes"] == MAX_UPLOAD_BYTES


def test_before_and_after_evidence_flow(client):
    inc = incident_in(client, "assigned")
    before_key = presign_and_upload(client, inc)
    inc = evidence(client, inc, before_key, "before").json()
    assert inc["evidence"][0]["kind"] == "before"
    inc = step(client, inc, "transitions", FW1, to="in_progress")
    after_key = presign_and_upload(client, inc, content_type="image/webp")
    inc = evidence(client, inc, after_key, "after").json()
    assert [e["kind"] for e in inc["evidence"]] == ["before", "after"]

    events = client.get(f"/api/v1/incidents/{inc['id']}/events", headers=OP).json()["items"]
    added = [e for e in events if e["action"] == "add_evidence"]
    assert [e["after"]["evidence"]["key"] for e in added] == [before_key, after_key]


def test_evidence_rejected_when_not_uploaded(client):
    inc = incident_in(client, "assigned")
    key = presign(client, inc).json()["key"]
    resp = evidence(client, inc, key, "before")
    assert resp.status_code == 422
    assert resp.json()["error"]["message"] == "object not uploaded"


def test_evidence_rejected_when_oversized(client, service):
    inc = incident_in(client, "assigned")
    key = presign(client, inc).json()["key"]
    service.store.put(key, MAX_UPLOAD_BYTES + 1, "image/jpeg")
    resp = evidence(client, inc, key, "before")
    assert resp.status_code == 422
    assert "bytes" in resp.json()["error"]["message"]


def test_evidence_rejected_when_type_mismatch(client):
    inc = incident_in(client, "assigned")
    signed = presign(client, inc).json()
    assert upload(client, signed, content_type="image/png").status_code == 204
    resp = evidence(client, inc, signed["key"], "before")
    assert resp.status_code == 422
    assert resp.json()["error"]["message"] == "object content type does not match its key"


def test_stub_upload_applies_policy(client):
    inc = incident_in(client, "assigned")
    signed = presign(client, inc).json()
    assert upload(client, signed, data=b"x" * (MAX_UPLOAD_BYTES + 1)).status_code == 400
    assert upload(client, signed, data=b"").status_code == 400
    assert upload(client, signed, content_type="image/gif").status_code == 400


def test_after_evidence_not_allowed_before_work_starts(client):
    inc = incident_in(client, "assigned")
    key = presign_and_upload(client, inc)
    assert evidence(client, inc, key, "after").status_code == 409


def test_unassigned_worker_cannot_register_even_uploaded_object(client):
    from tests.conftest import FW2

    inc = incident_in(client, "assigned")
    key = presign_and_upload(client, inc)
    assert evidence(client, inc, key, "before", headers=FW2).status_code == 403


def test_evidence_key_must_be_server_issued_for_this_incident(client):
    inc = incident_in(client, "assigned")
    other = incident_in(client, "assigned")
    foreign_key = presign_and_upload(client, other)
    for key in (foreign_key, "evil.jpg", f"{DEMO}/incidents/{inc['id']}/../x.jpg"):
        resp = evidence(client, inc, key, "before")
        assert resp.status_code == 422, key


def test_duplicate_evidence_rejected(client):
    inc = incident_in(client, "assigned")
    key = presign_and_upload(client, inc)
    assert evidence(client, inc, key, "before").status_code == 200
    assert evidence(client, inc, key, "before").status_code == 422


@pytest.mark.parametrize("content_type", ["image/gif", "application/pdf", "text/html"])
def test_upload_type_allowlist(client, content_type):
    inc = incident_in(client, "assigned")
    assert presign(client, inc, content_type=content_type).status_code == 422


def test_operator_can_attach_evidence(client):
    inc = incident_in(client, "in_progress")
    key = presign_and_upload(client, inc, headers=OP)
    assert evidence(client, inc, key, "after", headers=OP).status_code == 200


# S3Store against moto


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket="dw-evidence",
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        yield client


def test_s3_presigned_post_policy(s3):
    signed = S3Store(s3, "dw-evidence").presign_post("t/incidents/x/a.jpg", "image/jpeg")
    assert signed.fields["key"] == "t/incidents/x/a.jpg"
    assert signed.fields["Content-Type"] == "image/jpeg"
    policy = json.loads(base64.b64decode(signed.fields["policy"]))
    conditions = policy["conditions"]
    assert ["content-length-range", 1, MAX_UPLOAD_BYTES] in conditions
    assert {"Content-Type": "image/jpeg"} in conditions
    assert {"key": "t/incidents/x/a.jpg"} in conditions
    assert {"bucket": "dw-evidence"} in conditions
    assert "x-amz-signature" in signed.fields


def test_s3_head(s3):
    store = S3Store(s3, "dw-evidence")
    s3.put_object(Bucket="dw-evidence", Key="k.jpg", Body=JPEG, ContentType="image/jpeg")
    assert store.head("k.jpg") == StoredObject(len(JPEG), "image/jpeg")
    assert store.head("missing.jpg") is None


def test_s3_head_forbidden_counts_as_missing():
    class Denied:
        def head_object(self, **_):
            raise ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")

    assert S3Store(Denied(), "b").head("k.jpg") is None


def test_s3_head_other_errors_raise():
    class Broken:
        def head_object(self, **_):
            raise ClientError({"Error": {"Code": "500", "Message": "x"}}, "HeadObject")

    with pytest.raises(ClientError):
        S3Store(Broken(), "b").head("k.jpg")

import json
from urllib.parse import parse_qs, urlparse

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws

from api.app import create_app
from api.service import IncidentService
from api.settings import Settings
from domain.model import Actor, EvidenceKind, Role
from repo.memory import InMemoryRepo
from repo.storage import DOWNLOAD_URL_TTL_SECONDS, S3Store
from tests.conftest import (
    DEMO,
    FW1,
    FW2,
    MEMBERS,
    OP,
    OTHER,
    OTHER_FW,
    OTHER_OP,
    incident_in,
    staff,
)
from tests.test_uploads import JPEG, evidence, presign_and_upload


def detail(client, inc, headers=OP):
    return client.get(f"/api/v1/incidents/{inc['id']}", headers=headers)


def with_evidence(client):
    inc = incident_in(client, "assigned")
    key = presign_and_upload(client, inc)
    return evidence(client, inc, key, "before").json(), key


def test_detail_has_presigned_url_per_evidence_item(client):
    inc, key = with_evidence(client)
    for headers in (OP, FW1, FW2):
        resp = detail(client, inc, headers)
        assert resp.status_code == 200
        [item] = resp.json()["evidence"]
        assert item["key"] == key
        assert item["url_expires_in"] == DOWNLOAD_URL_TTL_SECONDS
        assert "_stub-download/" in item["url"]


def test_stub_url_serves_the_uploaded_bytes(client):
    inc, _ = with_evidence(client)
    url = detail(client, inc).json()["evidence"][0]["url"]
    got = client.get(urlparse(url).path)
    assert got.status_code == 200
    assert got.content == JPEG
    assert got.headers["content-type"] == "image/jpeg"


def test_urls_only_on_detail(client):
    inc, _ = with_evidence(client)
    queue = client.get("/api/v1/incidents", headers=OP).json()["items"]
    assert all("url" not in e for i in queue for e in i["evidence"])
    events = client.get(f"/api/v1/incidents/{inc['id']}/events", headers=OP).text
    assert "_stub-download" not in events


def test_other_tenant_gets_404_and_no_url(client, service):
    inc, _ = with_evidence(client)
    calls = []
    original = service.store.presign_get
    service.store.presign_get = lambda key: calls.append(key) or original(key)
    for headers in (OTHER_OP, OTHER_FW):
        resp = detail(client, inc, headers)
        assert resp.status_code == 404
        assert "url" not in resp.text
    assert calls == []


def test_unauthenticated_and_roleless_get_no_url(client):
    inc, _ = with_evidence(client)
    assert client.get(f"/api/v1/incidents/{inc['id']}").status_code == 401
    assert detail(client, inc, staff("x", "reporter")).status_code == 403


def test_url_not_in_logs(client, captured):
    inc, _ = with_evidence(client)
    url = detail(client, inc).json()["evidence"][0]["url"]
    logged = captured.getvalue()
    assert logged
    assert url not in logged
    assert "_stub-download" not in logged


def test_s3_presigned_get_expires_in_300s_and_stays_out_of_logs(clock, captured):
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-south-1")
        s3.create_bucket(
            Bucket="dw-evidence", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )
        repo = InMemoryRepo()
        for member in MEMBERS:
            repo.put_member(member)
        service = IncidentService(repo, S3Store(s3, "dw-evidence"), frozenset({DEMO, OTHER}), clock)
        client = TestClient(
            create_app(service, Settings(app_env="local", tenants=frozenset({DEMO})))
        )
        inc = incident_in(client, "assigned")
        signed = client.post(
            f"/api/v1/incidents/{inc['id']}/uploads",
            json={"content_type": "image/jpeg"},
            headers=FW1,
        ).json()
        s3.put_object(Bucket="dw-evidence", Key=signed["key"], Body=JPEG, ContentType="image/jpeg")
        service.add_evidence(
            Actor("fw-01", Role.FIELD_WORKER, DEMO), inc["id"], signed["key"], EvidenceKind.BEFORE
        )
        url = detail(client, inc).json()["evidence"][0]["url"]

    query = parse_qs(urlparse(url).query)
    assert query["X-Amz-Expires"] == ["300"]
    assert "X-Amz-Signature" in query
    assert urlparse(url).path.endswith(signed["key"])
    logged = captured.getvalue()
    assert "X-Amz-Signature" not in logged
    assert all("url" not in json.loads(line) for line in logged.splitlines())

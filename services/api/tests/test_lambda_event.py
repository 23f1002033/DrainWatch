import json

from mangum import Mangum

from api.app import create_app
from api.service import IncidentService
from api.settings import Settings
from repo.storage import StubStore
from tests.conftest import DEMO, MEMBERS, OP, OTHER


def http_event(method, path, claims=None, headers=None, body=None):
    ctx = {
        "requestId": "apigw-req-1",
        "http": {"method": method, "path": path, "sourceIp": "1.2.3.4", "protocol": "HTTP/1.1"},
        "stage": "$default",
    }
    if claims is not None:
        ctx["authorizer"] = {"jwt": {"claims": claims, "scopes": None}}
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json", **(headers or {})},
        "requestContext": ctx,
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


class Ctx:
    aws_request_id = "lambda-req-1"


def handler(repo, clock):
    for member in MEMBERS:
        repo.put_member(member)
    service = IncidentService(repo, StubStore(), frozenset({DEMO, OTHER}), clock)
    app = create_app(service, Settings(app_env="prod", tenants=frozenset({DEMO, OTHER})))
    return Mangum(app, lifespan="off")


def test_identity_from_jwt_authorizer_claims(repo, clock):
    claims = {"sub": "op-01", "cognito:groups": "[operator]", "custom:tenant_id": DEMO}
    resp = handler(repo, clock)(http_event("GET", "/api/v1/workers", claims), Ctx())
    assert resp["statusCode"] == 200
    ids = {w["id"] for w in json.loads(resp["body"])["items"]}
    assert ids == {"fw-01", "fw-02"}
    assert resp["headers"]["x-request-id"] == "apigw-req-1"


def test_prod_ignores_stub_headers(repo, clock):
    resp = handler(repo, clock)(http_event("GET", "/api/v1/workers", None, OP), Ctx())
    assert resp["statusCode"] == 401


def test_public_report_without_authorizer(repo, clock):
    event = http_event(
        "POST",
        f"/api/v1/public/{DEMO}/incidents",
        headers={"idempotency-key": "lambda-key-1"},
        body={"type": "waterlogging", "description": "water at gate"},
    )
    resp = handler(repo, clock)(event, Ctx())
    assert resp["statusCode"] == 201
    assert json.loads(resp["body"])["reference"].startswith("DW-")

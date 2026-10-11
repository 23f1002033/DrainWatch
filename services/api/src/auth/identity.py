from collections.abc import Mapping
from typing import Any

from domain.errors import Forbidden, Unauthorized
from domain.model import Actor, Role

STUB_SUB = "x-stub-sub"
STUB_GROUPS = "x-stub-groups"
STUB_TENANT = "x-stub-tenant"


def parse_groups(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, list | tuple):
        return {str(g) for g in raw}
    text = str(raw).strip().strip("[]")
    return {g for g in text.replace(",", " ").split() if g}


def actor_from_claims(claims: Mapping[str, Any]) -> Actor:
    sub = claims.get("sub")
    if not sub:
        raise Unauthorized("missing identity")
    groups = parse_groups(claims.get("cognito:groups"))
    if Role.OPERATOR in groups:
        role = Role.OPERATOR
    elif Role.FIELD_WORKER in groups:
        role = Role.FIELD_WORKER
    else:
        raise Forbidden("no staff role")
    tenant = claims.get("custom:tenant_id")
    if not tenant:
        raise Forbidden("no tenant on identity")
    return Actor(sub=str(sub), role=role, tenant_id=str(tenant))


def claims_from_aws_event(event: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not event:
        return {}
    ctx = event.get("requestContext") or {}
    return ((ctx.get("authorizer") or {}).get("jwt") or {}).get("claims") or {}


def claims_from_stub_headers(headers: Mapping[str, str]) -> Mapping[str, Any]:
    return {
        "sub": headers.get(STUB_SUB),
        "cognito:groups": headers.get(STUB_GROUPS),
        "custom:tenant_id": headers.get(STUB_TENANT),
    }


def resolve_actor(
    headers: Mapping[str, str], aws_event: Mapping[str, Any] | None, app_env: str
) -> Actor:
    claims = claims_from_aws_event(aws_event)
    if not claims and app_env == "local":
        claims = claims_from_stub_headers(headers)
    return actor_from_claims(claims)

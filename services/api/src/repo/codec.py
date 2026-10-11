from dataclasses import asdict
from decimal import Decimal
from typing import Any

from domain.model import Event, Incident, IncidentType, Role, Severity, Status
from repo.base import EVT_PREFIX, INC_PREFIX, events_pk, tenant_pk


def to_dynamo_safe(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_dynamo_safe(v) for v in value]
    return value


def from_dynamo_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo_safe(v) for v in value]
    return value


def incident_to_item(inc: Incident) -> dict[str, Any]:
    data = asdict(inc)
    data["evidence"] = list(inc.evidence)
    data = {k: v for k, v in data.items() if v is not None}
    for name in ("type", "status", "severity"):
        if name in data:
            data[name] = str(data[name])
    return {"PK": tenant_pk(inc.tenant_id), "SK": INC_PREFIX + inc.id, **data}


def item_to_incident(item: dict[str, Any]) -> Incident:
    data = {k: v for k, v in item.items() if k not in ("PK", "SK")}
    data["type"] = IncidentType(data["type"])
    data["status"] = Status(data["status"])
    if data.get("severity"):
        data["severity"] = Severity(data["severity"])
    data["version"] = int(data["version"])
    for name in ("lat", "lng"):
        if data.get(name) is not None:
            data[name] = float(data[name])
    data["evidence"] = tuple(dict(e) for e in data.get("evidence", []))
    return Incident(**data)


def event_to_item(evt: Event) -> dict[str, Any]:
    data = {k: v for k, v in asdict(evt).items() if v is not None}
    data["actor_role"] = str(evt.actor_role)
    return {"PK": events_pk(evt.tenant_id, evt.incident_id), "SK": EVT_PREFIX + evt.id, **data}


def item_to_event(item: dict[str, Any]) -> Event:
    data = {k: v for k, v in item.items() if k not in ("PK", "SK")}
    data["actor_role"] = Role(data["actor_role"])
    data.setdefault("before", None)
    return Event(**data)

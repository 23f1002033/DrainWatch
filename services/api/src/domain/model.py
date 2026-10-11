from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    REPORTED = "reported"
    TRIAGED = "triaged"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Severity(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


class IncidentType(StrEnum):
    WATERLOGGING = "waterlogging"
    BLOCKED_DRAIN = "blocked_drain"


class Role(StrEnum):
    OPERATOR = "operator"
    FIELD_WORKER = "field_worker"
    PUBLIC = "public"


class EvidenceKind(StrEnum):
    BEFORE = "before"
    AFTER = "after"


@dataclass(frozen=True)
class Actor:
    sub: str
    role: Role
    tenant_id: str


@dataclass(frozen=True)
class Incident:
    tenant_id: str
    id: str
    reference: str
    type: IncidentType
    description: str
    status: Status
    version: int
    created_at: str
    updated_at: str
    landmark: str | None = None
    lat: float | None = None
    lng: float | None = None
    severity: Severity | None = None
    assigned_to: str | None = None
    resolution_summary: str | None = None
    evidence: tuple[dict[str, str], ...] = field(default_factory=tuple)

    def with_changes(self, **changes: Any) -> "Incident":
        return replace(self, **changes)


@dataclass(frozen=True)
class Event:
    tenant_id: str
    incident_id: str
    id: str
    actor_sub: str
    actor_role: Role
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any]
    ts: str
    note: str | None = None


AUDITED_FIELDS = ("status", "severity", "assigned_to", "version", "resolution_summary")


def snapshot(incident: Incident) -> dict[str, Any]:
    return {name: getattr(incident, name) for name in AUDITED_FIELDS}

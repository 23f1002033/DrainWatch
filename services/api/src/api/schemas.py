from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.model import Event, EvidenceKind, Incident, IncidentType, Severity, Status


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicReportIn(_In):
    type: IncidentType
    description: str = Field(min_length=3, max_length=1000)
    landmark: str | None = Field(default=None, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class TriageIn(_In):
    severity: Severity
    reason: str | None = Field(default=None, max_length=1000)
    expected_version: int = Field(ge=1)


class AssignIn(_In):
    worker_id: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=1000)
    expected_version: int = Field(ge=1)


class TransitionIn(_In):
    to: Status
    note: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=1)


class UploadIn(_In):
    content_type: str


class EvidenceIn(_In):
    key: str = Field(min_length=1, max_length=512)
    kind: EvidenceKind


def incident_out(inc: Incident) -> dict[str, Any]:
    data = asdict(inc)
    data.pop("tenant_id")
    data["evidence"] = list(inc.evidence)
    return data


def event_out(evt: Event) -> dict[str, Any]:
    data = asdict(evt)
    data.pop("tenant_id")
    return data

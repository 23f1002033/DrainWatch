from dataclasses import dataclass
from typing import Protocol

from domain.model import Event, Incident, Member, Severity, Status

INC_PREFIX = "INC#"
EVT_PREFIX = "EVT#"
IDEM_PREFIX = "IDEM#"
MEMBER_PREFIX = "MEMBER#"
IDEM_TTL_SECONDS = 24 * 3600
# Queue pages read at most this many DynamoDB pages before returning a partial page.
MAX_QUERY_PAGES = 5


def tenant_pk(tenant_id: str) -> str:
    return f"TENANT#{tenant_id}"


def events_pk(tenant_id: str, incident_id: str) -> str:
    return f"TENANT#{tenant_id}#INC#{incident_id}"


@dataclass(frozen=True)
class IdemRecord:
    tenant_id: str
    key: str
    body_hash: str
    incident_id: str
    reference: str
    expires_at: int


@dataclass(frozen=True)
class QueueFilter:
    status: Status | None = None
    severity: Severity | None = None
    type: str | None = None
    created_before_id: str | None = None


@dataclass(frozen=True)
class Page:
    items: list[Incident]
    next_cursor: str | None


class IdempotencyExists(Exception):
    def __init__(self, record: IdemRecord | None):
        super().__init__("idempotency key already used")
        self.record = record


class ConditionFailed(Exception):
    pass


class Repo(Protocol):
    def create_incident(
        self, incident: Incident, event: Event, idem: IdemRecord, now_epoch: int
    ) -> None:
        """Write idempotency record, incident and first event atomically.
        Raises IdempotencyExists if an unexpired record exists for the key."""

    def get_idempotency(self, tenant_id: str, key: str, now_epoch: int) -> IdemRecord | None: ...

    def get_incident(self, tenant_id: str, incident_id: str) -> Incident | None: ...

    def commit_change(
        self, after: Incident, expected_version: int, expected_status: Status, event: Event
    ) -> None:
        """Replace the incident and append the event in one transaction, conditioned on
        the stored version and status. Raises ConditionFailed otherwise."""

    def list_incidents(
        self, tenant_id: str, flt: QueueFilter, cursor: str | None, limit: int
    ) -> Page: ...

    def list_events(self, tenant_id: str, incident_id: str) -> list[Event]: ...

    def put_member(self, member: Member) -> None: ...

    def list_members(self, tenant_id: str) -> list[Member]: ...

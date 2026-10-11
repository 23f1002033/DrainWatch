import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from domain import lifecycle
from domain.errors import (
    BadRequest,
    Forbidden,
    IdempotencyKeyReused,
    Invalid,
    NotFound,
    VersionConflict,
)
from domain.ids import is_ulid, min_ulid_at, new_ulid, reference_code
from domain.model import (
    Actor,
    Event,
    EvidenceKind,
    Incident,
    IncidentType,
    Member,
    Role,
    Severity,
    Status,
    snapshot,
)
from repo.base import (
    IDEM_TTL_SECONDS,
    INC_PREFIX,
    ConditionFailed,
    IdempotencyExists,
    IdemRecord,
    Page,
    QueueFilter,
    Repo,
)
from repo.storage import (
    ALLOWED_CONTENT_TYPES,
    CONTENT_TYPE_FOR_EXT,
    MAX_UPLOAD_BYTES,
    EvidenceStore,
    PresignedPost,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def body_hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def evidence_prefix(tenant_id: str, incident_id: str) -> str:
    return f"{tenant_id}/incidents/{incident_id}/"


class IncidentService:
    def __init__(
        self,
        repo: Repo,
        store: EvidenceStore,
        tenants: frozenset[str],
        clock: Clock = utc_now,
    ) -> None:
        self.repo = repo
        self.store = store
        self.tenants = tenants
        self.clock = clock

    def report(self, tenant_id: str, idem_key: str, body: dict[str, Any]) -> str:
        if tenant_id not in self.tenants:
            raise NotFound("unknown tenant")
        now = self.clock()
        now_epoch = int(now.timestamp())
        digest = body_hash(body)

        existing = self.repo.get_idempotency(tenant_id, idem_key, now_epoch)
        if existing:
            return self._replay(existing, digest)

        incident_id = new_ulid(now)
        stamp = iso(now)
        incident = Incident(
            tenant_id=tenant_id,
            id=incident_id,
            reference=reference_code(incident_id),
            type=IncidentType(body["type"]),
            description=body["description"],
            landmark=body.get("landmark"),
            lat=body.get("lat"),
            lng=body.get("lng"),
            status=Status.REPORTED,
            version=1,
            created_at=stamp,
            updated_at=stamp,
        )
        event = Event(
            tenant_id=tenant_id,
            incident_id=incident_id,
            id=new_ulid(now),
            actor_sub="anonymous",
            actor_role=Role.PUBLIC,
            action="report",
            before=None,
            after=snapshot(incident),
            ts=stamp,
        )
        idem = IdemRecord(
            tenant_id=tenant_id,
            key=idem_key,
            body_hash=digest,
            incident_id=incident_id,
            reference=incident.reference,
            expires_at=now_epoch + IDEM_TTL_SECONDS,
        )
        try:
            self.repo.create_incident(incident, event, idem, now_epoch)
        except IdempotencyExists as exc:
            if exc.record is None:
                raise VersionConflict("concurrent request with the same key, retry") from exc
            return self._replay(exc.record, digest)
        return incident.reference

    @staticmethod
    def _replay(record: IdemRecord, digest: str) -> str:
        if record.body_hash != digest:
            raise IdempotencyKeyReused("Idempotency-Key was used with a different body")
        return record.reference

    def get(self, actor: Actor, incident_id: str) -> Incident:
        incident = (
            self.repo.get_incident(actor.tenant_id, incident_id) if is_ulid(incident_id) else None
        )
        if incident is None:
            raise NotFound("incident not found")
        return incident

    def queue(
        self,
        actor: Actor,
        status: Status | None,
        severity: Severity | None,
        type_: IncidentType | None,
        older_than_hours: int | None,
        cursor: str | None,
        limit: int,
    ) -> Page:
        before_id = None
        if older_than_hours is not None:
            before_id = min_ulid_at(self.clock() - timedelta(hours=older_than_hours))
        if cursor is not None and not (
            cursor.startswith(INC_PREFIX) and is_ulid(cursor.removeprefix(INC_PREFIX))
        ):
            raise BadRequest("invalid cursor")
        flt = QueueFilter(status, severity, type_, before_id)
        return self.repo.list_incidents(actor.tenant_id, flt, cursor, limit)

    def events(self, actor: Actor, incident_id: str) -> list[Event]:
        self.get(actor, incident_id)
        return self.repo.list_events(actor.tenant_id, incident_id)

    def list_workers(self, actor: Actor) -> list[Member]:
        require_operator(actor)
        return self._field_workers(actor.tenant_id)

    def _field_workers(self, tenant_id: str) -> list[Member]:
        return [m for m in self.repo.list_members(tenant_id) if m.role is Role.FIELD_WORKER]

    def triage(self, actor, incident_id, expected_version, severity, reason) -> Incident:
        require_operator(actor)
        return self._apply(
            actor,
            incident_id,
            expected_version,
            lambda inc, now: lifecycle.triage(inc, actor, severity, reason, now),
        )

    def assign(self, actor, incident_id, expected_version, worker_id, reason) -> Incident:
        require_operator(actor)
        if worker_id not in {m.sub for m in self._field_workers(actor.tenant_id)}:
            raise Invalid("unknown worker")
        return self._apply(
            actor,
            incident_id,
            expected_version,
            lambda inc, now: lifecycle.assign(inc, actor, worker_id, reason, now),
        )

    def transition(self, actor, incident_id, expected_version, to: Status, note) -> Incident:
        return self._apply(
            actor,
            incident_id,
            expected_version,
            lambda inc, now: lifecycle.transition(inc, actor, to, note, now),
        )

    def presign_upload(
        self, actor: Actor, incident_id: str, content_type: str
    ) -> tuple[str, PresignedPost]:
        incident = self.get(actor, incident_id)
        if actor.role is Role.FIELD_WORKER and incident.assigned_to != actor.sub:
            raise Forbidden("only the assigned field worker can upload")
        ext = ALLOWED_CONTENT_TYPES.get(content_type)
        if ext is None:
            raise Invalid("content_type must be image/jpeg, image/png or image/webp")
        key = f"{evidence_prefix(actor.tenant_id, incident_id)}{new_ulid(self.clock())}.{ext}"
        return key, self.store.presign_post(key, content_type)

    def add_evidence(self, actor: Actor, incident_id: str, key: str, kind: EvidenceKind):
        prefix = evidence_prefix(actor.tenant_id, incident_id)
        name, _, ext = key.removeprefix(prefix).partition(".")
        if (
            not key.startswith(prefix)
            or not is_ulid(name)
            or ext not in ALLOWED_CONTENT_TYPES.values()
        ):
            raise Invalid("key must be one issued by the uploads endpoint for this incident")
        current = self.get(actor, incident_id)
        if any(e["key"] == key for e in current.evidence):
            raise Invalid("evidence already recorded")
        lifecycle.can_add_evidence(current, actor, kind)
        stored = self.store.head(key)
        if stored is None:
            raise Invalid("object not uploaded")
        if not 0 < stored.size <= MAX_UPLOAD_BYTES:
            raise Invalid(f"object must be between 1 and {MAX_UPLOAD_BYTES} bytes")
        if stored.content_type != CONTENT_TYPE_FOR_EXT[ext]:
            raise Invalid("object content type does not match its key")
        return self._apply(
            actor,
            incident_id,
            current.version,
            lambda inc, now: lifecycle.add_evidence(inc, actor, key, kind, now),
        )

    def _apply(self, actor: Actor, incident_id: str, expected_version: int, decide) -> Incident:
        current = self.get(actor, incident_id)
        if current.version != expected_version:
            raise VersionConflict(
                f"expected version {expected_version}, current is {current.version}"
            )
        now = self.clock()
        stamp = iso(now)
        change = decide(current, stamp)
        after_snap = snapshot(change.after)
        if change.detail:
            after_snap.update(change.detail)
        event = Event(
            tenant_id=actor.tenant_id,
            incident_id=incident_id,
            id=new_ulid(now),
            actor_sub=actor.sub,
            actor_role=actor.role,
            action=change.action,
            before=snapshot(current),
            after=after_snap,
            ts=stamp,
            note=change.note,
        )
        try:
            self.repo.commit_change(change.after, current.version, current.status, event)
        except ConditionFailed as exc:
            raise VersionConflict("incident was changed by another request") from exc
        return change.after


def require_operator(actor: Actor) -> None:
    if actor.role is not Role.OPERATOR:
        raise Forbidden("operator role required")

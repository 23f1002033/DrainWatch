from dataclasses import dataclass

from domain.errors import Forbidden, IllegalTransition, Invalid
from domain.model import Actor, EvidenceKind, Incident, Role, Severity, Status

S = Status


@dataclass(frozen=True)
class Rule:
    action: str
    role: Role
    assignee_only: bool = False
    note_required: bool = False


TRIAGE_FROM = frozenset({S.REPORTED, S.TRIAGED})
ASSIGN_FROM = frozenset({S.TRIAGED, S.ASSIGNED})

TRANSITIONS: dict[tuple[Status, Status], Rule] = {
    (S.ASSIGNED, S.IN_PROGRESS): Rule("start", Role.FIELD_WORKER, assignee_only=True),
    (S.IN_PROGRESS, S.RESOLVED): Rule(
        "resolve", Role.FIELD_WORKER, assignee_only=True, note_required=True
    ),
    (S.RESOLVED, S.CLOSED): Rule("close", Role.OPERATOR),
    (S.RESOLVED, S.IN_PROGRESS): Rule("verification_failed", Role.OPERATOR, note_required=True),
    (S.CLOSED, S.TRIAGED): Rule("reopen", Role.OPERATOR, note_required=True),
}

EVIDENCE_STATUSES = {
    EvidenceKind.BEFORE: frozenset({S.ASSIGNED, S.IN_PROGRESS}),
    EvidenceKind.AFTER: frozenset({S.IN_PROGRESS, S.RESOLVED}),
}


@dataclass(frozen=True)
class Change:
    action: str
    after: Incident
    note: str | None
    detail: dict | None = None


def _require_reason(text: str | None, what: str) -> str:
    if text is None or not text.strip():
        raise Invalid(f"{what} is required")
    return text.strip()


def _require_operator(actor: Actor) -> None:
    if actor.role is not Role.OPERATOR:
        raise Forbidden("operator role required")


def _bump(incident: Incident, now: str, **changes) -> Incident:
    return incident.with_changes(version=incident.version + 1, updated_at=now, **changes)


def triage(incident: Incident, actor: Actor, severity: Severity, reason: str | None, now: str):
    _require_operator(actor)
    if incident.status not in TRIAGE_FROM:
        raise IllegalTransition(f"cannot triage from {incident.status}")
    note = _require_reason(reason, "reason")
    after = _bump(incident, now, status=S.TRIAGED, severity=severity)
    return Change("triage", after, note)


def assign(incident: Incident, actor: Actor, worker_id: str, reason: str | None, now: str):
    _require_operator(actor)
    if incident.status not in ASSIGN_FROM:
        raise IllegalTransition(f"cannot assign from {incident.status}")
    note = _require_reason(reason, "reason")
    after = _bump(incident, now, status=S.ASSIGNED, assigned_to=worker_id)
    return Change("assign", after, note)


def transition(incident: Incident, actor: Actor, to: Status, note: str | None, now: str):
    rule = TRANSITIONS.get((incident.status, to))
    if rule is None:
        raise IllegalTransition(f"cannot move from {incident.status} to {to}")
    if actor.role is not rule.role:
        raise Forbidden(f"{rule.action} requires role {rule.role}")
    if rule.assignee_only and incident.assigned_to != actor.sub:
        raise Forbidden(f"only the assigned field worker can {rule.action}")
    clean_note = note.strip() if note and note.strip() else None
    if rule.note_required:
        clean_note = _require_reason(note, "note")

    changes: dict = {"status": to}
    if rule.action == "resolve":
        changes["resolution_summary"] = clean_note
    if rule.action == "reopen":
        changes["assigned_to"] = None
        changes["resolution_summary"] = None
    return Change(rule.action, _bump(incident, now, **changes), clean_note)


def can_add_evidence(incident: Incident, actor: Actor, kind: EvidenceKind) -> None:
    if actor.role is Role.FIELD_WORKER and incident.assigned_to != actor.sub:
        raise Forbidden("only the assigned field worker can add evidence")
    if actor.role not in (Role.OPERATOR, Role.FIELD_WORKER):
        raise Forbidden("staff role required")
    if incident.status not in EVIDENCE_STATUSES[kind]:
        raise IllegalTransition(f"cannot add {kind} evidence while {incident.status}")


def add_evidence(incident: Incident, actor: Actor, key: str, kind: EvidenceKind, now: str):
    can_add_evidence(incident, actor, kind)
    item = {"key": key, "kind": str(kind), "by": actor.sub, "ts": now}
    after = _bump(incident, now, evidence=(*incident.evidence, item))
    return Change("add_evidence", after, None, {"evidence": item})

import itertools

import pytest

from domain import lifecycle
from domain.errors import Forbidden, IllegalTransition, Invalid
from domain.model import Actor, EvidenceKind, Incident, IncidentType, Role, Severity, Status

OP = Actor("op-01", Role.OPERATOR, "demo-campus")
FW = Actor("fw-01", Role.FIELD_WORKER, "demo-campus")
FW_OTHER = Actor("fw-02", Role.FIELD_WORKER, "demo-campus")
NOW = "2026-10-11T06:00:00.000Z"

LEGAL = {
    ("assigned", "in_progress"),
    ("in_progress", "resolved"),
    ("resolved", "closed"),
    ("resolved", "in_progress"),
    ("closed", "triaged"),
}
ACTOR_FOR = {
    ("assigned", "in_progress"): FW,
    ("in_progress", "resolved"): FW,
    ("resolved", "closed"): OP,
    ("resolved", "in_progress"): OP,
    ("closed", "triaged"): OP,
}


def make(status: Status, assigned_to: str | None = "fw-01") -> Incident:
    return Incident(
        tenant_id="demo-campus",
        id="01J00000000000000000000000",
        reference="DW-00000000",
        type=IncidentType.WATERLOGGING,
        description="water",
        status=status,
        version=3,
        created_at=NOW,
        updated_at=NOW,
        severity=Severity.S2,
        assigned_to=assigned_to,
    )


@pytest.mark.parametrize("src,dst", list(itertools.product(Status, Status)))
def test_transition_matrix(src, dst):
    inc = make(src)
    if (src, dst) in LEGAL:
        change = lifecycle.transition(inc, ACTOR_FOR[(src, dst)], dst, "a reason", NOW)
        assert change.after.status == dst
        assert change.after.version == inc.version + 1
    else:
        for actor in (OP, FW):
            with pytest.raises(IllegalTransition):
                lifecycle.transition(inc, actor, dst, "a reason", NOW)


@pytest.mark.parametrize("src", list(Status))
def test_triage_matrix(src):
    inc = make(src)
    if src in (Status.REPORTED, Status.TRIAGED):
        change = lifecycle.triage(inc, OP, Severity.S1, "near electricals", NOW)
        assert change.after.status == Status.TRIAGED
        assert change.after.severity == Severity.S1
    else:
        with pytest.raises(IllegalTransition):
            lifecycle.triage(inc, OP, Severity.S1, "near electricals", NOW)


@pytest.mark.parametrize("src", list(Status))
def test_assign_matrix(src):
    inc = make(src)
    if src in (Status.TRIAGED, Status.ASSIGNED):
        change = lifecycle.assign(inc, OP, "fw-02", "closer", NOW)
        assert change.after.status == Status.ASSIGNED
        assert change.after.assigned_to == "fw-02"
    else:
        with pytest.raises(IllegalTransition):
            lifecycle.assign(inc, OP, "fw-02", "closer", NOW)


@pytest.mark.parametrize("pair", sorted(LEGAL))
def test_wrong_role_is_forbidden(pair):
    src, dst = pair
    wrong = OP if ACTOR_FOR[pair] is FW else FW
    with pytest.raises(Forbidden):
        lifecycle.transition(make(Status(src)), wrong, Status(dst), "note", NOW)


@pytest.mark.parametrize("dst", [Status.IN_PROGRESS, Status.RESOLVED])
def test_only_assignee_can_start_or_resolve(dst):
    src = Status.ASSIGNED if dst == Status.IN_PROGRESS else Status.IN_PROGRESS
    with pytest.raises(Forbidden):
        lifecycle.transition(make(src), FW_OTHER, dst, "note", NOW)


def test_field_worker_cannot_triage_or_assign():
    with pytest.raises(Forbidden):
        lifecycle.triage(make(Status.REPORTED), FW, Severity.S3, "r", NOW)
    with pytest.raises(Forbidden):
        lifecycle.assign(make(Status.TRIAGED), FW, "fw-01", "r", NOW)


@pytest.mark.parametrize(
    "src,dst,actor",
    [
        (Status.IN_PROGRESS, Status.RESOLVED, FW),
        (Status.RESOLVED, Status.IN_PROGRESS, OP),
        (Status.CLOSED, Status.TRIAGED, OP),
    ],
)
@pytest.mark.parametrize("note", [None, "", "   "])
def test_note_required(src, dst, actor, note):
    with pytest.raises(Invalid):
        lifecycle.transition(make(src), actor, dst, note, NOW)


@pytest.mark.parametrize("reason", [None, " "])
def test_triage_and_assign_need_reason(reason):
    with pytest.raises(Invalid):
        lifecycle.triage(make(Status.REPORTED), OP, Severity.S2, reason, NOW)
    with pytest.raises(Invalid):
        lifecycle.assign(make(Status.TRIAGED), OP, "fw-01", reason, NOW)


def test_resolve_stores_summary_and_reopen_clears_assignee():
    resolved = lifecycle.transition(make(Status.IN_PROGRESS), FW, Status.RESOLVED, "done", NOW)
    assert resolved.after.resolution_summary == "done"
    closed = lifecycle.transition(resolved.after, OP, Status.CLOSED, None, NOW).after
    reopened = lifecycle.transition(closed, OP, Status.TRIAGED, "water back", NOW).after
    assert reopened.assigned_to is None
    assert reopened.resolution_summary is None


@pytest.mark.parametrize("status", list(Status))
@pytest.mark.parametrize("kind", list(EvidenceKind))
def test_evidence_states(status, kind):
    allowed = status in lifecycle.EVIDENCE_STATUSES[kind]
    inc = make(status)
    if allowed:
        change = lifecycle.add_evidence(inc, FW, "k", kind, NOW)
        assert change.after.evidence[-1]["kind"] == kind
    else:
        with pytest.raises(IllegalTransition):
            lifecycle.add_evidence(inc, FW, "k", kind, NOW)

import json
import logging

from api import logs
from tests.conftest import FW1, OP, incident_in, post

SECRET_DESCRIPTION = "Secret-desc-7f3a water near the VC bungalow"
SECRET_NOTE = "Secret-note-91bc cleared by contractor"


def test_logs_are_json_and_never_contain_descriptions_or_notes(client, captured):
    client.post(
        "/api/v1/public/demo-campus/incidents",
        json={"type": "waterlogging", "description": SECRET_DESCRIPTION},
        headers={"Idempotency-Key": "log-test-0001"},
    )
    inc = incident_in(client, "in_progress")
    post(client, inc, "transitions", FW1, to="resolved", note=SECRET_NOTE)
    post(client, inc, "transitions", OP, to="closed", note=SECRET_NOTE)
    client.post(
        f"/api/v1/incidents/{inc['id']}/triage",
        json={"severity": "S1", "reason": SECRET_NOTE, "expected_version": 1, "bogus": 1},
        headers=OP,
    )

    lines = [json.loads(line) for line in captured.getvalue().splitlines()]
    assert lines
    text = captured.getvalue()
    assert "Secret-desc" not in text
    assert "Secret-note" not in text
    req = [line for line in lines if line["msg"] == "request"]
    assert {"request_id", "method", "route", "status", "duration_ms"} <= set(req[-1])
    statuses = {(line["route"], line["status"]) for line in req}
    assert ("/api/v1/public/{tenant}/incidents", 201) in statuses
    conflicts = [line for line in req if line["status"] == 409]
    assert conflicts
    assert all(line["error_code"] == "VERSION_CONFLICT" for line in conflicts)
    assert any(line["status"] == 422 for line in req)


def test_log_drops_unknown_fields(captured):
    logs.log(logging.INFO, "x", description="leak", note="leak", route="/r")
    line = json.loads(captured.getvalue())
    assert "description" not in line and "note" not in line
    assert line["route"] == "/r"

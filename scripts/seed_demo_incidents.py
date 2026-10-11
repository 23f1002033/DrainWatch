"""Create demo incidents for demo-campus through the real HTTP API.

Run after scripts/reset_demo.py. Files 6 public reports, then as op-demo triages 3
and assigns 2 of those to Ravi; the other 3 stay "reported". All of it is demo data.

Fixed Idempotency-Keys make a re-run within 24 h return the same incidents, and
incidents already past "reported" are left alone.

Deployed:  uv run --project services/api python scripts/seed_demo_incidents.py
           (needs AWS credentials for the token and DW_PW_OP_DEMO; nothing secret is printed)
Local:     ... scripts/seed_demo_incidents.py --local --api http://localhost:8000 \
               --worker-name "Field Worker 01"
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

import boto3

TENANT = "demo-campus"
STACK = os.environ.get("DW_STACK", "drainwatch")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
DOMAIN = os.environ.get("DW_EMAIL_DOMAIN", "example.com")

# Illustrative centre point; the incidents sit a few hundred metres around it.
CENTER = (
    float(os.environ.get("DW_DEMO_LAT", "28.6139")),
    float(os.environ.get("DW_DEMO_LNG", "77.2090")),
)

# slug, type, landmark, description, (dlat, dlng), triage, assign_reason
INCIDENTS = [
    (
        "canteen-panel",
        "waterlogging",
        "Canteen, east side door",
        "Standing water about a metre from the electrical panel by the canteen side door.",
        (0.0011, 0.0016),
        ("S1", "Water close to an electrical panel"),
        "S1 near electricals, nearest crew",
    ),
    (
        "hostel-gate",
        "blocked_drain",
        "Hostel C gate",
        "Drain grate at the hostel gate blocked with leaves and plastic, water backing up "
        "onto the path.",
        (0.0024, -0.0012),
        ("S2", "Ponding spreading onto the main walkway"),
        "Same crew is already on the east side",
    ),
    (
        "library-steps",
        "waterlogging",
        "Central library entrance",
        "Ponding across the library entrance steps after the rain, roughly ankle deep.",
        (-0.0008, 0.0005),
        ("S2", "Ponding at a busy entrance, still passable"),
        None,
    ),
    (
        "main-road-manhole",
        "blocked_drain",
        "Main road near the admin block",
        "Manhole on the main road overflowing, water running toward the parking area.",
        (-0.0019, -0.0021),
        None,
        None,
    ),
    (
        "sports-ground",
        "blocked_drain",
        "Behind the sports ground",
        "Drain behind the sports ground is slow, puddles still there hours after the rain.",
        (0.0031, 0.0027),
        None,
        None,
    ),
    (
        "bus-stop",
        "waterlogging",
        "Campus bus stop",
        "Puddle forming under the bus stop shelter, people stepping around it.",
        (-0.0027, 0.0009),
        None,
        None,
    ),
]


class Api:
    def __init__(self, base: str, auth: dict[str, str]):
        self.base = base.rstrip("/") + "/api/v1"
        self.auth = auth

    def call(self, method: str, path: str, body=None, headers=None, auth=True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        for k, v in {**(self.auth if auth else {}), **(headers or {})}.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"null")


def deployed_api() -> tuple[str, dict[str, str]]:
    cfn = boto3.client("cloudformation", region_name=REGION)
    outputs = cfn.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
    out = {o["OutputKey"]: o["OutputValue"] for o in outputs}
    password = os.environ.get("DW_PW_OP_DEMO")
    if not password:
        sys.exit("DW_PW_OP_DEMO is not set")
    idp = boto3.client("cognito-idp", region_name=REGION)
    token = idp.admin_initiate_auth(
        UserPoolId=out["UserPoolId"],
        ClientId=out["AppClientId"],
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": f"op-demo@{DOMAIN}", "PASSWORD": password},
    )["AuthenticationResult"]["IdToken"]
    return out["ApiUrl"], {"Authorization": f"Bearer {token}"}


def all_incidents(api: Api) -> list[dict]:
    items, cursor = [], None
    while True:
        query = "?limit=100" + (f"&cursor={cursor}" if cursor else "")
        status, body = api.call("GET", "/incidents" + query)
        if status != 200:
            sys.exit(f"queue read failed: {status} {body}")
        items.extend(body["items"])
        cursor = body["next_cursor"]
        if not cursor:
            return items


def expect(what: str, status: int, body, ok=(200, 201)) -> dict:
    if status not in ok:
        sys.exit(f"{what} failed: {status} {json.dumps(body)}")
    return body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed demo incidents for demo-campus")
    parser.add_argument("--local", action="store_true", help="use the local stub identity")
    parser.add_argument("--api", help="API base URL (default: stack output ApiUrl)")
    parser.add_argument("--worker-name", default="Ravi")
    args = parser.parse_args(argv)

    if args.local:
        base = args.api or "http://localhost:8000"
        auth = {"X-Stub-Sub": "op-01", "X-Stub-Groups": "operator", "X-Stub-Tenant": TENANT}
    else:
        base, auth = deployed_api()
        base = args.api or base
    api = Api(base, auth)

    workers = expect("workers", *api.call("GET", "/workers"))["items"]
    worker = next((w for w in workers if w["name"] == args.worker_name), None)
    if worker is None:
        sys.exit(f"no field worker named {args.worker_name!r} in {TENANT}")

    ours = {description for _, _, _, description, *_ in INCIDENTS}
    others = [i for i in all_incidents(api) if i["description"] not in ours]
    if others:
        sys.exit(
            f"{len(others)} other incidents exist in {TENANT}; run scripts/reset_demo.py first"
        )

    references = {}
    for slug, type_, landmark, description, (dlat, dlng), *_ in INCIDENTS:
        body = {
            "type": type_,
            "description": description,
            "landmark": landmark,
            "lat": round(CENTER[0] + dlat, 6),
            "lng": round(CENTER[1] + dlng, 6),
        }
        status, resp = api.call(
            "POST",
            f"/public/{TENANT}/incidents",
            body,
            headers={"Idempotency-Key": f"demo-seed-{slug}"},
            auth=False,
        )
        references[slug] = expect(f"report {slug}", status, resp)["reference"]
        time.sleep(0.6)  # public route is throttled to 2 rps

    by_ref = {i["reference"]: i for i in all_incidents(api)}

    for slug, *_, triage, assign_reason in INCIDENTS:
        inc = by_ref[references[slug]]
        if triage and inc["status"] == "reported":
            severity, reason = triage
            body = {"severity": severity, "reason": reason, "expected_version": inc["version"]}
            inc = expect(
                f"triage {slug}", *api.call("POST", f"/incidents/{inc['id']}/triage", body)
            )
        if assign_reason and inc["status"] == "triaged":
            body = {
                "worker_id": worker["id"],
                "reason": assign_reason,
                "expected_version": inc["version"],
            }
            inc = expect(
                f"assign {slug}", *api.call("POST", f"/incidents/{inc['id']}/assignments", body)
            )
        by_ref[inc["reference"]] = inc

    names = {w["id"]: w["name"] for w in workers}
    print(f"{'reference':<12} {'status':<9} {'sev':<4} {'assigned':<16} landmark")
    for slug, _, landmark, *_ in INCIDENTS:
        inc = by_ref[references[slug]]
        assignee = names.get(inc["assigned_to"], "-") if inc["assigned_to"] else "-"
        print(
            f"{inc['reference']:<12} {inc['status']:<9} {inc['severity'] or '-':<4} "
            f"{assignee:<16} {landmark}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

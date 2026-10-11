# DrainWatch Ops

Incident tracking for waterlogging and blocked drains on a campus, from the
first report to a verified closure.

Built for the WeMakeDevs x AWS Environmental Hacks (Heat and Water track).

## Problem

After heavy rain, blocked drains flood paths, hostel entrances and areas near
electrical rooms. Reports reach the facility team through calls and chat
messages. Nobody can see which reports are open, who is working on which one,
or whether a fix was checked. The same drain floods again and there is no
record of what was done last time.

## Who it is for

- **People on campus** (students, staff, visitors). They scan a QR poster and
  report a problem without an account.
- **Facility operators.** They triage reports by severity, assign a field
  worker, check the result, and close or reopen.
- **Field workers.** They start the job, upload before and after photos, and
  mark it resolved with a summary.

One deployment can serve several campuses (tenants). The pilot tenant is
`demo-campus`.

## How it works

1. A reporter opens the campus page, picks "waterlogging" or "blocked drain",
   adds a description and an optional landmark or map pin, and submits. They
   get a reference code back. The report itself is not publicly readable.
2. An operator sees it in the queue (newest first, filtered by status,
   severity, type or age). They set a severity and give a reason:
   - S1: blocks access or is near electricals.
   - S2: ponding or spreading.
   - S3: minor.
3. The operator assigns a field worker, again with a reason.
4. Only the assigned worker can start and resolve the job. Resolving needs a
   summary. Photos are uploaded straight to S3.
5. The operator checks the work. They close the incident, or send it back to
   in progress with a reason. A closed incident can be reopened with a reason.

```
reported -> triaged -> assigned -> in_progress -> resolved -> closed
                                   in_progress <- resolved     (verification failed)
            triaged  <------------------------------------ closed (reopen)
```

The server enforces these rules. Every change writes an audit event (who, what,
before, after, when) in the same database transaction as the change itself.

Status: the backend is deployed and smoke-tested. The web frontend
(`apps/web`, Next.js static export) is being built separately.

## Architecture

All in `ap-south-1` (Mumbai), defined in `infrastructure/template.yaml` (AWS SAM).

| Service | What it does | Why |
|---|---|---|
| AWS Amplify Hosting | Serves the static Next.js export over HTTPS | No server to run; manual zip deploys, no CI needed |
| Amazon API Gateway (HTTP API) | Public HTTPS endpoint, JWT check, CORS, throttling | Checks the Cognito token before Lambda runs; cheaper and simpler than a REST API |
| Amazon Cognito (Lite tier) | Staff sign-in, `operator` / `field_worker` groups, tenant id on each user | Managed user pool; the Lite tier covers what is needed at the lowest price |
| AWS Lambda (Python 3.12, arm64) | One FastAPI app behind Mangum | One function keeps deploys and cold starts simple; arm64 is cheaper per GB-second |
| Amazon DynamoDB (on-demand) | One table: incidents, audit events, idempotency records, staff members | Pay per request, conditional transactions for safe concurrent updates, TTL for idempotency keys |
| Amazon S3 | Private evidence bucket for photos | Browser uploads directly with a presigned POST, so photos never pass through Lambda |
| Amazon CloudWatch | JSON logs (14-day retention), two alarms (Lambda errors, API 5xx) | Basic visibility at low cost |
| Amazon SNS | Emails alarm notifications | Simplest way to get alerted |

Code layout (`services/api/src`):

- `domain/`: the state machine as pure functions, with no AWS code.
- `repo/`: one storage interface, with an in-memory version and a DynamoDB version.
  The same tests run against both.
- `auth/`: reads identity from the token claims.
- `api/`: HTTP routes and the code that connects them to the domain and storage.

### Data model (single table)

| PK | SK | Item |
|---|---|---|
| `TENANT#t` | `INC#<ulid>` | incident, with a `version` number |
| `TENANT#t#INC#<id>` | `EVT#<ulid>` | audit event |
| `TENANT#t` | `IDEM#<key>` | idempotency record for public reports, expires after 24 h |
| `TENANT#t` | `MEMBER#<sub>` | staff member (name, role) |

The queue is a Query on the tenant partition, newest first, with no table
Scans. The limits of this approach are listed under "Known limitations".

## Security choices

- **Identity comes only from the verified token.** Role (`cognito:groups`) and
  tenant (`custom:tenant_id`) are read from JWT claims that API Gateway has
  already verified. The local stub identity only works when `APP_ENV=local`,
  and the default is `prod`.
- **Tenant isolation.** Every key and query includes the tenant id taken from
  the token. Another tenant's incident returns 404, the same as one that does
  not exist, so ids cannot be probed. Pagination cursors only carry the sort
  key, so they cannot point into another tenant.
- **Users cannot change their tenant.** `custom:tenant_id` is immutable, and the
  app client can read it but not write it. Accounts can only be created by an
  admin.
- **Role checks on the server.** Only operators triage, assign, verify, close
  and reopen. Only the assigned field worker can start or resolve. Breaking a
  rule gives 403 (role) or 409 (illegal transition or stale version).
- **Safe concurrent updates.** Each change is one DynamoDB transaction that
  only succeeds if the stored version and status are still what the client
  read. Two updates racing on the same version give one success and one 409.
- **Audit events cannot be changed.** An event is only written if it does not
  already exist. The Lambda role has no `UpdateItem` or `DeleteItem`
  permission at all.
- **Uploads.**
  - The server picks the S3 key, under `<tenant>/incidents/<id>/`.
  - The presigned POST policy fixes the key and the content type
    (jpeg/png/webp), and limits the size to 5 MB.
  - When a photo is registered as evidence, the server checks the stored
    object with HeadObject and rejects it if it is missing, too large or the
    wrong type.
  - The bucket is private, public access is blocked, and it is encrypted with
    SSE-S3. Requests without TLS are denied.
- **Least-privilege IAM.** The function can only:
  - `GetItem`, `PutItem` and `Query` on this table;
  - `PutObject` and `GetObject` on this bucket;
  - write to its own log group.
- **Abuse limits.** The API allows 20 requests/s (burst 40). The anonymous
  report route allows 2 requests/s (burst 5) and requires an `Idempotency-Key`
  header, so retries do not create duplicates.
- **Logs.** One JSON line per request with an allow-list of fields. Report
  descriptions, notes and request bodies are never logged.
- **Secrets.** There are none in the repo. Demo passwords live in a local
  env file outside git and are never printed.

## Cost

Estimated at about $0.10 for a one-week pilot, using ap-south-1 list prices.
The project target is under $2. A $5 AWS Budget with email alerts was created
before the first deploy. Details and assumptions are in
[docs/cost.md](docs/cost.md).

## Run locally

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/). This does not touch AWS.

```
cd services/api
uv sync
APP_ENV=local REPO=memory KNOWN_TENANTS=demo-campus,other-campus \
  uv run uvicorn api.main:app --app-dir src --port 8000
```

Locally you act as a user by sending headers:
`X-Stub-Sub: fw-01`, `X-Stub-Groups: field_worker`, `X-Stub-Tenant: demo-campus`.

Tests and lint (DynamoDB and S3 are mocked with moto):

```
cd services/api
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

## Deploy

Needs the AWS CLI and SAM CLI, with credentials for the target account.

Copy `infrastructure/samconfig.example.toml` to `infrastructure/samconfig.toml`
(git-ignored) and add `parameter_overrides = "AlarmEmail=you@example.com"` under
`[default.deploy.parameters]` so alarm emails reach you.

```
cd infrastructure
sam build && sam deploy        # stack "drainwatch", region ap-south-1

# demo users; passwords come from env vars, see the script header
uv run --project services/api python scripts/seed_demo.py

# end-to-end check against the live API
scripts/smoke.sh

# frontend: after building the static export in apps/web/out
scripts/deploy_web.sh
```

`scripts/reset_demo.py <tenant>` clears one tenant's incidents, events and
idempotency records. It keeps staff accounts and asks for confirmation first.

## Tear down

See [docs/teardown.md](docs/teardown.md). In short:

1. Empty the evidence bucket.
2. Run `sam delete`.
3. Optionally remove the SAM artifact stack and the budget.
4. Also delete the Amplify app: `aws amplify delete-app --app-id <id>`.

## Known limitations

- **Queue filtering.** Filters by status, severity and type are applied after
  DynamoDB reads the rows. A page can come back short, and cost grows with the
  number of incidents in a tenant. This is fine for one campus. A larger
  deployment would need an index on status.
- **Report spam.** Anonymous reports are protected only by throttling. There
  is no CAPTCHA and no duplicate detection.
- **Photo metadata.** Photos are stored as uploaded. Location metadata (EXIF)
  is not removed and images are not scanned.
- **Backups.** Point-in-time recovery is off to keep cost down, so deleted
  data cannot be restored.
- **Staff setup.** Staff are added with `scripts/seed_demo.py`. There is no
  admin screen for managing users.
- **No notifications.** Workers are not notified when a job is assigned to
  them.
- **Single region.** Everything runs in ap-south-1.
- **Not yet tested by real users.** The pilot has only been run with seeded
  demo accounts.

## AI tools used

This project was built with Claude Code (Anthropic) as a coding assistant. It
wrote most of the backend code, tests, infrastructure template, scripts and
docs, working from the author's specification and stopping for review before
anything was deployed or billed. The product itself has no AI or LLM features.

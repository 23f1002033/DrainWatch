# DrainWatch API (M1, local)

FastAPI app, one Lambda via Mangum (`api.main.handler`). Layers:
`domain/` pure state machine, `repo/` interface with InMemory and DynamoDB
impls, `auth/` identity from JWT claims, `api/` HTTP and orchestration.

## Run locally

    uv sync
    APP_ENV=local REPO=memory KNOWN_TENANTS=demo-campus,other-campus \
      uv run uvicorn api.main:app --app-dir src --port 8000

Local identity comes from `X-Stub-Sub`, `X-Stub-Groups`, `X-Stub-Tenant`
headers, honoured only when `APP_ENV=local`. Anywhere else role and tenant
come only from the API Gateway JWT claims (`cognito:groups`,
`custom:tenant_id`). `APP_ENV` defaults to `prod`.

## Test

    uv run pytest -q
    uv run ruff check . && uv run ruff format --check .

Every API test runs against both repos (InMemory and DynamoDB on moto).

## Table

| PK | SK | Item |
|----|----|------|
| `TENANT#t` | `INC#<ulid>` | incident, `version` |
| `TENANT#t#INC#<id>` | `EVT#<ulid>` | audit event, put-if-absent only |
| `TENANT#t` | `IDEM#<key>` | idempotency record, `ttl` = now + 24h |

Every change is one TransactWriteItems: Put incident conditioned on
`version = expected AND status = expected`, plus Put event conditioned on
`attribute_not_exists(PK)`. Expired idempotency rows are treated as absent
before DynamoDB TTL removes them.

## Queue limit (pilot scale)

`GET /incidents` is a Query on `TENANT#t`, `SK` descending (ULIDs sort by
creation time, so newest first). `older_than_hours` is a key condition (SK
upper bound from a ULID at the cutoff). `status`, `severity`, `type` are
DynamoDB FilterExpressions: they cut what is returned, not what is read. One
request reads at most 5 DynamoDB pages of `limit` items, then returns what it
has plus a cursor, so a page can be short and a cursor can lead to an empty
page. Clients page until `next_cursor` is null.

That is fine for one campus (hundreds to low thousands of incidents). Past
that, add a GSI on `TENANT#t#STATUS#s` so the common "open by status" query
reads only matching items. There are no Scans.

The cursor encodes only the SK. The partition always comes from the caller's
tenant claim, so a cursor cannot cross tenants.

## Not in M1

- Workers list is a static seed in local mode and empty elsewhere. Cognito
  group lookup comes with the deploy milestone.
- Evidence keys are checked for shape and incident prefix, not for the object
  actually existing in S3.

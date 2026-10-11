"""Delete every incident, audit event and idempotency record for one tenant.

Keeps MEMBER items (staff accounts). Uses your own AWS credentials, not the Lambda
role (the Lambda role cannot delete). Evidence photos in S3 are left in place.

Run: uv run --project services/api python scripts/reset_demo.py demo-campus [--dry-run]
"""

import argparse
import os
import sys

import boto3

PREFIXES = ("INC#", "IDEM#")


def _query_keys(db, table: str, pk: str, prefix: str) -> list[dict]:
    keys: list[dict] = []
    params = {
        "TableName": table,
        "KeyConditionExpression": "PK = :pk AND begins_with(SK, :p)",
        "ExpressionAttributeValues": {":pk": {"S": pk}, ":p": {"S": prefix}},
        "ProjectionExpression": "PK, SK",
        "ConsistentRead": True,
    }
    while True:
        resp = db.query(**params)
        keys.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return keys
        params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def collect(db, table: str, tenant: str) -> dict[str, list[dict]]:
    pk = f"TENANT#{tenant}"
    incidents = _query_keys(db, table, pk, "INC#")
    events: list[dict] = []
    for inc in incidents:
        incident_id = inc["SK"]["S"].removeprefix("INC#")
        events.extend(_query_keys(db, table, f"{pk}#INC#{incident_id}", "EVT#"))
    return {
        "incidents": incidents,
        "events": events,
        "idempotency": _query_keys(db, table, pk, "IDEM#"),
    }


def delete(db, table: str, keys: list[dict]) -> int:
    for start in range(0, len(keys), 25):
        requests = [{"DeleteRequest": {"Key": k}} for k in keys[start : start + 25]]
        while requests:
            resp = db.batch_write_item(RequestItems={table: requests})
            requests = resp.get("UnprocessedItems", {}).get(table, [])
    return len(keys)


def table_from_stack(stack: str, region: str) -> str:
    cfn = boto3.client("cloudformation", region_name=region)
    outputs = cfn.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in outputs if o["OutputKey"] == "TableName")


def main(argv: list[str] | None = None, ask=input) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tenant")
    parser.add_argument("--stack", default=os.environ.get("DW_STACK", "drainwatch"))
    parser.add_argument("--table", help="table name (default: read from the stack outputs)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    region = os.environ.get("AWS_REGION", "ap-south-1")
    db = boto3.client("dynamodb", region_name=region)
    table = args.table or table_from_stack(args.stack, region)
    found = collect(db, table, args.tenant)
    counts = ", ".join(f"{len(v)} {k}" for k, v in found.items())
    print(f"table {table}, tenant {args.tenant}: {counts}. MEMBER items are kept.")
    total = sum(len(v) for v in found.values())
    if args.dry_run or total == 0:
        return 0
    if ask(f"Type the tenant id ({args.tenant}) to delete these {total} items: ") != args.tenant:
        print("aborted, nothing deleted")
        return 1
    deleted = sum(delete(db, table, keys) for keys in found.values())
    print(f"deleted {deleted} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Create demo Cognito users and their MEMBER items.

Passwords come only from env vars and are never printed:
  DW_PW_OP_DEMO, DW_PW_FW_RAVI, DW_PW_FW_MEENA, DW_PW_OP_OTHER

Run: uv run --project services/api python scripts/seed_demo.py
"""

import os
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/api/src"))

from domain.model import Member, Role
from repo.dynamo import DynamoRepo

STACK = os.environ.get("DW_STACK", "drainwatch")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
EMAIL_DOMAIN = os.environ.get("DW_EMAIL_DOMAIN", "example.com")

USERS = [
    ("op-demo", "Ops Desk Demo", "demo-campus", Role.OPERATOR, "DW_PW_OP_DEMO"),
    ("fw-ravi", "Ravi", "demo-campus", Role.FIELD_WORKER, "DW_PW_FW_RAVI"),
    ("fw-meena", "Meena", "demo-campus", Role.FIELD_WORKER, "DW_PW_FW_MEENA"),
    ("op-other", "Ops Desk Other", "other-campus", Role.OPERATOR, "DW_PW_OP_OTHER"),
]


def stack_outputs() -> dict[str, str]:
    cfn = boto3.client("cloudformation", region_name=REGION)
    stack = cfn.describe_stacks(StackName=STACK)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}


def attrs(user: dict) -> dict[str, str]:
    return {a["Name"]: a["Value"] for a in user.get("UserAttributes", user.get("Attributes", []))}


def main() -> int:
    missing = [env for *_, env in USERS if not os.environ.get(env)]
    if missing:
        print(f"missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    out = stack_outputs()
    pool = out["UserPoolId"]
    idp = boto3.client("cognito-idp", region_name=REGION)
    repo = DynamoRepo(boto3.client("dynamodb", region_name=REGION), out["TableName"])

    for handle, name, tenant, role, env in USERS:
        email = f"{handle}@{EMAIL_DOMAIN}"
        try:
            idp.admin_create_user(
                UserPoolId=pool,
                Username=email,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": name},
                    {"Name": "custom:tenant_id", "Value": tenant},
                ],
            )
            state = "created"
        except idp.exceptions.UsernameExistsException:
            state = "exists"
        user = idp.admin_get_user(UserPoolId=pool, Username=email)
        found = attrs(user)
        if found.get("custom:tenant_id") != tenant:
            print(f"{email}: tenant is {found.get('custom:tenant_id')}, expected {tenant}")
            return 1
        idp.admin_set_user_password(
            UserPoolId=pool, Username=email, Password=os.environ[env], Permanent=True
        )
        idp.admin_add_user_to_group(UserPoolId=pool, Username=email, GroupName=str(role))
        repo.put_member(Member(tenant, found["sub"], name, role))
        print(f"{email:<28} {state:<8} {tenant:<13} {role!s:<13} sub={found['sub']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

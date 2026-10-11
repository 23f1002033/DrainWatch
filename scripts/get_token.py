"""Print an ID token for a seeded user. The password is read from the named env var."""

import os
import sys

import boto3

email, password_env, pool, client_id = sys.argv[1:5]
idp = boto3.client("cognito-idp", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
resp = idp.admin_initiate_auth(
    UserPoolId=pool,
    ClientId=client_id,
    AuthFlow="ADMIN_USER_PASSWORD_AUTH",
    AuthParameters={"USERNAME": email, "PASSWORD": os.environ[password_env]},
)
print(resp["AuthenticationResult"]["IdToken"])

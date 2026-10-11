import boto3
from botocore.config import Config
from mangum import Mangum

from api import logs
from api.app import create_app
from api.service import IncidentService
from api.settings import Settings
from domain.model import Member, Role
from repo.dynamo import DynamoRepo
from repo.memory import InMemoryRepo
from repo.storage import S3Store, StubStore

LOCAL_MEMBERS = [
    Member("demo-campus", "op-01", "Operator 01", Role.OPERATOR),
    Member("demo-campus", "fw-01", "Field Worker 01", Role.FIELD_WORKER),
    Member("demo-campus", "fw-02", "Field Worker 02", Role.FIELD_WORKER),
    Member("other-campus", "fw-91", "Field Worker 91", Role.FIELD_WORKER),
]


def build(settings: Settings):
    logs.configure()
    if settings.repo == "memory":
        repo = InMemoryRepo()
        for member in LOCAL_MEMBERS:
            repo.put_member(member)
    else:
        client = boto3.client("dynamodb", endpoint_url=settings.dynamo_endpoint)
        repo = DynamoRepo(client, settings.table_name)
    if settings.app_env == "local":
        store = StubStore(settings.stub_upload_base)
    else:
        # Regional virtual-host URL: the global endpoint can 307 for new buckets.
        s3 = boto3.client(
            "s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
        )
        store = S3Store(s3, settings.bucket)
    return create_app(IncidentService(repo, store, settings.tenants), settings)


app = build(Settings.from_env())
handler = Mangum(app, lifespan="off")

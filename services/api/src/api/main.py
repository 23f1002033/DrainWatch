import boto3
from mangum import Mangum

from api.app import create_app
from api.service import IncidentService
from api.settings import Settings
from auth.directory import LOCAL_WORKERS, StaticDirectory
from repo.dynamo import DynamoRepo
from repo.memory import InMemoryRepo
from repo.storage import S3Signer, StubSigner


def build(settings: Settings):
    if settings.repo == "memory":
        repo = InMemoryRepo()
    else:
        client = boto3.client("dynamodb", endpoint_url=settings.dynamo_endpoint)
        repo = DynamoRepo(client, settings.table_name)
    if settings.app_env == "local":
        signer = StubSigner(settings.stub_upload_base)
    else:
        signer = S3Signer(boto3.client("s3"), settings.bucket)
    workers = StaticDirectory(LOCAL_WORKERS if settings.app_env == "local" else {})
    service = IncidentService(repo, workers, signer, settings.tenants)
    return create_app(service, settings)


app = build(Settings.from_env())
handler = Mangum(app, lifespan="off")

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    app_env: str = "local"
    repo: str = "memory"
    table_name: str = "drainwatch"
    bucket: str = ""
    dynamo_endpoint: str | None = None
    stub_upload_base: str = "http://localhost:8000/_stub-upload"
    tenants: frozenset[str] = field(default_factory=lambda: frozenset({"demo-campus"}))

    @classmethod
    def from_env(cls) -> "Settings":
        tenants = os.environ.get("KNOWN_TENANTS", "demo-campus")
        return cls(
            app_env=os.environ.get("APP_ENV", "prod"),
            repo=os.environ.get("REPO", "dynamo"),
            table_name=os.environ.get("TABLE_NAME", "drainwatch"),
            bucket=os.environ.get("UPLOAD_BUCKET", ""),
            dynamo_endpoint=os.environ.get("DYNAMO_ENDPOINT") or None,
            stub_upload_base=os.environ.get("STUB_UPLOAD_BASE", cls.stub_upload_base),
            tenants=frozenset(t.strip() for t in tenants.split(",") if t.strip()),
        )

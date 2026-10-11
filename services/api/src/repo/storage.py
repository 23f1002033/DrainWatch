import threading
from dataclasses import dataclass
from typing import Protocol

from botocore.exceptions import ClientError

ALLOWED_CONTENT_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
CONTENT_TYPE_FOR_EXT = {ext: ct for ct, ext in ALLOWED_CONTENT_TYPES.items()}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
UPLOAD_URL_TTL_SECONDS = 300


@dataclass(frozen=True)
class PresignedPost:
    url: str
    fields: dict[str, str]
    expires_in: int


@dataclass(frozen=True)
class StoredObject:
    size: int
    content_type: str


class EvidenceStore(Protocol):
    def presign_post(self, key: str, content_type: str) -> PresignedPost: ...

    def head(self, key: str) -> StoredObject | None:
        """None when the object does not exist (or is not visible to this role)."""


def post_conditions(key: str, content_type: str) -> list:
    return [
        {"key": key},
        {"Content-Type": content_type},
        ["content-length-range", 1, MAX_UPLOAD_BYTES],
    ]


class S3Store:
    def __init__(self, client, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    def presign_post(self, key: str, content_type: str) -> PresignedPost:
        signed = self._s3.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=post_conditions(key, content_type),
            ExpiresIn=UPLOAD_URL_TTL_SECONDS,
        )
        return PresignedPost(signed["url"], signed["fields"], UPLOAD_URL_TTL_SECONDS)

    def head(self, key: str) -> StoredObject | None:
        try:
            resp = self._s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            # Without s3:ListBucket a missing key answers 403, not 404.
            if exc.response.get("Error", {}).get("Code") in ("403", "404", "NoSuchKey"):
                return None
            raise
        return StoredObject(int(resp["ContentLength"]), resp.get("ContentType", ""))


class StubStore:
    """Local and test store. The local app exposes a POST endpoint that applies the
    same policy S3 would and records the object here."""

    def __init__(self, base_url: str = "http://localhost:8000/_stub-upload") -> None:
        self._base = base_url
        self._objects: dict[str, StoredObject] = {}
        self._lock = threading.Lock()

    def presign_post(self, key: str, content_type: str) -> PresignedPost:
        return PresignedPost(
            self._base, {"key": key, "Content-Type": content_type}, UPLOAD_URL_TTL_SECONDS
        )

    def head(self, key: str) -> StoredObject | None:
        return self._objects.get(key)

    def put(self, key: str, size: int, content_type: str) -> None:
        with self._lock:
            self._objects[key] = StoredObject(size, content_type)

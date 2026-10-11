from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

ALLOWED_CONTENT_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
UPLOAD_URL_TTL_SECONDS = 300


@dataclass(frozen=True)
class PresignedPut:
    url: str
    headers: dict[str, str]
    expires_in: int


class Signer(Protocol):
    def presign_put(self, key: str, content_type: str, content_length: int) -> PresignedPut: ...


class StubSigner:
    def __init__(self, base_url: str = "http://localhost:8000/_stub-upload") -> None:
        self._base = base_url

    def presign_put(self, key: str, content_type: str, content_length: int) -> PresignedPut:
        return PresignedPut(
            url=f"{self._base}/{quote(key)}?stub=1",
            headers={"Content-Type": content_type, "Content-Length": str(content_length)},
            expires_in=UPLOAD_URL_TTL_SECONDS,
        )


class S3Signer:
    def __init__(self, client, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    def presign_put(self, key: str, content_type: str, content_length: int) -> PresignedPut:
        url = self._s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": content_length,
            },
            ExpiresIn=UPLOAD_URL_TTL_SECONDS,
        )
        return PresignedPut(
            url=url,
            headers={"Content-Type": content_type, "Content-Length": str(content_length)},
            expires_in=UPLOAD_URL_TTL_SECONDS,
        )

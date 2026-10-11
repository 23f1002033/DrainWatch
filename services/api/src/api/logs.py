import json
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("drainwatch")

# Only these keys ever reach the log. Request bodies, descriptions and notes are never passed.
ALLOWED_FIELDS = frozenset(
    {
        "request_id",
        "lambda_request_id",
        "method",
        "route",
        "status",
        "duration_ms",
        "tenant_id",
        "role",
        "incident_id",
        "error_code",
        "error_type",
        "frames",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "msg": record.msg,
        }
        out.update(getattr(record, "fields", {}))
        return json.dumps(out, separators=(",", ":"))


def configure(stream=None) -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    logger.propagate = False


def log(level: int, msg: str, **fields: Any) -> None:
    safe = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS and v is not None}
    logger.log(level, msg, extra={"fields": safe})


def frames(exc: BaseException) -> list[str]:
    tb = traceback.extract_tb(exc.__traceback__)
    return [f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}" for f in tb[-8:]]

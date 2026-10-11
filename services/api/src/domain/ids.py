import os
import re
import threading
from datetime import datetime

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

_lock = threading.Lock()
_last_ms = -1
_last_rand = 0


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def new_ulid(now: datetime) -> str:
    """Monotonic ULID: ids created in the same millisecond still sort in creation order."""
    global _last_ms, _last_rand
    ms = int(now.timestamp() * 1000)
    with _lock:
        same_ms = ms == _last_ms
        rand = _last_rand + 1 if same_ms else int.from_bytes(os.urandom(10), "big")
        _last_ms, _last_rand = ms, rand
    return _encode(ms, 10) + _encode(rand, 16)


def min_ulid_at(now: datetime) -> str:
    return _encode(int(now.timestamp() * 1000), 10) + "0" * 16


def is_ulid(value: str) -> bool:
    return bool(ULID_RE.match(value))


def reference_code(incident_id: str) -> str:
    return "DW-" + incident_id[-8:]

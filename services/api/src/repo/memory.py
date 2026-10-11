import copy
import threading
from typing import Any

from domain.model import Event, Incident, Member, Status
from repo.base import (
    EVT_PREFIX,
    IDEM_PREFIX,
    INC_PREFIX,
    MEMBER_PREFIX,
    ConditionFailed,
    IdempotencyExists,
    IdemRecord,
    Page,
    QueueFilter,
    events_pk,
    tenant_pk,
)
from repo.codec import (
    event_to_item,
    incident_to_item,
    item_to_event,
    item_to_incident,
    item_to_member,
    member_to_item,
)


class InMemoryRepo:
    """Same key layout and conditions as the DynamoDB table, held in a dict."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _put_new(self, item: dict[str, Any]) -> None:
        key = (item["PK"], item["SK"])
        if key in self._items:
            raise ConditionFailed(key)
        self._items[key] = copy.deepcopy(item)

    def create_incident(self, incident: Incident, event: Event, idem: IdemRecord, now_epoch: int):
        with self._lock:
            idem_key = (tenant_pk(idem.tenant_id), IDEM_PREFIX + idem.key)
            existing = self._items.get(idem_key)
            if existing and existing["ttl"] > now_epoch:
                raise IdempotencyExists(_idem_from_item(existing))
            inc_item = incident_to_item(incident)
            evt_item = event_to_item(event)
            for item in (inc_item, evt_item):
                if (item["PK"], item["SK"]) in self._items:
                    raise ConditionFailed(item["SK"])
            self._items[idem_key] = _idem_to_item(idem)
            self._put_new(inc_item)
            self._put_new(evt_item)

    def get_idempotency(self, tenant_id: str, key: str, now_epoch: int) -> IdemRecord | None:
        item = self._items.get((tenant_pk(tenant_id), IDEM_PREFIX + key))
        if not item or item["ttl"] <= now_epoch:
            return None
        return _idem_from_item(item)

    def get_incident(self, tenant_id: str, incident_id: str) -> Incident | None:
        item = self._items.get((tenant_pk(tenant_id), INC_PREFIX + incident_id))
        return item_to_incident(copy.deepcopy(item)) if item else None

    def commit_change(
        self, after: Incident, expected_version: int, expected_status: Status, event: Event
    ) -> None:
        with self._lock:
            key = (tenant_pk(after.tenant_id), INC_PREFIX + after.id)
            current = self._items.get(key)
            if (
                current is None
                or current["version"] != expected_version
                or current["status"] != str(expected_status)
            ):
                raise ConditionFailed(key)
            evt_item = event_to_item(event)
            if (evt_item["PK"], evt_item["SK"]) in self._items:
                raise ConditionFailed(evt_item["SK"])
            self._items[key] = incident_to_item(after)
            self._put_new(evt_item)

    def list_incidents(
        self, tenant_id: str, flt: QueueFilter, cursor: str | None, limit: int
    ) -> Page:
        pk = tenant_pk(tenant_id)
        sks = sorted(
            (sk for (p, sk) in self._items if p == pk and sk.startswith(INC_PREFIX)),
            reverse=True,
        )
        if cursor:
            sks = [sk for sk in sks if sk < cursor]
        if flt.created_before_id:
            sks = [sk for sk in sks if sk < INC_PREFIX + flt.created_before_id]
        matched: list[Incident] = []
        last_sk = None
        for sk in sks:
            item = self._items[(pk, sk)]
            if _matches(item, flt):
                matched.append(item_to_incident(copy.deepcopy(item)))
                last_sk = sk
                if len(matched) == limit:
                    break
        more = last_sk is not None and len(matched) == limit and sks[-1] != last_sk
        return Page(matched, last_sk if more else None)

    def list_events(self, tenant_id: str, incident_id: str) -> list[Event]:
        pk = events_pk(tenant_id, incident_id)
        sks = sorted(sk for (p, sk) in self._items if p == pk and sk.startswith(EVT_PREFIX))
        return [item_to_event(copy.deepcopy(self._items[(pk, sk)])) for sk in sks]

    def put_member(self, member: Member) -> None:
        item = member_to_item(member)
        with self._lock:
            self._items[(item["PK"], item["SK"])] = item

    def list_members(self, tenant_id: str) -> list[Member]:
        pk = tenant_pk(tenant_id)
        sks = sorted(sk for (p, sk) in self._items if p == pk and sk.startswith(MEMBER_PREFIX))
        return [item_to_member(self._items[(pk, sk)]) for sk in sks]


def _matches(item: dict[str, Any], flt: QueueFilter) -> bool:
    if flt.status and item["status"] != str(flt.status):
        return False
    if flt.severity and item.get("severity") != str(flt.severity):
        return False
    return not (flt.type and item["type"] != str(flt.type))


def _idem_to_item(idem: IdemRecord) -> dict[str, Any]:
    return {
        "PK": tenant_pk(idem.tenant_id),
        "SK": IDEM_PREFIX + idem.key,
        "body_hash": idem.body_hash,
        "incident_id": idem.incident_id,
        "reference": idem.reference,
        "ttl": idem.expires_at,
    }


def _idem_from_item(item: dict[str, Any]) -> IdemRecord:
    return IdemRecord(
        tenant_id=item["PK"].removeprefix("TENANT#"),
        key=item["SK"].removeprefix(IDEM_PREFIX),
        body_hash=item["body_hash"],
        incident_id=item["incident_id"],
        reference=item["reference"],
        expires_at=int(item["ttl"]),
    )

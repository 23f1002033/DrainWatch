from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from domain.model import Event, Incident, Status
from repo.base import (
    EVT_PREFIX,
    IDEM_PREFIX,
    INC_PREFIX,
    MAX_QUERY_PAGES,
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
    from_dynamo_safe,
    incident_to_item,
    item_to_event,
    item_to_incident,
    to_dynamo_safe,
)

_ser = TypeSerializer()
_de = TypeDeserializer()


def _dump(item: dict[str, Any]) -> dict[str, Any]:
    return {k: _ser.serialize(v) for k, v in to_dynamo_safe(item).items()}


def _load(item: dict[str, Any]) -> dict[str, Any]:
    return from_dynamo_safe({k: _de.deserialize(v) for k, v in item.items()})


def create_table(client, table_name: str) -> None:
    client.create_table(
        TableName=table_name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
    )
    client.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
    )


class DynamoRepo:
    def __init__(self, client, table_name: str) -> None:
        self._db = client
        self._table = table_name

    def _put(self, item: dict[str, Any], condition: str, **expr: Any) -> dict[str, Any]:
        put: dict[str, Any] = {
            "TableName": self._table,
            "Item": _dump(item),
            "ConditionExpression": condition,
        }
        if expr.get("names"):
            put["ExpressionAttributeNames"] = expr["names"]
        if expr.get("values"):
            put["ExpressionAttributeValues"] = _dump(expr["values"])
        return {"Put": put}

    def _transact(self, ops: list[dict[str, Any]]) -> None:
        try:
            self._db.transact_write_items(TransactItems=ops)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            reasons = exc.response.get("CancellationReasons") or []
            raise ConditionFailed([r.get("Code") for r in reasons]) from exc

    def create_incident(self, incident: Incident, event: Event, idem: IdemRecord, now_epoch: int):
        idem_item = {
            "PK": tenant_pk(idem.tenant_id),
            "SK": IDEM_PREFIX + idem.key,
            "body_hash": idem.body_hash,
            "incident_id": idem.incident_id,
            "reference": idem.reference,
            "ttl": idem.expires_at,
        }
        ops = [
            self._put(
                idem_item,
                "attribute_not_exists(PK) OR #ttl <= :now",
                names={"#ttl": "ttl"},
                values={":now": now_epoch},
            ),
            self._put(incident_to_item(incident), "attribute_not_exists(PK)"),
            self._put(event_to_item(event), "attribute_not_exists(PK)"),
        ]
        try:
            self._transact(ops)
        except ConditionFailed as exc:
            codes = exc.args[0] if exc.args else []
            if codes and codes[0] == "ConditionalCheckFailed":
                raise IdempotencyExists(
                    self.get_idempotency(idem.tenant_id, idem.key, now_epoch)
                ) from exc
            raise

    def get_idempotency(self, tenant_id: str, key: str, now_epoch: int) -> IdemRecord | None:
        item = self._get(tenant_pk(tenant_id), IDEM_PREFIX + key)
        if not item or item["ttl"] <= now_epoch:
            return None
        return IdemRecord(
            tenant_id=tenant_id,
            key=key,
            body_hash=item["body_hash"],
            incident_id=item["incident_id"],
            reference=item["reference"],
            expires_at=item["ttl"],
        )

    def _get(self, pk: str, sk: str) -> dict[str, Any] | None:
        resp = self._db.get_item(
            TableName=self._table,
            Key={"PK": {"S": pk}, "SK": {"S": sk}},
            ConsistentRead=True,
        )
        return _load(resp["Item"]) if "Item" in resp else None

    def get_incident(self, tenant_id: str, incident_id: str) -> Incident | None:
        item = self._get(tenant_pk(tenant_id), INC_PREFIX + incident_id)
        return item_to_incident(item) if item else None

    def commit_change(
        self, after: Incident, expected_version: int, expected_status: Status, event: Event
    ) -> None:
        self._transact(
            [
                self._put(
                    incident_to_item(after),
                    "#v = :v AND #s = :s",
                    names={"#v": "version", "#s": "status"},
                    values={":v": expected_version, ":s": str(expected_status)},
                ),
                self._put(event_to_item(event), "attribute_not_exists(PK)"),
            ]
        )

    def list_incidents(
        self, tenant_id: str, flt: QueueFilter, cursor: str | None, limit: int
    ) -> Page:
        names: dict[str, str] = {}
        values: dict[str, Any] = {":pk": tenant_pk(tenant_id), ":lo": INC_PREFIX}
        if flt.created_before_id:
            key_cond = "PK = :pk AND SK BETWEEN :lo AND :hi"
            values[":hi"] = INC_PREFIX + flt.created_before_id
        else:
            key_cond = "PK = :pk AND begins_with(SK, :lo)"
        filters = []
        for attr, val in (("status", flt.status), ("severity", flt.severity), ("type", flt.type)):
            if val:
                names[f"#{attr}"] = attr
                values[f":{attr}"] = str(val)
                filters.append(f"#{attr} = :{attr}")

        params: dict[str, Any] = {
            "TableName": self._table,
            "KeyConditionExpression": key_cond,
            "ExpressionAttributeValues": _dump(values),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if filters:
            params["FilterExpression"] = " AND ".join(filters)
            params["ExpressionAttributeNames"] = names
        if cursor:
            params["ExclusiveStartKey"] = {"PK": {"S": tenant_pk(tenant_id)}, "SK": {"S": cursor}}

        matched: list[Incident] = []
        for _ in range(MAX_QUERY_PAGES):
            resp = self._db.query(**params)
            items = resp.get("Items", [])
            for i, raw in enumerate(items):
                matched.append(item_to_incident(_load(raw)))
                if len(matched) == limit:
                    more = i < len(items) - 1 or "LastEvaluatedKey" in resp
                    return Page(matched, INC_PREFIX + matched[-1].id if more else None)
            last = resp.get("LastEvaluatedKey")
            if not last:
                return Page(matched, None)
            params["ExclusiveStartKey"] = last
        return Page(matched, last["SK"]["S"])

    def list_events(self, tenant_id: str, incident_id: str) -> list[Event]:
        params: dict[str, Any] = {
            "TableName": self._table,
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :evt)",
            "ExpressionAttributeValues": {
                ":pk": {"S": events_pk(tenant_id, incident_id)},
                ":evt": {"S": EVT_PREFIX},
            },
            "ConsistentRead": True,
        }
        events: list[Event] = []
        while True:
            resp = self._db.query(**params)
            events.extend(item_to_event(_load(i)) for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                return events
            params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

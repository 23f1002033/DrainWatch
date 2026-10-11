import threading

from tests.conftest import DEMO, OP, OTHER, OTHER_OP

URL = f"/api/v1/public/{DEMO}/incidents"
BODY = {"type": "blocked_drain", "description": "Drain blocked by leaves", "lat": 12.97}


def create(client, key, body=BODY, url=URL):
    return client.post(url, json=body, headers={"Idempotency-Key": key})


def queue(client, headers=OP):
    return client.get("/api/v1/incidents", headers=headers).json()["items"]


def test_same_key_same_body_returns_same_reference(client):
    first = create(client, "retry-key-1")
    second = create(client, "retry-key-1")
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert set(first.json()) == {"reference"}
    items = queue(client)
    assert len(items) == 1
    events = client.get(f"/api/v1/incidents/{items[0]['id']}/events", headers=OP).json()
    assert len(events["items"]) == 1


def test_same_key_different_body_is_409(client):
    create(client, "retry-key-2")
    resp = create(client, "retry-key-2", {**BODY, "description": "something else"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(queue(client)) == 1


def test_missing_or_bad_key_is_400(client):
    assert client.post(URL, json=BODY).status_code == 400
    assert create(client, "short").status_code == 400


def test_key_expires_after_24h(client, clock):
    first = create(client, "retry-key-3").json()
    clock.advance(hours=23, minutes=59)
    assert create(client, "retry-key-3").json() == first
    clock.advance(minutes=2)
    later = create(client, "retry-key-3").json()
    assert later != first
    assert len(queue(client)) == 2


def test_key_is_scoped_per_tenant(client):
    a = create(client, "shared-key-1").json()
    b = create(client, "shared-key-1", url=f"/api/v1/public/{OTHER}/incidents").json()
    assert a != b
    assert len(queue(client)) == 1
    assert len(queue(client, OTHER_OP)) == 1


def test_concurrent_same_key_creates_one_incident(service):
    results, errors = [], []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        try:
            results.append(service.report(DEMO, "race-key-1", dict(BODY)))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(set(results)) == 1
    assert len(service.repo.list_incidents(DEMO, _no_filter(), None, 100).items) == 1


def _no_filter():
    from repo.base import QueueFilter

    return QueueFilter()

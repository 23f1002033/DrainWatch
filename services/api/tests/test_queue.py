from tests.conftest import OP, incident_in, new_incident, report


def get(client, **params):
    resp = client.get("/api/v1/incidents", params=params, headers=OP)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_newest_first(client, clock):
    refs = []
    for _ in range(3):
        refs.append(report(client))
        clock.advance(minutes=5)
    assert [i["reference"] for i in get(client)["items"]] == list(reversed(refs))


def test_filters(client):
    a = new_incident(client, type="blocked_drain")
    b = incident_in(client, "triaged")
    assert [i["id"] for i in get(client, type="blocked_drain")["items"]] == [a["id"]]
    assert [i["id"] for i in get(client, status="triaged")["items"]] == [b["id"]]
    assert [i["id"] for i in get(client, severity="S2")["items"]] == [b["id"]]
    assert get(client, severity="S1")["items"] == []
    assert get(client, status="triaged", type="blocked_drain")["items"] == []


def test_older_than_hours(client, clock):
    old = new_incident(client)
    clock.advance(hours=5)
    new_incident(client)
    clock.advance(minutes=30)
    assert [i["id"] for i in get(client, older_than_hours=4)["items"]] == [old["id"]]
    assert len(get(client, older_than_hours=0)["items"]) == 2
    assert get(client, older_than_hours=6)["items"] == []


def test_pagination_with_filter_visits_every_match_once(client, clock):
    expected = set()
    for n in range(13):
        inc = new_incident(client, type="blocked_drain" if n % 3 == 0 else "waterlogging")
        if n % 3 == 0:
            expected.add(inc["id"])
        clock.advance(seconds=1)
    seen: list[str] = []
    cursor = None
    while True:
        page = get(client, type="blocked_drain", limit=2, **({"cursor": cursor} if cursor else {}))
        seen.extend(i["id"] for i in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen))
    assert set(seen) == expected
    assert seen == sorted(seen, reverse=True)


def test_bad_query_params(client):
    resp = client.get("/api/v1/incidents", params={"cursor": "!!!notbase64"}, headers=OP)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"
    resp = client.get("/api/v1/incidents", params={"cursor": "SU5DI2Zvbw"}, headers=OP)
    assert resp.status_code == 400
    assert client.get("/api/v1/incidents?status=bogus", headers=OP).status_code == 422
    assert client.get("/api/v1/incidents?limit=1000", headers=OP).status_code == 422

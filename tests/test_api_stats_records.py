from __future__ import annotations

from tests.test_api_matches_votes import _auth, _login, _record, client, db_factory, server  # noqa: F401


def test_records_count_wins_losses_and_mvps(client, server):
    first = _record(client, server, winner=0).json()
    url = f"/servers/{server['id']}"
    ids = server["ids"]
    client.post(f"{url}/matches/{first['id']}/user-mvp", headers=_auth(server["owner"]), json={"player_id": ids["p5"]})

    rows = client.get(f"{url}/stats/records", headers=_auth(server["owner"])).json()
    by_name = {r["nickname"]: r for r in rows}
    assert len(rows) == 10
    # The saved run put p0..p4 on team 0 (winner) and p5..p9 on team 1.
    assert by_name["p0"]["wins"] == 1 and by_name["p0"]["losses"] == 0
    assert by_name["p5"]["wins"] == 0 and by_name["p5"]["losses"] == 1
    assert by_name["p5"]["user_mvp"] == 1
    assert sum(r["ai_mvp"] for r in rows) == 1
    ratings = [r["final_rating"] for r in rows]
    assert ratings == sorted(ratings, reverse=True)


def test_player_record_detail(client, server):
    match = _record(client, server, winner=0).json()
    url = f"/servers/{server['id']}/stats/players/{server['ids']['p0']}/record"
    # Any member can read it.
    token = _login(client, server["id"], "p9")
    res = client.get(url, headers=_auth(token))
    assert res.status_code == 200, res.text
    detail = res.json()
    assert detail["record"]["games"] == 1 and detail["record"]["wins"] == 1
    assert detail["positions"] and detail["positions"][0]["games"] == 1
    assert len(detail["rating_history"]) == 1
    point = detail["rating_history"][0]
    assert point["match_id"] == match["id"] and point["won"] is True and point["delta"] > 0
    recent = detail["recent"][0]
    assert recent["match_id"] == match["id"] and recent["won"] is True
    assert sorted(recent["teammates"]) == ["p1", "p2", "p3", "p4"]


def test_player_record_for_unknown_player_is_404(client, server):
    res = client.get(f"/servers/{server['id']}/stats/players/9999/record", headers=_auth(server["owner"]))
    assert res.status_code == 404


def test_player_with_no_games_has_an_empty_record(client, server):
    res = client.get(
        f"/servers/{server['id']}/stats/players/{server['ids']['p3']}/record", headers=_auth(server["owner"])
    ).json()
    assert res["record"]["games"] == 0
    assert res["recent"] == [] and res["rating_history"] == [] and res["positions"] == []

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.main import app
from app.database.base import Base
from app.models.team import Team
from app.services.player_service import PlayerService
from app.services.team_service import TeamService

JOIN = "lol2026"


@pytest.fixture
def db_factory():
    from app.database import entities  # noqa: F401  registers tables on Base.metadata

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(db_factory):
    def _get_db():
        session = db_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[deps.get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def server(client, db_factory):
    """A server with 10 players (p0..p9) and one saved team run."""
    res = client.post(
        "/servers", json={"name": "서버", "owner_display_name": "Owner", "join_code": JOIN, "owner_pin": "1234"}
    )
    server_id, owner = res.json()["member"]["server_id"], res.json()["token"]
    for i in range(10):
        r = client.post(
            f"/servers/{server_id}/players",
            headers=_auth(owner),
            json={"nickname": f"p{i}", "tier": "GOLD", "division": "I", "lp": 0, "main_role": "MID"},
        )
        assert r.status_code == 200, r.text
    with db_factory() as session:
        players = sorted(PlayerService(session, server_id).list_players(), key=lambda p: p.nickname)
        TeamService(session, server_id).repo.save_generated_teams(
            [Team(index=0, players=players[:5]), Team(index=1, players=players[5:])]
        )
    run_at = client.get(f"/servers/{server_id}/teams/runs", headers=_auth(owner)).json()[0]
    ids = {p["nickname"]: p["id"] for p in client.get(f"/servers/{server_id}/players", headers=_auth(owner)).json()}
    return {"id": server_id, "owner": owner, "run_at": run_at, "ids": ids}


def _login(client, server_id, name, pin=None) -> str:
    r = client.post(f"/servers/{server_id}/session", json={"display_name": name, "join_code": JOIN, "pin": pin})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _record(client, server, winner=0):
    return client.post(
        f"/servers/{server['id']}/matches",
        headers=_auth(server["owner"]),
        json={"team_run_at": server["run_at"], "winning_team_index": winner},
    )


def _ratings(client, server) -> dict[str, tuple[float, int]]:
    rows = client.get(f"/servers/{server['id']}/players", headers=_auth(server["owner"])).json()
    return {p["nickname"]: (p["internal_rating"], p["games_played"]) for p in rows}


# --- matches: record from a saved run, list, delete ---


def test_record_from_saved_run_then_reject_a_second_recording(client, server):
    res = _record(client, server)
    assert res.status_code == 200, res.text
    assert res.json()["team_run_at"].startswith(server["run_at"][:19])
    assert len(res.json()["participants"]) == 10

    again = _record(client, server, winner=1)
    assert again.status_code == 409
    assert "이미" in again.json()["detail"]


def test_list_and_delete_restores_ratings(client, server):
    before = _ratings(client, server)
    match_id = _record(client, server).json()["id"]
    assert _ratings(client, server) != before

    listed = client.get(f"/servers/{server['id']}/matches", headers=_auth(server["owner"])).json()
    assert [m["id"] for m in listed] == [match_id]
    assert listed[0]["revertible"] is True

    player = _login(client, server["id"], "p0")
    assert client.delete(f"/servers/{server['id']}/matches/{match_id}", headers=_auth(player)).status_code == 403

    res = client.delete(f"/servers/{server['id']}/matches/{match_id}", headers=_auth(server["owner"]))
    assert res.status_code == 200
    assert res.json() == {"ratings_reverted": True}
    after = _ratings(client, server)
    for name, (rating, games) in before.items():
        assert after[name][0] == pytest.approx(rating)
        assert after[name][1] == games
    # The run is free to be recorded again (the "fix a wrong winner" path).
    assert _record(client, server, winner=1).status_code == 200


def test_record_needs_teams_or_a_run(client, server):
    res = client.post(
        f"/servers/{server['id']}/matches", headers=_auth(server["owner"]), json={"winning_team_index": 0}
    )
    assert res.status_code == 400


# --- votes: yourself, or on someone's behalf as an admin ---


def test_a_player_votes_as_themselves_once(client, server):
    match_id = _record(client, server).json()["id"]
    token = _login(client, server["id"], "p0")
    assert client.get(f"/servers/{server['id']}/me/player", headers=_auth(token)).json()["nickname"] == "p0"

    vote = lambda body: client.post(  # noqa: E731
        f"/servers/{server['id']}/matches/{match_id}/votes", headers=_auth(token), json=body
    )
    first = vote({"voted_player_id": server["ids"]["p5"]})
    assert first.status_code == 200, first.text
    assert first.json()["voter_player_id"] == server["ids"]["p0"]

    second = vote({"voted_player_id": server["ids"]["p6"]})
    assert second.status_code == 409
    assert second.json()["detail"] == "이미 이 경기에 투표했습니다"


def test_a_player_cannot_vote_as_someone_else(client, server):
    match_id = _record(client, server).json()["id"]
    token = _login(client, server["id"], "p0")
    res = client.post(
        f"/servers/{server['id']}/matches/{match_id}/votes",
        headers=_auth(token),
        json={"voter_player_id": server["ids"]["p1"], "voted_player_id": server["ids"]["p5"]},
    )
    assert res.status_code == 403


def test_a_member_with_no_matching_player_cannot_vote_until_linked(client, server):
    match_id = _record(client, server).json()["id"]
    token = _login(client, server["id"], "닉네임다름")
    assert client.get(f"/servers/{server['id']}/me/player", headers=_auth(token)).json() is None
    res = client.post(
        f"/servers/{server['id']}/matches/{match_id}/votes",
        headers=_auth(token),
        json={"voted_player_id": server["ids"]["p5"]},
    )
    assert res.status_code == 400
    assert "연결" in res.json()["detail"]

    members = client.get(f"/servers/{server['id']}/members", headers=_auth(server["owner"])).json()
    member_id = next(m["id"] for m in members if m["display_name"] == "닉네임다름")
    # Only admins can link.
    denied = client.put(
        f"/servers/{server['id']}/members/{member_id}/player",
        headers=_auth(token),
        json={"player_id": server["ids"]["p2"]},
    )
    assert denied.status_code == 403
    linked = client.put(
        f"/servers/{server['id']}/members/{member_id}/player",
        headers=_auth(server["owner"]),
        json={"player_id": server["ids"]["p2"]},
    )
    assert linked.status_code == 200 and linked.json()["player_id"] == server["ids"]["p2"]

    res = client.post(
        f"/servers/{server['id']}/matches/{match_id}/votes",
        headers=_auth(token),
        json={"voted_player_id": server["ids"]["p5"]},
    )
    assert res.status_code == 200
    assert res.json()["voter_player_id"] == server["ids"]["p2"]


def test_an_admin_can_vote_on_someones_behalf(client, server):
    match_id = _record(client, server).json()["id"]
    res = client.post(
        f"/servers/{server['id']}/matches/{match_id}/votes",
        headers=_auth(server["owner"]),
        json={"voter_player_id": server["ids"]["p1"], "voted_player_id": server["ids"]["p5"]},
    )
    assert res.status_code == 200
    assert res.json()["voter_player_id"] == server["ids"]["p1"]

from __future__ import annotations

import dataclasses
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.auth import read_token
from app.riot.client import resolve_riot_api_key
from app.api.main import app
from app.api.routers import servers as servers_router
from app.database.base import Base
from app.services.server_service import ServerService
from app.utils.enums import Role


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
    # Not used as a context manager, so the startup hook (init_db against
    # the real local DB) never runs.
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_server(client, join_code="lol2026", owner_pin="1234") -> tuple[int, str]:
    res = client.post(
        "/servers",
        json={"name": "서버", "owner_display_name": "Owner", "join_code": join_code, "owner_pin": owner_pin},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return body["member"]["server_id"], body["token"]


def _login(client, server_id, name, join_code="lol2026", pin=None):
    return client.post(f"/servers/{server_id}/session", json={"display_name": name, "join_code": join_code, "pin": pin})


def test_server_scoped_and_ocr_endpoints_reject_requests_without_a_token(client):
    server_id, _ = _create_server(client)

    assert client.get(f"/servers/{server_id}/players").status_code == 401
    assert client.get(f"/servers/{server_id}/stats/leaderboard").status_code == 401
    assert client.post(f"/servers/{server_id}/teams/generate", json={"player_ids": []}).status_code == 401
    assert client.post("/ocr/riot-ids", files={"file": ("a.png", b"x")}).status_code == 401
    assert client.get(f"/servers/{server_id}/players", headers=_auth("forged.token")).status_code == 401


def test_creating_a_server_returns_a_working_owner_token(client):
    server_id, token = _create_server(client)

    res = client.get(f"/servers/{server_id}/me", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["role"] == "OWNER"
    assert client.get(f"/servers/{server_id}/players", headers=_auth(token)).status_code == 200


def test_player_login_needs_the_right_entry_code_but_no_pin(client):
    server_id, _ = _create_server(client)

    assert _login(client, server_id, "홍길동", join_code="wrong").status_code == 401

    res = _login(client, server_id, "홍길동")
    assert res.status_code == 200
    assert res.json()["member"]["role"] == "PLAYER"
    assert client.get(f"/servers/{server_id}/players", headers=_auth(res.json()["token"])).status_code == 200


def test_a_token_for_one_server_does_not_open_another(client):
    server_a, token_a = _create_server(client)
    server_b, _ = _create_server(client)

    assert client.get(f"/servers/{server_b}/players", headers=_auth(token_a)).status_code == 401


def test_typing_the_owners_name_without_their_pin_does_not_grant_owner(client):
    server_id, _ = _create_server(client)

    assert _login(client, server_id, "Owner").status_code == 401
    assert _login(client, server_id, "Owner", pin="9999").status_code == 401
    assert _login(client, server_id, "Owner", pin="1234").status_code == 200


def test_player_cannot_use_admin_endpoints(client):
    server_id, _ = _create_server(client)
    player_token = _login(client, server_id, "홍길동").json()["token"]

    res = client.put(f"/servers/{server_id}/season-label", json={"label": "X"}, headers=_auth(player_token))
    assert res.status_code == 403
    res = client.put(f"/servers/{server_id}/join-code", json={"join_code": "hijack"}, headers=_auth(player_token))
    assert res.status_code == 403


def test_pre_existing_admin_claims_a_pin_on_first_login(client, db_factory):
    with db_factory() as session:
        server = ServerService(session).create_server("서버", owner_display_name="Legacy")  # no code, no PIN

    assert _login(client, server.id, "Legacy", join_code="").status_code == 401  # admin still needs a PIN
    assert _login(client, server.id, "Legacy", join_code="", pin="5678").status_code == 200
    assert _login(client, server.id, "Legacy", join_code="", pin="0000").status_code == 401


def test_changing_the_entry_code_logs_everyone_out_but_the_owner(client):
    server_id, owner_token = _create_server(client)
    player_token = _login(client, server_id, "홍길동").json()["token"]

    res = client.put(f"/servers/{server_id}/join-code", json={"join_code": "newcode"}, headers=_auth(owner_token))
    assert res.status_code == 200
    new_owner_token = res.json()["token"]

    assert client.get(f"/servers/{server_id}/players", headers=_auth(player_token)).status_code == 401
    assert client.get(f"/servers/{server_id}/players", headers=_auth(owner_token)).status_code == 401
    assert client.get(f"/servers/{server_id}/players", headers=_auth(new_owner_token)).status_code == 200
    assert _login(client, server_id, "홍길동").status_code == 401
    assert _login(client, server_id, "홍길동", join_code="newcode").status_code == 200


def test_promoted_player_must_log_in_again_with_a_pin(client):
    server_id, owner_token = _create_server(client)
    player_token = _login(client, server_id, "홍길동").json()["token"]

    res = client.post(
        f"/servers/{server_id}/members/promote", json={"target_display_name": "홍길동"}, headers=_auth(owner_token)
    )
    assert res.status_code == 200

    assert client.get(f"/servers/{server_id}/me", headers=_auth(player_token)).status_code == 401
    res = _login(client, server_id, "홍길동", pin="4321")
    assert res.status_code == 200
    assert res.json()["member"]["role"] == Role.SERVER_ADMIN.value


def test_owner_can_reset_an_admins_pin_and_it_revokes_their_session(client):
    server_id, owner_token = _create_server(client)
    client.post(f"/servers/{server_id}/members/promote", json={"target_display_name": "Admin"}, headers=_auth(owner_token))
    admin_token = _login(client, server_id, "Admin", pin="1111").json()["token"]

    # A Server Admin can't reset the Owner's PIN...
    res = client.post(f"/servers/{server_id}/members/reset-pin", json={"target_display_name": "Owner"}, headers=_auth(admin_token))
    assert res.status_code == 403

    # ...but the Owner can reset the admin's.
    res = client.post(f"/servers/{server_id}/members/reset-pin", json={"target_display_name": "Admin"}, headers=_auth(owner_token))
    assert res.status_code == 200
    assert client.get(f"/servers/{server_id}/me", headers=_auth(admin_token)).status_code == 401
    assert _login(client, server_id, "Admin", pin="2222").status_code == 200


def test_change_own_pin_reissues_the_token(client):
    server_id, owner_token = _create_server(client)

    res = client.put(f"/servers/{server_id}/me/pin", json={"current_pin": "0000", "new_pin": "9999"}, headers=_auth(owner_token))
    assert res.status_code == 401

    res = client.put(f"/servers/{server_id}/me/pin", json={"current_pin": "1234", "new_pin": "9999"}, headers=_auth(owner_token))
    assert res.status_code == 200
    assert client.get(f"/servers/{server_id}/me", headers=_auth(owner_token)).status_code == 401
    assert client.get(f"/servers/{server_id}/me", headers=_auth(res.json()["token"])).status_code == 200


def test_server_creation_is_gated_by_the_creation_code_when_set(client, monkeypatch):
    gated = dataclasses.replace(servers_router.settings, server_creation_code="letmein")
    monkeypatch.setattr(servers_router, "settings", gated)
    body = {"name": "서버", "owner_display_name": "Owner", "join_code": "lol2026", "owner_pin": "1234"}

    assert client.post("/servers", json=body).status_code == 403
    assert client.post("/servers", json={**body, "creation_code": "nope"}).status_code == 403
    assert client.post("/servers", json={**body, "creation_code": "letmein"}).status_code == 200


def test_server_creation_is_disabled_on_vercel_without_a_creation_code(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    body = {"name": "서버", "owner_display_name": "Owner", "join_code": "lol2026", "owner_pin": "1234"}
    assert client.post("/servers", json=body).status_code == 403


def test_short_entry_code_or_pin_is_rejected(client):
    body = {"name": "서버", "owner_display_name": "Owner", "join_code": "ab", "owner_pin": "1234"}
    assert client.post("/servers", json=body).status_code == 400


def test_player_login_lasts_a_year_but_admin_login_a_month(client):
    server_id, owner_token = _create_server(client)
    player_token = _login(client, server_id, "홍길동").json()["token"]

    def days_left(token):
        import base64, json
        body = token.split(".")[0]
        return (json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))["exp"] - time.time()) / 86400

    read_token(player_token)  # signature still verifies
    assert days_left(player_token) > 360
    assert 29 < days_left(owner_token) < 31


def test_owner_can_rename_the_server_and_a_member_who_stays_logged_in(client):
    server_id, owner_token = _create_server(client)
    player_token = _login(client, server_id, "홍길동").json()["token"]

    res = client.put(f"/servers/{server_id}/name", json={"name": "새 이름"}, headers=_auth(owner_token))
    assert res.status_code == 200 and res.json()["name"] == "새 이름"

    res = client.put(
        f"/servers/{server_id}/members/rename",
        json={"target_display_name": "Owner", "new_display_name": "새오너"},
        headers=_auth(owner_token),
    )
    assert res.status_code == 200
    me = client.get(f"/servers/{server_id}/me", headers=_auth(owner_token))
    assert me.status_code == 200 and me.json()["display_name"] == "새오너" and me.json()["role"] == "OWNER"
    # The PIN moved with the membership, under the new name.
    assert _login(client, server_id, "새오너", pin="1234").status_code == 200

    # Name collisions and non-owners are rejected.
    res = client.put(
        f"/servers/{server_id}/members/rename",
        json={"target_display_name": "새오너", "new_display_name": "홍길동"},
        headers=_auth(owner_token),
    )
    assert res.status_code == 409
    res = client.put(f"/servers/{server_id}/name", json={"name": "X"}, headers=_auth(player_token))
    assert res.status_code == 403


def test_riot_api_key_is_stored_in_the_db_and_never_returned_in_full(client, db_factory):
    server_id, owner_token = _create_server(client)
    player_token = _login(client, server_id, "홍길동").json()["token"]
    key = "RGAPI-00000000-test-only-0000-abcd"

    res = client.put(f"/servers/{server_id}/riot-api-key", json={"api_key": key}, headers=_auth(player_token))
    assert res.status_code == 403
    res = client.put(f"/servers/{server_id}/riot-api-key", json={"api_key": "not-a-key"}, headers=_auth(owner_token))
    assert res.status_code == 400

    res = client.put(f"/servers/{server_id}/riot-api-key", json={"api_key": key}, headers=_auth(owner_token))
    assert res.status_code == 200
    assert res.json() == {"configured": True, "source": "db", "last4": "abcd"}
    assert key not in res.text
    with db_factory() as session:
        assert resolve_riot_api_key(session) == key

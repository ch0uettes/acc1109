from __future__ import annotations

from typing import Iterator, Optional

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.auth import read_token
from app.database.base import SessionLocal
from app.models.server_membership import ServerMembership
from app.services.server_service import ServerService
from app.utils.exceptions import AuthenticationError


def get_db() -> Iterator[Session]:
    """One session per request. Rolling back here (rather than in every
    route) mirrors the exact pattern the Streamlit pages used - a failed
    commit leaves a session's transaction unusable until rolled back (see
    PlayerService.rollback's docstring) - but centralized, since each
    request already gets its own short-lived session instead of the
    Streamlit pages' one-session-per-render-tree lifetime."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_member(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> ServerMembership:
    """Any logged-in member of any server - for endpoints that aren't
    server-scoped (OCR) but still cost money per call, so a stranger
    without a token can't hit them. The identity comes only from the
    signed token issued by POST /servers/{id}/session (see app/auth.py),
    never from a client-supplied name, and its Role is re-read from the
    DB on every request."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("입장이 필요합니다")
    claims = read_token(authorization.removeprefix("Bearer ").strip())
    return ServerService(db).resolve_token(claims)


def get_actor(server_id: int, member: ServerMembership = Depends(get_member)) -> ServerMembership:
    """A logged-in member of *this* server (the {server_id} path param) -
    a token for one server never opens another."""
    if member.server_id != server_id:
        raise AuthenticationError("이 서버에 입장한 상태가 아닙니다")
    return member

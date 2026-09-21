from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database.base import SessionLocal
from app.models.server_membership import ServerMembership
from app.services.server_service import ServerService


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


def get_actor(
    server_id: int,
    x_actor_name: str = Header(..., alias="X-Actor-Name"),
    db: Session = Depends(get_db),
) -> ServerMembership:
    """Resolves the acting identity's Role server-side from its
    ServerMembership row - never trusts a client-supplied role. Same
    "pick a name" identity model as the Streamlit UI's actor picker
    (see DEPLOY.md): X-Actor-Name is just a display name, not a login
    credential."""
    member = ServerService(db).get_member(server_id, x_actor_name)
    if member is None:
        raise HTTPException(status_code=404, detail=f"'{x_actor_name}' is not a member of this server")
    return member

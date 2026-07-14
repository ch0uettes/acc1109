from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.utils.enums import Role


class ServerMembership(BaseModel):
    """Ties an identity to a Role within one Server. There is no login
    system yet, so `display_name` is the only identifying field for now
    (free text an operator enters when registering an admin) - `discord_id`
    is reserved for when a real auth/Discord-linked identity exists, at
    which point this same row shape carries over without a migration."""

    id: Optional[int] = None
    server_id: int
    display_name: str
    discord_id: Optional[str] = None
    role: Role
    created_at: datetime

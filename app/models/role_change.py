from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.utils.enums import Role


class RoleChange(BaseModel):
    """Audit row for every Role change within a Server (promote, demote,
    ownership transfer, or the initial Owner grant at server creation -
    old_role=None there). Mirrors SeedRatingChange's shape so both audit
    trails read the same way: old value, new value, who, when, why."""

    id: Optional[int] = None
    server_id: int
    membership_id: int
    target_display_name: str
    old_role: Optional[Role]
    new_role: Role
    changed_by: str
    changed_at: datetime
    reason: Optional[str] = None

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RoleChangeEntity(Base):
    __tablename__ = "role_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    membership_id: Mapped[int] = mapped_column(ForeignKey("server_memberships.id"))
    target_display_name: Mapped[str]
    old_role: Mapped[Optional[str]] = mapped_column(nullable=True)
    new_role: Mapped[str]
    changed_by: Mapped[str]
    changed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    reason: Mapped[Optional[str]] = mapped_column(nullable=True)

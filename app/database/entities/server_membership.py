from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ServerMembershipEntity(Base):
    __tablename__ = "server_memberships"
    __table_args__ = (UniqueConstraint("server_id", "display_name", name="uq_server_membership_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    display_name: Mapped[str]
    discord_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    role: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

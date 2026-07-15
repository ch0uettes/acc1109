from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class InternalRatingChangeEntity(Base):
    __tablename__ = "internal_rating_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    old_internal_rating: Mapped[float]
    new_internal_rating: Mapped[float]
    changed_by: Mapped[str]
    changed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    reason: Mapped[Optional[str]] = mapped_column(nullable=True)

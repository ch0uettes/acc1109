from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RatingHistoryEntity(Base):
    __tablename__ = "rating_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    recorded_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    official_rating: Mapped[float]
    internal_rating: Mapped[float]
    reason: Mapped[str]

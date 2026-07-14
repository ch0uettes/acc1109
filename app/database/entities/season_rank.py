from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PlayerSeasonRankEntity(Base):
    __tablename__ = "player_season_ranks"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    season: Mapped[str]
    current_tier: Mapped[str]
    current_division: Mapped[str]
    current_lp: Mapped[int]
    peak_tier: Mapped[Optional[str]] = mapped_column(nullable=True)
    peak_division: Mapped[Optional[str]] = mapped_column(nullable=True)
    peak_lp: Mapped[Optional[int]] = mapped_column(nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

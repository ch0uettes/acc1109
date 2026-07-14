from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class VoteEntity(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    voter_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    voted_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

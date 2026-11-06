from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class MatchEntity(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    played_at: Mapped[datetime]
    winning_team_index: Mapped[int]
    ai_mvp_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    user_mvp_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(nullable=True)
    # The saved team run (teams.generated_at) this match was recorded from;
    # NULL for matches recorded before runs were linked.
    team_run_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    match_players: Mapped[list["MatchPlayerEntity"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class MatchPlayerEntity(Base):
    __tablename__ = "match_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_index: Mapped[int]
    position: Mapped[str]
    contribution_score: Mapped[float] = mapped_column(default=0.0)
    stat_detail: Mapped[str] = mapped_column(default="{}")
    # What this match did to the player, so deleting it can undo exactly
    # its share. NULL = recorded before these were kept: not revertible.
    internal_rating_before: Mapped[Optional[float]] = mapped_column(nullable=True)
    internal_rating_after: Mapped[Optional[float]] = mapped_column(nullable=True)
    exited_calibration: Mapped[Optional[bool]] = mapped_column(nullable=True)

    match: Mapped["MatchEntity"] = relationship(back_populates="match_players")

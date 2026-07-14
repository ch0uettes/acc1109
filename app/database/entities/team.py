from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TeamEntity(Base):
    """One team's snapshot from a single balancer run. `generated_at` is
    shared across all teams produced by the same run so they can be
    grouped without a separate batch table."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    team_index: Mapped[int]
    generated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    team_players: Mapped[list["TeamPlayerEntity"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


class TeamPlayerEntity(Base):
    __tablename__ = "team_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    position: Mapped[str]

    team: Mapped["TeamEntity"] = relationship(back_populates="team_players")

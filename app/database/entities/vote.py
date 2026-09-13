from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class VoteEntity(Base):
    __tablename__ = "votes"
    # One vote per (match, voter) - the last line of defense against a
    # double-submit or a race past VoteRepository's own existing-vote
    # check. A pre-existing deployment's votes table needs
    # scripts/migrate_2026_vote_uniqueness.py to actually get this index;
    # Base.metadata.create_all() only provisions it for a fresh table.
    __table_args__ = (UniqueConstraint("match_id", "voter_player_id", name="uq_vote_match_voter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    voter_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    voted_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

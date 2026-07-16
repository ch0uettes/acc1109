from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PlayerEntity(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("server_id", "nickname", name="uq_player_server_nickname"),
        UniqueConstraint("server_id", "puuid", name="uq_player_server_puuid"),
        UniqueConstraint("server_id", "discord_id", name="uq_player_server_discord_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))
    discord_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    puuid: Mapped[Optional[str]] = mapped_column(nullable=True)
    nickname: Mapped[str]
    tier: Mapped[str]
    division: Mapped[str] = mapped_column(default="IV")
    lp: Mapped[int] = mapped_column(default=0)
    peak_tier: Mapped[Optional[str]] = mapped_column(nullable=True)
    peak_division: Mapped[Optional[str]] = mapped_column(nullable=True)
    peak_lp: Mapped[Optional[int]] = mapped_column(nullable=True)
    official_rating: Mapped[Optional[float]] = mapped_column(nullable=True)
    seed_rating: Mapped[Optional[float]] = mapped_column(nullable=True)
    rating_source: Mapped[str] = mapped_column(default="CURRENT_SEASON")
    calibration_mode: Mapped[bool] = mapped_column(default=False)
    internal_rating: Mapped[float] = mapped_column(default=0.0)
    main_role: Mapped[str]
    sub_role: Mapped[Optional[str]] = mapped_column(nullable=True)
    recommended_main_role: Mapped[Optional[str]] = mapped_column(nullable=True)
    recommended_main_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    recommended_sub_role: Mapped[Optional[str]] = mapped_column(nullable=True)
    recommended_sub_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    recent_form: Mapped[float] = mapped_column(default=0.0)
    champion_pool: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.5)
    games_played: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[Optional[bool]] = mapped_column(nullable=True, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

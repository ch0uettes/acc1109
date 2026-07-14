from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ServerEntity(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    discord_guild_id: Mapped[Optional[str]] = mapped_column(unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    # NULL = use DEFAULT_NORMALIZATION_CONFIG/DEFAULT_HARD_CONSTRAINT_CONFIG
    # (app/balance/config.py) - only set once an Owner saves an override via
    # the 서버 관리 page. Stored as the full dataclass -> dict, not a partial
    # diff, so loading never has to merge with the code-level default.
    normalization_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    hard_constraint_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)

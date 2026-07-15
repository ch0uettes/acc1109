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
    # NULL = use settings.current_season_label (env-var default) - only set
    # once an Owner/Server Admin saves an override via the 서버 관리 page.
    # Per-server because different Discord servers/leagues can be on
    # different splits, unlike the old single global env var.
    current_season_label: Mapped[Optional[str]] = mapped_column(nullable=True, default=None)
    # NULL = every Constraint plugin uses its own default_priority (see
    # app/balance/constraint_engine) - name -> priority override, only set
    # once an Owner/Server Admin saves one via the 서버 관리 page. No UI
    # form ships yet (backend-ready, matching SearchPolicy's unexercised
    # hooks) - this column exists so a future one needs no schema change.
    constraint_priorities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)

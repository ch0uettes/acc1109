from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AppSettingEntity(Base):
    """Deployment-wide key/value settings that must survive serverless
    cold starts (an in-memory override doesn't) - e.g. the Riot API key,
    editable from the 서버 관리 page instead of only via env var +
    redeploy. A brand-new table, so init_db()'s create_all() provisions
    it on an existing DB without a migration script."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_by: Mapped[Optional[str]] = mapped_column(nullable=True)

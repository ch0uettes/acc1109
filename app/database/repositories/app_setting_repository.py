from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.database.entities.app_setting import AppSettingEntity

RIOT_API_KEY = "riot_api_key"


class AppSettingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str) -> str | None:
        entity = self.session.get(AppSettingEntity, key)
        return entity.value if entity else None

    def set(self, key: str, value: str | None, updated_by: str | None = None) -> None:
        entity = self.session.get(AppSettingEntity, key)
        if entity is None:
            entity = AppSettingEntity(key=key)
            self.session.add(entity)
        entity.value = value
        entity.updated_at = datetime.utcnow()
        entity.updated_by = updated_by
        self.session.commit()

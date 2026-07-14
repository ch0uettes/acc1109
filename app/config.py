"""Application-wide configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    database_url: str
    riot_api_key: Optional[str]
    riot_platform: str
    riot_region: str
    current_season_label: str


def _build_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "app.db"
    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        database_url=f"sqlite:///{db_path}",
        riot_api_key=os.environ.get("RIOT_API_KEY"),
        riot_platform=os.environ.get("RIOT_PLATFORM", "kr"),
        riot_region=os.environ.get("RIOT_REGION", "asia"),
        # Riot's API doesn't tag league entries with a season id, so there's
        # nothing to auto-detect here - bump this manually when a new split
        # starts. It only labels PlayerSeasonRank snapshots, nothing scores
        # off of it.
        current_season_label=os.environ.get("CURRENT_SEASON_LABEL", "2025-S2"),
    )


settings = _build_settings()


def update_riot_api_key(key: str) -> None:
    """Overrides the in-memory Riot API key for this running process only -
    never persisted to disk/env/DB. Riot dev keys expire every 24h, so a
    UI-driven temporary override (see the sidebar in app/ui/app.py) is more
    useful here than a permanent setting would be; restarting the app
    reverts to whatever RIOT_API_KEY the environment provides. `settings`
    is frozen to prevent accidental mutation everywhere else - this is the
    one blessed call site allowed to bypass that."""
    object.__setattr__(settings, "riot_api_key", key or None)

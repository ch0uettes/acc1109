from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.balance.config import (
    DEFAULT_HARD_CONSTRAINT_CONFIG,
    DEFAULT_NORMALIZATION_CONFIG,
    HardConstraintConfig,
    NormalizationConfig,
)


class Server(BaseModel):
    """One independent inhouse community. Every major entity (Player,
    Match, Vote, RatingHistory, PlayerSeasonRank, ...) belongs to exactly
    one Server, so two servers never share players, ratings, or match
    history - even if the same real Riot account plays in both.

    `discord_guild_id` is unused today but reserved so a future Discord Bot
    integration can map one Discord server to one of these 1:1 without a
    schema change.

    `normalization_config`/`hard_constraint_config` are this Server's
    override of the Balance Evaluator's Feature Normalizer thresholds and
    Hard Constraint thresholds (see app/balance/config.py) - editable by
    the Owner via the 서버 관리 page. Default to the shared module-level
    defaults until explicitly overridden, never None here (the DB column
    is nullable; ServerRepository resolves NULL to these defaults before
    building this domain object)."""

    id: Optional[int] = None
    name: str
    discord_guild_id: Optional[str] = None
    created_at: datetime
    normalization_config: NormalizationConfig = Field(default=DEFAULT_NORMALIZATION_CONFIG)
    hard_constraint_config: HardConstraintConfig = Field(default=DEFAULT_HARD_CONSTRAINT_CONFIG)

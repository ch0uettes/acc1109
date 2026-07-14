from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.utils.enums import Division, Position, RatingSource, Tier


class Player(BaseModel):
    """Domain representation of an inhouse participant.

    `tier`/`division`/`lp` are the *current season* values (UNRANKED if
    Riot has no current-season rank for them). `peak_tier` is independent
    metadata only - the highest tier ever reached - and never feeds into
    any rating computation; it exists purely as a future ML feature (e.g.
    current << peak suggests a returning player).

    Official Rating and Seed Rating are mutually exclusive, independently
    tracked concepts: `official_rating` is set only when a real tier basis
    exists (current season or an operator-verified manual entry);
    `seed_rating` is an operator's own skill judgment, used only when
    neither of those exists. Never derive one from the other.

    `main_role`/`sub_role` are the player's own Profile position, freely
    editable at any time - `recommended_main_role`/`recommended_sub_role`
    (+ their confidences) are a permanent, never-overwritten record of
    what Riot's match-history analysis suggested at registration time.
    They seed `main_role`/`sub_role` once, then become reference-only."""

    id: Optional[int] = None
    server_id: Optional[int] = None
    discord_id: Optional[str] = None
    puuid: Optional[str] = None
    nickname: str
    tier: Tier
    division: Division = Division.IV
    lp: int = 0
    peak_tier: Optional[Tier] = None
    peak_division: Optional[Division] = None
    peak_lp: Optional[int] = None
    official_rating: Optional[float] = None
    seed_rating: Optional[float] = None
    rating_source: RatingSource = RatingSource.CURRENT_SEASON
    calibration_mode: bool = False
    internal_rating: float = 0.0
    main_role: Position
    sub_role: Optional[Position] = None
    recommended_main_role: Optional[Position] = None
    recommended_main_confidence: Optional[float] = None
    recommended_sub_role: Optional[Position] = None
    recommended_sub_confidence: Optional[float] = None
    recent_form: float = 0.0
    champion_pool: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    games_played: int = 0

    @model_validator(mode="after")
    def _sub_role_must_differ_from_main(self) -> "Player":
        if self.sub_role == self.main_role:
            self.sub_role = None
        return self

    @property
    def base_rating(self) -> float:
        """Official Rating if a real tier basis exists, else the operator's
        Seed Rating, else 0 (should not normally happen - one of the two
        is always set once a player is fully registered)."""
        if self.official_rating is not None:
            return self.official_rating
        return self.seed_rating or 0.0

    @property
    def final_rating(self) -> float:
        """Weighted blend of base_rating and internal_rating. The blend
        shifts toward internal_rating as more inhouse games accumulate -
        see rating.final_blender.DEFAULT_FINAL_RATING_BLENDER."""
        from app.rating.final_blender import DEFAULT_FINAL_RATING_BLENDER

        return DEFAULT_FINAL_RATING_BLENDER.blend(self.base_rating, self.internal_rating, self.games_played)

from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    IRON = "IRON"
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"
    EMERALD = "EMERALD"
    DIAMOND = "DIAMOND"
    MASTER = "MASTER"
    UNRANKED = "UNRANKED"


class Division(str, Enum):
    """Riot division within a tier. Only meaningful for Iron~Diamond -
    Master and above has no division, just uncapped LP."""

    I = "I"
    II = "II"
    III = "III"
    IV = "IV"


class Position(str, Enum):
    TOP = "TOP"
    JUNGLE = "JUNGLE"
    MID = "MID"
    ADC = "ADC"
    SUPPORT = "SUPPORT"


class RatingSource(str, Enum):
    """Where a player's base rating (official_rating or seed_rating) came
    from - never collapse this into the tier field alone.

    CURRENT_SEASON: Riot API confirmed this season's rank -> official_rating.
    MANUAL: an operator typed in an exact tier/division/lp they know to be
        true (e.g. a friend without a linked Riot ID) -> official_rating.
    SEED: no real rank data exists at all (no current season, and Peak Tier
        is metadata-only, not a scoring input) - an operator judged the
        player's skill and assigned a starting point -> seed_rating. Never
        auto-computed (e.g. never a participant average); Estimated Rating
        as a self-serve/auto concept is retired in favor of this."""

    CURRENT_SEASON = "CURRENT_SEASON"
    MANUAL = "MANUAL"
    SEED = "SEED"


class Role(str, Enum):
    """RBAC role. PLATFORM_ADMIN is global (not tied to any one Server);
    every other role is scoped per-server via ServerMembership - the same
    identity can hold different roles in different servers. Actions are
    gated through app.services.rbac.require_permission, which reads
    ROLE_PERMISSIONS - adding a new role (MODERATOR is a reserved
    placeholder today, or a future COACH/ANALYST) means adding one enum
    value and one permission set, never touching callers."""

    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    OWNER = "OWNER"
    SERVER_ADMIN = "SERVER_ADMIN"
    MODERATOR = "MODERATOR"
    PLAYER = "PLAYER"

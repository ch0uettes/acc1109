from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.contribution import ContributionScore
from app.models.player import Player


class ContributionScoreCalculator(ABC):
    """Interface kept separate from MVP selection on purpose: MVP is
    derived from contribution scores, never computed directly."""

    @abstractmethod
    def calculate(self, player: Player, match_stats: dict[str, Any]) -> ContributionScore:
        ...


# A rough "average game" total under OCRContributionScoreCalculator's
# default weights (kills=4, deaths=4, assists=6, cs=120, gold=8000,
# damage=10000, vision=15 - a plausible mid-length ranked line), used as
# DummyContributionScoreCalculator's neutral placeholder. Not derived from
# player.final_rating: a high-rated player whose OCR row failed to match
# shouldn't be assumed to have had a great INDIVIDUAL box score this one
# match (rating reflects long-run skill, not this game), and doing so also
# put the fallback on a roughly 5-10x smaller scale than a real OCR-derived
# total (final_rating/100 rarely exceeds ~30, real totals commonly run
# 50-300) - meaning a player with a missed OCR row could effectively never
# be picked as MVP no matter how well they actually played. A fixed
# same-scale neutral value fixes both problems: it doesn't penalize a
# missed OCR match relative to a real one, and it doesn't secretly reward
# high-rated players for a game whose stats were never even read.
NEUTRAL_FALLBACK_TOTAL = 121.0


class DummyContributionScoreCalculator(ContributionScoreCalculator):
    """Fallback when no real match_stats exist for a player (e.g. OCR
    couldn't match their row to a registered nickname): a fixed neutral
    placeholder on the same scale as a real OCR-derived score, not derived
    from the player's rating (see NEUTRAL_FALLBACK_TOTAL)."""

    def calculate(self, player: Player, match_stats: dict[str, Any]) -> ContributionScore:
        return ContributionScore(player_id=player.id, combat=NEUTRAL_FALLBACK_TOTAL)


class OCRContributionScoreCalculator(ContributionScoreCalculator):
    """Computes Contribution Score from OCR-extracted match_stats
    (kills/deaths/assists reliably; cs/gold/damage/vision_score if the
    reviewer filled them in). Weights below are placeholders - they haven't
    been tuned against real games and should be revisited once they can be
    checked against actual match outcomes."""

    def __init__(
        self,
        kill_weight: float = 3.0,
        assist_weight: float = 1.5,
        damage_weight: float = 1 / 1000,
        vision_weight: float = 2.0,
        cs_weight: float = 0.5,
        gold_weight: float = 1 / 1000,
        death_weight: float = 2.0,
        fallback: ContributionScoreCalculator | None = None,
    ) -> None:
        self.kill_weight = kill_weight
        self.assist_weight = assist_weight
        self.damage_weight = damage_weight
        self.vision_weight = vision_weight
        self.cs_weight = cs_weight
        self.gold_weight = gold_weight
        self.death_weight = death_weight
        self.fallback = fallback or DummyContributionScoreCalculator()

    def calculate(self, player: Player, match_stats: dict[str, Any]) -> ContributionScore:
        if not match_stats:
            return self.fallback.calculate(player, match_stats)

        kills = match_stats.get("kills", 0)
        deaths = match_stats.get("deaths", 0)
        assists = match_stats.get("assists", 0)
        cs = match_stats.get("cs", 0)
        gold = match_stats.get("gold", 0)
        damage = match_stats.get("damage", 0)
        vision_score = match_stats.get("vision_score", 0)

        return ContributionScore(
            player_id=player.id,
            combat=kills * self.kill_weight + assists * self.assist_weight + damage * self.damage_weight,
            vision=vision_score * self.vision_weight,
            economy=cs * self.cs_weight + gold * self.gold_weight,
            objective=0.0,  # not reliably visible on the basic end-game screen
            death_penalty=deaths * self.death_weight,
        )

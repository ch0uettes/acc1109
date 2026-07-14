from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.player import Player


class RatingCalculator(ABC):
    """Strategy interface so official/internal rating math can evolve
    independently (e.g. Riot API driven tiers, Elo-based internal rating)."""

    @abstractmethod
    def calculate(self, player: Player) -> float:
        ...

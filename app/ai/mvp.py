from __future__ import annotations

from app.models.match import MatchPlayerResult


class AIMVPSelector:
    """Picks the highest Contribution Score. Deliberately distinct from
    User MVP, which comes from a vote tally (see services.vote_service)."""

    def select(self, participants: list[MatchPlayerResult]) -> int | None:
        if not participants:
            return None
        return max(participants, key=lambda p: p.contribution.total).player_id

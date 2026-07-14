from __future__ import annotations

from app.models.player import Player


def confidence_weighted_internal_rating(player: Player) -> float:
    """Scales a player's Internal Rating by how much this data should be
    trusted (Player.confidence, 0-1 - set when a rating is resolved: high
    for a Riot-confirmed current-season rank, low for an operator's Seed
    Rating guess on a brand-new player). Confidence isn't scored as its
    own independent Feature - it describes how much to trust *another*
    signal, so it doesn't earn or lose points by itself; it modifies the
    signal it's attached to instead:

        internal_rating_contribution = internal_rating * confidence

    This is a shared modifier, not a Feature - reusable by future
    learning-based Features (AI Prediction, MVP score, ...) that also
    want to discount low-confidence data, without any of them depending
    on a ConfidenceFeature that scores anything on its own."""
    return player.internal_rating * player.confidence

from __future__ import annotations


class AppError(Exception):
    """Base class for all domain-level errors."""


class PlayerNotFoundError(AppError):
    pass


class InvalidPlayerCountError(AppError):
    pass


class BalanceError(AppError):
    pass


class PermissionDeniedError(AppError):
    pass


class InvalidRatingValueError(AppError):
    pass


class MatchNotFoundError(AppError):
    pass


class InvalidVoteError(AppError):
    """Raised for a vote whose voter/candidate isn't actually a participant
    of the match being voted on."""


class DuplicateVoteError(AppError):
    """Raised when a voter has already cast a vote for this match."""


class DuplicateMembershipError(AppError):
    """Raised when a server membership insert collides with the
    (server_id, display_name) unique constraint - typically a race between
    two near-simultaneous self-registrations/promotions of the same name."""


class DuplicateServerError(AppError):
    """Raised when a server insert collides with the discord_guild_id
    unique constraint - another server is already linked to that guild."""

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

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.utils.exceptions import (
    AppError,
    DuplicateMembershipError,
    DuplicateServerError,
    DuplicateVoteError,
    InvalidPlayerCountError,
    InvalidRatingValueError,
    InvalidVoteError,
    MatchNotFoundError,
    PermissionDeniedError,
    PlayerNotFoundError,
)

_STATUS_BY_ERROR: dict[type[AppError], int] = {
    PermissionDeniedError: 403,
    PlayerNotFoundError: 404,
    MatchNotFoundError: 404,
    DuplicateMembershipError: 409,
    DuplicateServerError: 409,
    DuplicateVoteError: 409,
    InvalidVoteError: 400,
    InvalidRatingValueError: 400,
    InvalidPlayerCountError: 400,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        status_code = _STATUS_BY_ERROR.get(type(exc), 400)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # Same case the Streamlit pages caught explicitly per-call-site
        # (duplicate nickname/puuid/discord_id racing the unique
        # constraint) - get_db's rollback already unstuck the session,
        # this just turns it into a client-facing 409 instead of a 500.
        return JSONResponse(status_code=409, content={"detail": "이미 존재하는 데이터와 충돌했습니다 (중복)."})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Without this, an unhandled exception propagates past
        # CORSMiddleware to Starlette's ServerErrorMiddleware, which
        # returns a bare 500 with no CORS headers - the browser then
        # reports it to the frontend as a generic "Failed to fetch"
        # network error instead of a readable 500, since a cross-origin
        # response missing CORS headers is indistinguishable from a
        # network failure from the fetch() caller's side (observed
        # directly debugging the vote-casting flow). This still returns
        # 500 - it just makes sure the response actually reaches the
        # client instead of looking like the request never happened.
        return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})

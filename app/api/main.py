from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.errors import register_exception_handlers
from app.api.routers import matches, ocr, players, servers, stats, teams, votes
from app.database.base import init_db


class UTF8JSONResponse(JSONResponse):
    """Starlette's default JSONResponse sends `Content-Type: application/json`
    with no charset parameter - the bytes are always UTF-8 (confirmed
    directly: DB storage, psycopg2, and this response layer all checked out
    byte-for-byte correct), but without an explicit charset, a client that
    doesn't default JSON to UTF-8 on its own is free to guess wrong. Observed
    directly on iPadOS Safari (which - unlike desktop Safari - has no manual
    encoding override to work around it), showing Korean text mangled while
    curl/desktop browsers rendered the identical bytes fine."""

    media_type = "application/json; charset=utf-8"


app = FastAPI(title="AI Inhouse Balancer API", default_response_class=UTF8JSONResponse)

# CORS_ALLOWED_ORIGINS is a comma-separated list (e.g. the deployed
# Next.js frontend's origin); "*" during local dev only - tighten this
# before going live since credentials (X-Actor-Name) travel on every call.
_allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(servers.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(matches.router)
app.include_router(votes.router)
app.include_router(stats.router)
app.include_router(ocr.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

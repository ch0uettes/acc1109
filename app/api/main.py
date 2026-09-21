from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routers import matches, ocr, players, servers, stats, teams, votes
from app.database.base import init_db

app = FastAPI(title="AI Inhouse Balancer API")

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

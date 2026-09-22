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


@app.get("/debug/encoding")
def debug_encoding() -> dict:
    """Temporary diagnostic for the Vercel Korean-text-garbling issue -
    pinpoints whether the corruption is already baked into the Python
    string psycopg2 hands back (DB/driver-side) or introduced later
    (JSON serialization/response encoding). Remove once resolved."""
    import locale
    import os

    from sqlalchemy import text

    from app.database.base import engine

    with engine.connect() as conn:
        client_encoding = conn.execute(text("SHOW client_encoding")).scalar()
        name = conn.execute(text("SELECT name FROM servers WHERE id = 1")).scalar()

    return {
        "locale_preferred_encoding": locale.getpreferredencoding(False),
        "sys_default_encoding": __import__("sys").getdefaultencoding(),
        "env_LANG": os.environ.get("LANG"),
        "env_LC_ALL": os.environ.get("LC_ALL"),
        "env_PYTHONIOENCODING": os.environ.get("PYTHONIOENCODING"),
        "db_client_encoding": client_encoding,
        "raw_name_repr": repr(name),
        "raw_name_hex": name.encode("utf-8", errors="surrogateescape").hex() if name else None,
    }

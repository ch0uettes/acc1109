from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _build_engine():
    # pool_pre_ping: a serverless function's warm container can sit idle
    # between invocations long enough for Postgres (or Supabase's pooler)
    # to have already closed the connection server-side - without this,
    # the first query on a reused-but-stale connection raises "server
    # closed the connection unexpectedly" instead of transparently
    # reconnecting. Cheap enough to always enable, including local SQLite.
    if settings.database_url.startswith("sqlite"):
        return create_engine(settings.database_url, echo=False, pool_pre_ping=True)

    # Postgres/serverless path: one request is handled per warm instance
    # at a time, and Supabase's own connection pooler (pgbouncer - use its
    # "Transaction" pooler connection string, port 6543, as DATABASE_URL
    # when deployed to Vercel) already pools upstream, so a large app-side
    # pool here would just hold idle connections the pooler has to account
    # for on top of its own. pool_recycle keeps connections from outliving
    # the pooler's own idle-connection timeout.
    return create_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_recycle=280,
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app.database import entities  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(engine)

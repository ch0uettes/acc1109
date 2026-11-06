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
        # Without this, psycopg2 falls back to negotiating client_encoding
        # from the runtime's locale - Vercel's Python container doesn't set
        # one the same way local dev does, and was observed decoding
        # correctly-stored UTF-8 Korean text as CP949 instead (real data
        # came back as garbage, e.g. "기본 서버" -> "湲곕낯 ..."). Forcing
        # UTF8 here makes the client_encoding explicit instead of
        # environment-dependent.
        connect_args={"client_encoding": "utf8"},
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app.database import entities  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(engine)
    add_missing_columns(engine)


def add_missing_columns(bind) -> list[str]:
    """create_all() creates missing tables but never alters existing ones,
    so a nullable column added to a model would be missing from the live
    database. Add those - additive only: no column is changed or dropped,
    and existing rows just get NULL. Returns "table.column" for each one
    added. Safe to run on every cold start, including several at once."""
    from sqlalchemy import inspect, text

    preparer = bind.dialect.identifier_preparer
    existing_tables = set(inspect(bind).get_table_names())
    added: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {c["name"] for c in inspect(bind).get_columns(table.name)}
        for column in table.columns:
            if column.name in present or not column.nullable:
                continue
            ddl = (
                f"ALTER TABLE {preparer.quote(table.name)} "
                f"ADD COLUMN {preparer.quote(column.name)} {column.type.compile(dialect=bind.dialect)}"
            )
            try:
                with bind.begin() as conn:
                    conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")
            except Exception:
                # Another instance starting at the same moment may have
                # added it first; anything else is a real failure.
                if column.name not in {c["name"] for c in inspect(bind).get_columns(table.name)}:
                    raise
    return added

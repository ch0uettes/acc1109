"""One-off data migration: copies every row from the local SQLite database
(data/app.db) into a target Postgres database, preserving IDs - for moving
this app's real data (players, Seed Rating audit trail, match history, ...)
from local dev into a persistent hosted DB before deploying to Streamlit
Community Cloud (whose local filesystem is wiped on every redeploy - see
DEPLOY.md). Run once, locally, against your real data/app.db:

    python scripts/migrate_sqlite_to_postgres.py "postgresql://user:pass@host/db"

Only safe against an EMPTY target database - this does not upsert; running
it twice against the same target will fail on duplicate primary keys.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import entities  # noqa: E402,F401  registers tables on Base.metadata
from app.database.base import Base  # noqa: E402

# Parent-before-child, respecting every ForeignKey in app/database/entities/.
TABLE_ORDER = [
    "servers",
    "players",
    "server_memberships",
    "matches",
    "match_players",
    "teams",
    "team_players",
    "votes",
    "rating_histories",
    "player_season_ranks",
    "seed_rating_changes",
    "role_changes",
]


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/migrate_sqlite_to_postgres.py <postgres-url>")
        sys.exit(1)
    target_url = sys.argv[1]

    print(f"Source: {settings.database_url}")
    print(f"Target: {target_url}")

    source_engine = create_engine(settings.database_url)
    target_engine = create_engine(target_url)
    Base.metadata.create_all(target_engine)

    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    with SourceSession() as src, TargetSession() as dst:
        for table_name in TABLE_ORDER:
            table = Base.metadata.tables[table_name]
            rows = src.execute(select(table)).mappings().all()
            if not rows:
                print(f"  {table_name}: 0 rows")
                continue
            dst.execute(table.insert(), [dict(row) for row in rows])
            print(f"  {table_name}: {len(rows)} rows copied")
        dst.commit()

        # Postgres sequences don't auto-advance when ids are inserted
        # explicitly (as above) - bump each to max(id) so future
        # auto-increment inserts don't collide with the copied rows.
        for table_name in TABLE_ORDER:
            table = Base.metadata.tables[table_name]
            if "id" not in table.c:
                continue
            dst.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
                )
            )
        dst.commit()

    print("Done.")


if __name__ == "__main__":
    main()

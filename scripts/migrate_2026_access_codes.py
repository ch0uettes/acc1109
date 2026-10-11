"""One-off migration: adds servers.join_code_hash and
server_memberships.pin_hash (both nullable) to an EXISTING database, for
the server entry code / admin PIN login (see app/auth.py).
Base.metadata.create_all() only provisions these for brand-new tables.
Uses SQLAlchemy's dialect-agnostic engine (same approach as
migrate_2026_vote_uniqueness.py) so it works against both local SQLite and
a real Postgres deployment:

    python scripts/migrate_2026_access_codes.py                  # local (settings.database_url)
    python scripts/migrate_2026_access_codes.py "<DATABASE_URL>" # explicit target, e.g. Supabase

Safe to re-run: each column is only added if missing. Existing servers
start with no entry code and existing admins with no PIN - the Owner
should log in right after deploying to claim their PIN, then set an entry
code on the 서버 관리 page.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.config import settings  # noqa: E402

COLUMNS = (
    ("servers", "join_code_hash"),
    ("server_memberships", "pin_hash"),
)


def main() -> None:
    database_url = sys.argv[1] if len(sys.argv) > 1 else settings.database_url
    print(f"Migrating {database_url}")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, column in COLUMNS:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column in existing:
                print(f"  skip {table}.{column} (already present)")
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR NULL"))
            print(f"  added {table}.{column}")

    print("Done.")


if __name__ == "__main__":
    main()

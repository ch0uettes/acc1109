"""One-off migration: adds a unique index on votes(match_id, voter_player_id)
to an EXISTING votes table, enforcing "one vote per voter per match" at the
database level (previously nothing stopped a double-submit from recording
two rows). Base.metadata.create_all() (app/database/base.py:init_db()) only
provisions this for a brand-new table via VoteEntity's own
UniqueConstraint - it never adds a constraint to a table that already
exists, which is what this script is for. Uses SQLAlchemy's
dialect-agnostic engine (same approach as migrate_2026_v1_schema.py) so it
works against both local SQLite and a real Postgres deployment:

    python scripts/migrate_2026_vote_uniqueness.py                # local (settings.database_url)
    python scripts/migrate_2026_vote_uniqueness.py "<DATABASE_URL>" # explicit target, e.g. Supabase

Safe to re-run (CREATE UNIQUE INDEX IF NOT EXISTS). If duplicate
(match_id, voter_player_id) rows already exist from before this fix, the
index creation fails loudly instead of silently leaving the old data
unprotected - resolve those duplicates by hand (keep the earliest vote,
delete the rest) and re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402

INDEX_NAME = "uq_vote_match_voter"


def main() -> None:
    database_url = sys.argv[1] if len(sys.argv) > 1 else settings.database_url
    print(f"Migrating {database_url}")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        conn.execute(
            text(f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} ON votes (match_id, voter_player_id)")
        )
        print(f"  ensured unique index {INDEX_NAME} on votes(match_id, voter_player_id)")

    print("Done.")


if __name__ == "__main__":
    main()

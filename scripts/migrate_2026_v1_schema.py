"""One-off migration for the v1.0 architecture work: adds nullable columns
to tables that already have production rows (servers, decision_logs).
Brand-new tables (internal_rating_changes, ...) need no migration - see
app/database/base.py:init_db(), which calls Base.metadata.create_all() on
every app start and provisions any missing table automatically; it just
never adds *columns* to an *existing* table, which is what this script is
for.

Unlike the two prior migration scripts (migrate_2026_balance_config.py,
migrate_2026_position_roles.py), which hardcode sqlite3.connect(...) +
PRAGMA table_info and have only ever run against local SQLite, this one
uses SQLAlchemy's dialect-agnostic engine/inspector so it works against
both local SQLite and the real Supabase Postgres deployment:

    python scripts/migrate_2026_v1_schema.py                # local (settings.database_url)
    python scripts/migrate_2026_v1_schema.py "<DATABASE_URL>" # explicit target, e.g. Supabase

Safe to re-run: each column add is guarded by an inspector column check,
so a partially-applied prior run doesn't crash a retry.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.config import settings  # noqa: E402

# (table, column, SQL type) - SQL types here are plain TEXT/REAL/INTEGER,
# valid across both SQLite and Postgres for a simple nullable ADD COLUMN.
# JSON-mapped columns (player_snapshot/search_statistics/version_metadata)
# use TEXT, not a native JSON type - same choice migrate_2026_balance_config.py
# made for normalization_config/hard_constraint_config: SQLAlchemy's JSON
# type serializes/deserializes in Python regardless of the underlying
# column type, so TEXT round-trips correctly on both SQLite and Postgres.
NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("servers", "current_season_label", "TEXT"),
    ("servers", "constraint_priorities", "TEXT"),
    ("decision_logs", "execution_id", "TEXT"),
    ("decision_logs", "search_policy_name", "TEXT"),
    ("decision_logs", "player_snapshot", "TEXT"),
    ("decision_logs", "search_statistics", "TEXT"),
    ("decision_logs", "version_metadata", "TEXT"),
    ("decision_logs", "execution_time_seconds", "REAL"),
    ("decision_logs", "candidate_count", "INTEGER"),
    ("players", "is_active", "BOOLEAN"),
    ("players", "peak_achieved_season", "TEXT"),
]


def main() -> None:
    database_url = sys.argv[1] if len(sys.argv) > 1 else settings.database_url
    print(f"Migrating {database_url}")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, column, coltype in NEW_COLUMNS:
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype} NULL"))
                print(f"  added {table}.{column}")
            else:
                print(f"  skip add {table}.{column} (already present)")

    print("Done.")


if __name__ == "__main__":
    main()

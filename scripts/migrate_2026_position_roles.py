"""One-off migration: players.position -> main_role, plus new nullable
sub_role/recommended_* columns, for the Position-Aware Multi-Objective Team
Balancer refactor. Run once against data/app.db:

    python scripts/migrate_2026_position_roles.py

Safe to re-run: each statement is guarded so a partially-applied prior run
doesn't crash a retry.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402


def _column_names(cur: sqlite3.Cursor, table: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def main() -> None:
    db_path = settings.data_dir / "app.db"
    print(f"Migrating {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    columns = _column_names(cur, "players")

    if "position" in columns and "main_role" not in columns:
        cur.execute("ALTER TABLE players RENAME COLUMN position TO main_role")
        print("  renamed players.position -> main_role")
    else:
        print("  skip rename (already applied or already absent)")

    columns = _column_names(cur, "players")
    for column, coltype in [
        ("sub_role", "TEXT"),
        ("recommended_main_role", "TEXT"),
        ("recommended_main_confidence", "REAL"),
        ("recommended_sub_role", "TEXT"),
        ("recommended_sub_confidence", "REAL"),
    ]:
        if column not in columns:
            cur.execute(f"ALTER TABLE players ADD COLUMN {column} {coltype} NULL")
            print(f"  added players.{column}")
        else:
            print(f"  skip add {column} (already present)")

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()

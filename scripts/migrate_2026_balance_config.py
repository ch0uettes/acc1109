"""One-off migration: adds nullable normalization_config/hard_constraint_config
JSON columns to servers, so each server can override the Balance Evaluator's
Feature Normalizer thresholds and Hard Constraint thresholds (see
app/balance/config.py) instead of always using the code-level defaults. Run
once against data/app.db:

    python scripts/migrate_2026_balance_config.py

Safe to re-run: each statement is guarded so a partially-applied prior run
doesn't crash a retry. NULL means "use DEFAULT_NORMALIZATION_CONFIG /
DEFAULT_HARD_CONSTRAINT_CONFIG" - existing servers stay on defaults until an
Owner explicitly saves an override via the 서버 관리 page.
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

    columns = _column_names(cur, "servers")
    for column in ("normalization_config", "hard_constraint_config"):
        if column not in columns:
            cur.execute(f"ALTER TABLE servers ADD COLUMN {column} TEXT NULL")
            print(f"  added servers.{column}")
        else:
            print(f"  skip add {column} (already present)")

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()

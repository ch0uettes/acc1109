"""Clears one member's admin PIN directly in the DB - the escape hatch for
an Owner who forgot their own PIN (the 서버 관리 page's PIN reset needs a
logged-in Owner, so it can't help here). Their next admin login sets a
new PIN, so log in right after running this.

    python scripts/reset_member_pin.py <server_id> "<display_name>"                  # local
    python scripts/reset_member_pin.py <server_id> "<display_name>" "<DATABASE_URL>" # e.g. Supabase
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    server_id, display_name = int(sys.argv[1]), sys.argv[2]
    database_url = sys.argv[3] if len(sys.argv) > 3 else settings.database_url
    engine = create_engine(database_url)

    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE server_memberships SET pin_hash = NULL WHERE server_id = :sid AND display_name = :name"),
            {"sid": server_id, "name": display_name},
        )
    if result.rowcount == 0:
        print(f"No member '{display_name}' on server {server_id}")
        sys.exit(1)
    print(f"Cleared PIN for '{display_name}' on server {server_id} - log in now to set a new one.")


if __name__ == "__main__":
    main()

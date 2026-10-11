from __future__ import annotations

from sqlalchemy.engine import make_url

from app.config import pin_postgres_driver


def test_driverless_postgres_urls_are_pinned_to_psycopg2():
    for raw in (
        "postgresql://user:pw@aws-0-ap.pooler.supabase.com:6543/postgres",
        "postgres://user:pw@aws-0-ap.pooler.supabase.com:6543/postgres",
    ):
        pinned = pin_postgres_driver(raw)
        assert pinned.startswith("postgresql+psycopg2://")
        assert make_url(pinned).get_dialect().driver == "psycopg2"
        assert make_url(pinned).port == 6543


def test_urls_that_already_name_a_driver_or_are_not_postgres_are_untouched():
    for raw in (
        "postgresql+psycopg://user:pw@host/db",
        "postgresql+psycopg2://user:pw@host/db",
        "sqlite:///data/app.db",
    ):
        assert pin_postgres_driver(raw) == raw

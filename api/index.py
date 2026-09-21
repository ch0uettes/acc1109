"""Vercel Python Function entrypoint - Vercel's Python runtime detects the
module-level `app` ASGI instance here and serves it directly (see
https://vercel.com/docs/functions/runtimes/python). vercel.json rewrites
every /api/* request to this one function so FastAPI's own router handles
sub-path dispatch, rather than one Vercel function per endpoint file."""
from __future__ import annotations

from app.api.main import app

__all__ = ["app"]

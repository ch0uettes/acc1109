from __future__ import annotations

import sys

# Windows + a non-UTF-8 console codepage (e.g. cp949 on a Korean locale)
# can crash on a library's first Unicode console output. Reconfiguring here
# is harmless everywhere else.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from app.ui.app import run

if __name__ == "__main__":
    run()

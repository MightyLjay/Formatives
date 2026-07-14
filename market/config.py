"""Tiny, dependency-free .env loader so you don't retype ODDS_API_KEY every session.

Reads KEY=VALUE lines from a .env file in the current directory and sets them in the environment,
WITHOUT overriding anything already set (an explicit `$env:ODDS_API_KEY` still wins). No secrets are
ever printed. .env is gitignored — never commit it.
"""
from __future__ import annotations

import os


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, val)  # explicit env vars take precedence
    except OSError:
        pass  # a missing/unreadable .env is not an error — just fall back to the real environment

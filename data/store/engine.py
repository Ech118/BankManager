"""Postgres connection handling and migration runner.

Specified by docs/data-model.md "Storage".

Reads DATABASE_URL. In MODE=mock this module is never imported, so a developer
with no Postgres installed can still run the whole pipeline.

TODO(roadmap Step 1, P1): connection pool + migration runner.
"""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def connect():
    """Open a connection from DATABASE_URL.

    Raises RuntimeError when DATABASE_URL is unset, naming MODE=mock as the
    alternative, so the failure is self-explanatory.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def migrate() -> list[str]:
    """Apply pending migrations in filename order. Returns the ones applied."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")

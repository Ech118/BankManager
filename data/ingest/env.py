"""Read `.env` into the process environment.

Nothing else in the repo does this: every module reads `os.environ` directly, so
a `.env` file is inert unless something loads it. P1 needs SEC_USER_AGENT to
reach the process, hence this.

Deliberately dependency-free (no python-dotenv) and deliberately
non-overriding: a variable already set in the real environment always wins, so
`SEC_USER_AGENT=... make check-live` and CI secrets behave the way people
expect and a stale `.env` can never shadow them.

Only `KEY=value` lines are understood - no interpolation, no `export`, no
multi-line values. That covers `.env.example` and keeps the parser too small to
hide a surprise.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_loaded = False


def parse_env(text: str) -> dict[str, str]:
    """Parse `.env` text into a mapping. Blank lines and `#` comments ignored."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        # Strip one layer of matching quotes, so both KEY=a b and KEY="a b" work.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def load_env(path: str | Path | None = None, *, force: bool = False) -> None:
    """Load `.env` once per process. Existing environment variables win."""
    global _loaded
    if _loaded and not force:
        return

    env_path = Path(path) if path else _REPO_ROOT / ".env"
    if env_path.is_file():
        for key, value in parse_env(env_path.read_text(encoding="utf-8")).items():
            os.environ.setdefault(key, value)

    _loaded = True


def get(name: str, default: str | None = None) -> str | None:
    """Environment variable, loading `.env` first."""
    load_env()
    return os.environ.get(name, default)


def require(name: str, *, hint: str = "") -> str:
    """Environment variable that must be present and non-empty.

    Raises RuntimeError naming the variable and how to set it. Failing here, at
    startup, beats failing obscurely against a provider under load.
    """
    value = (get(name) or "").strip()
    if not value:
        suffix = f" {hint}" if hint else ""
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in.{suffix}"
        )
    return value

"""On-disk cache keyed by accession number.

Specified by docs/sec-pitfalls.md and docs/roadmap.md Step 5 (cost and latency).

Filings are immutable once published, so an accession number is a perfect cache
key: a cached document can never go stale. Market data is NOT immutable and is
cached only with a short TTL plus its observation timestamp.

Two reads, because there are two kinds of thing in here:

  get(key)                 immutable - a filing document. A hit is always valid.
  get_fresh(key, max_age)  mutable  - the ticker->CIK map, a submissions index.
                           A hit older than max_age is treated as a miss.

Writes are atomic (temp file then rename), so an interrupted run leaves either
the old entry or the new one, never a truncated file that would be served as if
it were real.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path

CACHE_ROOT = Path(".cache") / "edgar"
"""Gitignored. Never commit cached filings."""

DAY_SECONDS = 24 * 60 * 60

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def cache_root() -> Path:
    """Where the cache lives. BM_CACHE_DIR overrides it, which is what tests use."""
    override = os.environ.get("BM_CACHE_DIR")
    return Path(override) / "edgar" if override else CACHE_ROOT


def _path(key: str) -> Path:
    """Map a cache key to a file.

    The readable stem keeps the directory browsable while debugging; the hash
    suffix is what actually guarantees uniqueness, since sanitising can map two
    different keys onto the same stem.
    """
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    stem = _UNSAFE.sub("_", key).strip("_")[:80] or "key"
    return cache_root() / f"{stem}.{digest}"


def get(key: str) -> bytes | None:
    """Return cached bytes for `key`, or None on a miss."""
    path = _path(key)
    try:
        return path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None


def get_fresh(key: str, max_age_seconds: float) -> bytes | None:
    """Cached bytes for `key` if younger than `max_age_seconds`, else None.

    For anything that changes: the ticker->CIK map, a submissions index. An
    entry that has aged out is a miss, not an error.
    """
    path = _path(key)
    try:
        age = time.time() - path.stat().st_mtime
    except (FileNotFoundError, NotADirectoryError):
        return None
    if age > max_age_seconds:
        return None
    return get(key)


def put(key: str, payload: bytes) -> None:
    """Store `payload` under `key`. Written atomically."""
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def accession_key(accession: str, part: str) -> str:
    """Cache key for one part of one filing, e.g. ("0001234567-26-000010", "10-K.htm")."""
    return f"filing/{accession}/{part}"


def clear() -> None:
    """Remove every cached entry. For tests and for `make` cleanup, not for runtime."""
    root = cache_root()
    if not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_file():
            child.unlink()

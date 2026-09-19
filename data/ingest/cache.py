"""On-disk cache keyed by accession number.

Specified by docs/sec-pitfalls.md and docs/roadmap.md Step 5 (cost and latency).

Filings are immutable once published, so an accession number is a perfect cache
key: a cached document can never go stale. Market data is NOT immutable and is
cached only with a short TTL plus its observation timestamp.

TODO(roadmap Step 1, P1): implement; TODO(roadmap Step 5, P1): add the TTL path.
"""

from __future__ import annotations

from pathlib import Path

CACHE_ROOT = Path(".cache") / "edgar"
"""Gitignored. Never commit cached filings."""


def get(key: str) -> bytes | None:
    """Return cached bytes for `key`, or None on a miss."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def put(key: str, payload: bytes) -> None:
    """Store `payload` under `key`. Immutable once written."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def accession_key(accession: str, part: str) -> str:
    """Cache key for one part of one filing, e.g. ("0001234567-26-000010", "10-K.htm")."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")

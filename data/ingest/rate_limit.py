"""Politeness limits for the SEC and other providers.

Specified by docs/sec-pitfalls.md "SEC User-Agent and rate limits".

EDGAR requires a descriptive User-Agent with contact details and throttles
aggressively above roughly 10 requests per second. Being blocked mid-demo is a
self-inflicted outage, so every EDGAR call goes through here.

TODO(roadmap Step 1, P1): implement the token bucket and the 429 backoff.
"""

from __future__ import annotations

EDGAR_MAX_REQUESTS_PER_SECOND = 8.0
"""Deliberately under the ~10/s EDGAR tolerates."""

EDGAR_BACKOFF_SECONDS = (1.0, 2.0, 5.0, 15.0)
"""Escalating sleeps after a 429 or 503. Give up after the last one."""


class RateLimiter:
    """Token bucket shared by every client hitting one host."""

    def __init__(self, requests_per_second: float = EDGAR_MAX_REQUESTS_PER_SECOND) -> None:
        self.requests_per_second = requests_per_second
        raise NotImplementedError("TODO(roadmap Step 1, P1): token bucket")

    def acquire(self) -> None:
        """Block until a request may be sent."""
        raise NotImplementedError("TODO(roadmap Step 1, P1)")


def user_agent() -> str:
    """Build the EDGAR User-Agent from SEC_USER_AGENT.

    Raises RuntimeError when it is unset: an anonymous EDGAR client gets banned,
    and failing loudly at startup beats failing obscurely under load.
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1): read SEC_USER_AGENT, validate, return")

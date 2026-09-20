"""Politeness limits for the SEC and other providers.

Specified by docs/sec-pitfalls.md "SEC User-Agent and rate limits".

EDGAR requires a descriptive User-Agent with contact details and throttles
aggressively above roughly 10 requests per second. Being blocked mid-demo is a
self-inflicted outage, so every EDGAR call goes through here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from data.ingest.env import require

EDGAR_MAX_REQUESTS_PER_SECOND = 8.0
"""Deliberately under the ~10/s EDGAR tolerates."""

EDGAR_BACKOFF_SECONDS = (1.0, 2.0, 5.0, 15.0)
"""Escalating sleeps after a 429 or 503. Give up after the last one."""

RETRY_STATUS_CODES = frozenset({429, 503})


class RateLimiter:
    """Token bucket shared by every client hitting one host.

    A bucket rather than fixed spacing: a handful of calls may go out
    back-to-back (the common case - a few metadata fetches), but a long run
    still averages out under the cap.

    `clock` and `sleep` are injectable so tests can prove the pacing without
    spending real seconds doing it.
    """

    def __init__(
        self,
        requests_per_second: float = EDGAR_MAX_REQUESTS_PER_SECOND,
        *,
        burst: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.requests_per_second = requests_per_second
        self.capacity = burst if burst is not None else max(1.0, requests_per_second)
        self._tokens = self.capacity
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.requests_per_second)
        self._updated = now

    def acquire(self) -> None:
        """Block until a request may be sent.

        The lock is held across the sleep on purpose: waiters are served in
        arrival order, so one thread cannot starve behind a burst of others.
        """
        with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                self._sleep((1.0 - self._tokens) / self.requests_per_second)


def user_agent() -> str:
    """Build the EDGAR User-Agent from SEC_USER_AGENT.

    Raises RuntimeError when it is unset: an anonymous EDGAR client gets banned,
    and failing loudly at startup beats failing obscurely under load.

    SEC asks for contact details, so a value with no "@" in it is rejected too -
    it would be accepted by our code and then quietly throttled by theirs.
    """
    value = require(
        "SEC_USER_AGENT",
        hint='Example: SEC_USER_AGENT="BankManager Research you@example.com"',
    )
    if "@" not in value:
        raise RuntimeError(
            "SEC_USER_AGENT must include contact details, e.g. "
            '"BankManager Research you@example.com". SEC throttles or blocks '
            f"clients without them; got {value!r}."
        )
    return value


def backoff_delays() -> tuple[float, ...]:
    """The escalating retry schedule, as a tuple you can iterate."""
    return EDGAR_BACKOFF_SECONDS

"""Step 2: the EDGAR ingestion layer, against recorded responses.

Nothing here touches the network. Every HTTP test installs an httpx client over
a MockTransport that replays a recorded payload, so the suite runs offline and
deterministically - and so a test failure means our code changed, not that SEC
was slow today.
"""

from __future__ import annotations

import json

import httpx
import pytest

from data.ingest import cache, edgar_client, env
from data.ingest.rate_limit import RateLimiter, user_agent

# --------------------------------------------------------------------------
# Recorded payloads, trimmed to the fields we actually read.
# --------------------------------------------------------------------------
COMPANY_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 19617, "ticker": "JPM", "title": "JPMORGAN CHASE & CO"},
    "2": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
}

SUBMISSIONS = {
    "cik": "320193",
    "name": "Apple Inc.",
    "sic": "3571",
    "sicDescription": "Electronic Computers",
    "fiscalYearEnd": "0927",
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-24-000123",
                "0000320193-24-000081",
                "0000320193-23-000106",
            ],
            "filingDate": ["2024-11-01", "2024-08-02", "2023-11-03"],
            "reportDate": ["2024-09-28", "2024-06-29", "2023-09-30"],
            "form": ["10-K", "10-Q", "10-K"],
            "primaryDocument": ["aapl-20240928.htm", "aapl-20240629.htm", "aapl-20230930.htm"],
            "isXBRL": [1, 1, 1],
        }
    },
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test gets its own cache dir and a valid User-Agent."""
    monkeypatch.setenv("BM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("SEC_USER_AGENT", "BankManager Test test@example.com")
    monkeypatch.setattr(env, "_loaded", True)  # don't read the real .env
    edgar_client.set_client(None)
    yield
    edgar_client.set_client(None)


def install(handler):
    """Point the EDGAR client at a MockTransport running `handler`."""
    edgar_client.set_client(
        httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.invalid")
    )


def json_handler(payload, *, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        return httpx.Response(200, json=payload)

    return handler


# --------------------------------------------------------------------------
# .env loading
# --------------------------------------------------------------------------
def test_parse_env_handles_comments_blanks_and_quotes():
    parsed = env.parse_env(
        '# a comment\n\nSEC_USER_AGENT="Name me@example.com"\nMODE=mock\nBAD LINE\n'
    )
    assert parsed["SEC_USER_AGENT"] == "Name me@example.com"
    assert parsed["MODE"] == "mock"
    assert "BAD LINE" not in parsed


def test_real_environment_wins_over_dotenv(tmp_path, monkeypatch):
    """A stale .env must never shadow a variable the caller actually exported."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("SEC_USER_AGENT=from-dotenv\n")
    monkeypatch.setenv("SEC_USER_AGENT", "from-shell")
    monkeypatch.setattr(env, "_loaded", False)
    env.load_env(dotenv, force=True)
    assert env.get("SEC_USER_AGENT") == "from-shell"


# --------------------------------------------------------------------------
# User-Agent
# --------------------------------------------------------------------------
def test_user_agent_returns_the_configured_value():
    assert "@" in user_agent()


def test_user_agent_raises_when_unset(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        user_agent()


def test_user_agent_rejects_a_value_without_contact_details(monkeypatch):
    """SEC would accept the request and then throttle us. Fail here instead."""
    monkeypatch.setenv("SEC_USER_AGENT", "BankManager")
    with pytest.raises(RuntimeError, match="contact details"):
        user_agent()


# --------------------------------------------------------------------------
# Rate limiter
# --------------------------------------------------------------------------
def test_rate_limiter_allows_a_burst_up_to_capacity():
    now, slept = [0.0], []
    limiter = RateLimiter(8.0, clock=lambda: now[0], sleep=lambda s: slept.append(s))
    for _ in range(8):
        limiter.acquire()
    assert slept == [], "a full bucket should not sleep"


def test_rate_limiter_throttles_once_the_bucket_is_empty():
    now, slept = [0.0], []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds  # a real sleep advances the clock; the fake must too

    limiter = RateLimiter(8.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(12):
        limiter.acquire()

    assert slept, "expected throttling past the burst"
    assert sum(slept) == pytest.approx(4 / 8.0, abs=1e-6)


def test_rate_limiter_stays_under_the_configured_rate():
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    limiter = RateLimiter(8.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(80):
        limiter.acquire()

    # 80 requests, 8/s, minus the initial full bucket -> at least 9 seconds.
    assert now[0] >= (80 - 8) / 8.0 - 1e-6


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------
def test_cache_round_trip():
    assert cache.get("missing") is None
    cache.put("k", b"payload")
    assert cache.get("k") == b"payload"


def test_cache_keys_do_not_collide_after_sanitising():
    """'a/b' and 'a:b' sanitise to the same stem; the hash must keep them apart."""
    cache.put("a/b", b"first")
    cache.put("a:b", b"second")
    assert cache.get("a/b") == b"first"
    assert cache.get("a:b") == b"second"


def test_get_fresh_treats_an_aged_entry_as_a_miss():
    cache.put("k", b"payload")
    assert cache.get_fresh("k", 60) == b"payload"
    assert cache.get_fresh("k", -1) is None, "an expired entry is a miss"
    assert cache.get("k") == b"payload", "immutable read ignores age"


def test_accession_key_is_stable():
    assert cache.accession_key("0000320193-24-000123", "aapl.htm") == (
        "filing/0000320193-24-000123/aapl.htm"
    )


# --------------------------------------------------------------------------
# Ticker normalisation and CIK lookup
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [("aapl", "AAPL"), ("BRK.B", "BRK-B"), ("BRK-B", "BRK-B"), ("brk/b", "BRK-B"), (" msft ", "MSFT")],
)
def test_normalize_ticker(raw, expected):
    assert edgar_client.normalize_ticker(raw) == expected


def test_lookup_cik_zero_pads():
    install(json_handler(COMPANY_TICKERS))
    assert edgar_client.lookup_cik("AAPL") == "0000320193"
    assert edgar_client.lookup_cik("JPM") == "0000019617"


def test_lookup_cik_accepts_either_share_class_spelling():
    install(json_handler(COMPANY_TICKERS))
    assert edgar_client.lookup_cik("BRK.B") == edgar_client.lookup_cik("BRK-B")


def test_lookup_cik_raises_a_readable_keyerror_for_an_unknown_ticker():
    install(json_handler(COMPANY_TICKERS))
    with pytest.raises(KeyError, match="company_tickers"):
        edgar_client.lookup_cik("NOTREAL")


def test_ticker_map_is_cached_between_calls():
    calls = []
    install(json_handler(COMPANY_TICKERS, calls=calls))
    edgar_client.lookup_cik("AAPL")
    edgar_client.lookup_cik("JPM")
    assert len(calls) == 1, f"expected one fetch, made {len(calls)}"


# --------------------------------------------------------------------------
# Submissions and filings
# --------------------------------------------------------------------------
def test_list_filings_is_newest_first():
    install(json_handler(SUBMISSIONS))
    filings = edgar_client.list_filings("0000320193")
    assert [f["filed_at"] for f in filings] == ["2024-11-01", "2024-08-02", "2023-11-03"]


def test_list_filings_filters_by_form():
    install(json_handler(SUBMISSIONS))
    filings = edgar_client.list_filings("0000320193", forms=["10-K"])
    assert [f["form"] for f in filings] == ["10-K", "10-K"]


def test_list_filings_excludes_anything_filed_after_as_of():
    """A 10-K for FY2024 filed in Nov 2024 is invisible to a mid-2024 run."""
    install(json_handler(SUBMISSIONS))
    filings = edgar_client.list_filings("0000320193", as_of="2024-09-01")
    assert [f["filed_at"] for f in filings] == ["2024-08-02", "2023-11-03"]
    assert all(f["filed_at"] <= "2024-09-01" for f in filings)


def test_list_filings_carries_the_fields_downstream_needs():
    install(json_handler(SUBMISSIONS))
    newest = edgar_client.list_filings("0000320193")[0]
    assert newest["accession"] == "0000320193-24-000123"
    assert newest["period_end"] == "2024-09-28"
    assert newest["primary_document"] == "aapl-20240928.htm"
    assert newest["is_xbrl"] is True


# --------------------------------------------------------------------------
# Retry behaviour
# --------------------------------------------------------------------------
def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(edgar_client.time, "sleep", lambda s: None)
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429)
        return httpx.Response(200, json=COMPANY_TICKERS)

    install(handler)
    assert edgar_client.lookup_cik("AAPL") == "0000320193"
    assert len(attempts) == 3


def test_gives_up_after_the_backoff_schedule(monkeypatch):
    monkeypatch.setattr(edgar_client.time, "sleep", lambda s: None)
    install(lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        edgar_client.lookup_cik("AAPL")


def test_does_not_retry_a_404(monkeypatch):
    """Retrying a 404 just burns the rate-limit budget."""
    monkeypatch.setattr(edgar_client.time, "sleep", lambda s: None)
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(404)

    install(handler)
    with pytest.raises(httpx.HTTPStatusError):
        edgar_client.lookup_cik("AAPL")
    assert len(attempts) == 1


def test_documents_are_cached_forever():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=b"<html>10-K</html>")

    install(handler)
    first = edgar_client.fetch_document("320193", "0000320193-24-000123", "aapl.htm")
    second = edgar_client.fetch_document("320193", "0000320193-24-000123", "aapl.htm")
    assert first == second == b"<html>10-K</html>"
    assert len(calls) == 1, "an immutable filing must not be fetched twice"


def test_submissions_are_parsed_as_json():
    install(json_handler(SUBMISSIONS))
    submissions = edgar_client.fetch_submissions("320193")
    assert submissions["sic"] == "3571"
    assert submissions["fiscalYearEnd"] == "0927"


def test_cache_survives_a_new_client():
    """The cache is on disk, so a fresh client still gets a hit."""
    calls = []
    install(json_handler(SUBMISSIONS, calls=calls))
    edgar_client.fetch_submissions("320193")
    install(json_handler(SUBMISSIONS, calls=calls))
    edgar_client.fetch_submissions("320193")
    assert len(calls) == 1


def test_cached_payload_is_valid_json_on_disk():
    install(json_handler(SUBMISSIONS))
    edgar_client.fetch_submissions("320193")
    raw = cache.get_fresh("sec/submissions/0000320193.json", 60)
    assert raw is not None
    assert json.loads(raw)["cik"] == "320193"

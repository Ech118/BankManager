"""Recent news, for post-earnings developments.

Specified by docs/data-model.md "News" and docs/verification.md (injection).

News text is the LEAST trusted input in the system: it is arbitrary third-party
prose fed to an LLM. It is returned as data, wrapped as quoted content by the
MCP layer, and agents are instructed never to follow instructions found in it.

`as_of` BOUNDS THE WINDOW FROM ABOVE AS WELL AS BELOW
    The lower bound is the obvious one. The upper bound is the one that makes a
    backtest a backtest: a run dated June 2025 that reads September 2025
    headlines has been told the answer. The provider is asked for a bounded
    range AND the results are filtered again on the way back, because a provider
    that ignores its own `to` parameter would otherwise leak the future
    silently. Belt and braces is cheap here; the failure is not.

A PROVIDER OUTAGE IS AN EMPTY LIST AND A GAP, NEVER AN EXCEPTION
    An agent that gets no news reasons about a company with no recent news,
    which is wrong but visible. An agent that gets an exception aborts a run.
    And a failed fetch must never fall through to an agent inventing a headline
    (docs/mcp-tools.md, error conventions).

EVERY ITEM CARRIES A SOURCE, AND ITEMS WITHOUT A USABLE ONE ARE DROPPED
    `NewsItem` requires an absolute URL and a `source_id` that resolves in the
    factsheet's registry. A headline with no link cannot be checked by anyone,
    so it is not worth the risk of an agent citing it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field

from schema.contracts.common import ISODate, SourceRef, Ticker
from schema.contracts.market import NewsItem

NEWS_SOURCE_PREFIX = "src:news"

MAX_SNIPPET_CHARS = 500
"""Enough to judge relevance, short enough that twenty of them do not dominate
an agent's context. The full article is behind the url."""


@dataclass
class NewsResult:
    news: list[NewsItem] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    sources: dict[str, SourceRef] = field(default_factory=dict)


def window(as_of: ISODate, lookback_days: int) -> tuple[ISODate, ISODate]:
    """[as_of - lookback_days, as_of]. Both bounds inclusive."""
    end = dt.date.fromisoformat(as_of)
    start = end - dt.timedelta(days=lookback_days)
    return start.isoformat(), end.isoformat()


def _date_of(item: dict) -> ISODate | None:
    """Finnhub dates a story with a unix timestamp in `datetime`."""
    stamp = item.get("datetime")
    if not stamp:
        return None
    try:
        return dt.datetime.fromtimestamp(int(stamp), dt.UTC).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def source_id_for(ticker: Ticker, url: str, date: ISODate) -> str:
    """src:news:<TICKER>:<date>:<hash of url>.

    The url is hashed rather than embedded: SourceId is a constrained pattern
    and a raw url carries slashes, colons and query strings that do not fit it.
    The hash is stable, so the same story cited twice cites one source.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{NEWS_SOURCE_PREFIX}:{ticker}:{date.replace('-', '')}:{digest}"


def normalize(
    raw: list[dict],
    *,
    ticker: Ticker,
    start: ISODate,
    end: ISODate,
    limit: int,
) -> NewsResult:
    """Provider payload -> NewsItem[], newest first, inside the window."""
    items: list[NewsItem] = []
    sources: dict[str, SourceRef] = {}
    seen: set[str] = set()

    for entry in raw:
        url = str(entry.get("url") or "").strip()
        headline = str(entry.get("headline") or "").strip()
        date = _date_of(entry)
        if not (url.startswith(("http://", "https://")) and headline and date):
            continue
        # The provider was asked for this range; filtering again means a
        # provider that ignores its own `to` cannot leak the future.
        if date < start or date > end:
            continue
        if url in seen:
            continue
        seen.add(url)

        source_id = source_id_for(ticker, url, date)
        summary = str(entry.get("summary") or "").strip()
        items.append(
            NewsItem(
                headline=headline,
                date=date,
                url=url,
                source_id=source_id,
                snippet=summary[:MAX_SNIPPET_CHARS] or None,
            )
        )
        sources[source_id] = SourceRef(
            kind="news",
            url=url,
            accession=None,
            fetched_at=f"{end}T00:00:00Z",
        )

    # Newest first; url breaks ties so two runs over the same payload agree.
    items.sort(key=lambda item: (item.date, item.url), reverse=True)
    items = items[:limit]
    kept = {item.source_id for item in items}
    return NewsResult(
        news=items, sources={k: v for k, v in sources.items() if k in kept}
    )


def search(
    ticker: Ticker, as_of: ISODate, lookback_days: int = 60, limit: int = 20
) -> NewsResult:
    """Headlines published in [as_of - lookback_days, as_of], newest first.

    The upper bound matters as much as the lower one: a backtest that sees
    tomorrow's news is not a backtest (ADR 0003).
    """
    from data.ingest import market_client

    start, end = window(as_of, lookback_days)
    try:
        raw = market_client.get_client().news(ticker, start, end)
    except Exception as exc:  # noqa: BLE001 - a provider must never abort a run
        return NewsResult(
            news=[],
            gaps=[
                f"{ticker}: the news provider could not be reached ({exc}). No "
                f"developments between {start} and {end} are available; treat the "
                "absence of news as unknown rather than as quiet."
            ],
        )

    result = normalize(raw, ticker=ticker, start=start, end=end, limit=limit)
    if not result.news:
        result.gaps.append(
            f"{ticker}: the news provider returned nothing between {start} and "
            f"{end}. Treat the absence of news as unknown rather than as quiet."
        )
    return result

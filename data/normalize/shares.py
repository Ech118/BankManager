"""Shares outstanding: the number that decides whether market cap is real.

THE TRAP
    `dei:EntityCommonStockSharesOutstanding` is the cover-page share count, and
    it is unusable for a filer with more than one share class:

      GOOGL   the tag is ABSENT from companyfacts entirely. Alphabet reports it
              per class, so every entry is dimensioned, and companyfacts serves
              only consolidated facts - the concept vanishes rather than
              arriving sliced.
      BRK-B   the tag is present and reads 941,481. That is CLASS A alone.
              Multiplied by a Class B price of ~$510 it gives a market cap of
              $480M for a company whose own cover page reports a public float
              of $903B - wrong by a factor of about 1,900.

    Finnhub does not rescue the second case: its `shareOutstanding` for BRK.B
    is 1.44 (millions), the same Class A count. Its `marketCapitalization`,
    though, is right, so dividing it by the price recovers a usable
    class-equivalent share count.

THE RULE
    Try candidates in order and keep the FIRST ONE THAT SURVIVES A SANITY
    CHECK. The check is a floor, not an equality: implied market cap must be at
    least MIN_FLOAT_COVERAGE of the company's own reported public float, since
    float is a subset of market cap (insiders are excluded from it).

    That is deterministic, needs no per-ticker knowledge, and rejects exactly
    the share counts that are missing a class.

    If every candidate fails, shares are `unavailable` plus a data_quality gap.
    A market cap built on a share count we cannot defend is worse than no
    market cap: it silently poisons EV, every multiple, and the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.normalize import concept_map, dimensions
from data.normalize.concept_map import US_GAAP
from schema.contracts.common import ISODate
from schema.contracts.enums import SourceKind

DEI = "dei"
DEI_SHARES = "EntityCommonStockSharesOutstanding"
DEI_PUBLIC_FLOAT = "EntityPublicFloat"

MIN_FLOAT_COVERAGE = 0.25
"""Implied market cap must be at least this fraction of reported public float.

Float excludes insider and affiliate holdings, so it is always LESS than market
cap - in the surveyed filers between 40% and 100% of it. A quarter leaves room
for a heavily insider-owned company while still rejecting a share count that is
short by a whole class (BRK-B's is short by ~99.95%).
"""

MAX_FLOAT_MULTIPLE = 50.0
"""And not absurdly more than float either, which catches a share count that
was multiplied instead of divided."""


@dataclass(frozen=True)
class ShareCandidate:
    """One possible share count, and where it came from."""

    value: float
    concept: str
    source_kind: SourceKind
    accession: str | None = None
    filed_at: ISODate | None = None
    source_url: str | None = None
    note: str = ""


def _latest_entry(companyfacts: dict, taxonomy: str, concept: str, as_of: ISODate | None):
    """The most recently FILED consolidated entry for a concept, at or before as_of."""
    node = (companyfacts.get("facts") or {}).get(taxonomy, {}).get(concept)
    if not node:
        return None
    best = None
    for entries in (node.get("units") or {}).values():
        for entry in entries:
            if not dimensions.is_consolidated(entry):
                continue
            filed = entry.get("filed")
            if as_of and filed and filed > as_of:
                continue
            if entry.get("val") in (None, 0):
                continue
            key = (filed or "", entry.get("end") or "")
            if best is None or key > (best.get("filed") or "", best.get("end") or ""):
                best = entry
    return best


def public_float(companyfacts: dict, as_of: ISODate | None = None) -> float | None:
    """The filer's own reported public float, in full USD."""
    entry = _latest_entry(companyfacts, DEI, DEI_PUBLIC_FLOAT, as_of)
    return float(entry["val"]) if entry else None


def passes_float_check(shares: float, price: float | None, float_value: float | None) -> bool:
    """Is a share count defensible against the filer's own public float?

    Unverifiable is not the same as wrong: with no price or no reported float
    there is nothing to check against, so the candidate is accepted. The check
    exists to REJECT a demonstrably impossible number, not to require proof.
    """
    if not shares or shares <= 0:
        return False
    if not price or not float_value or float_value <= 0:
        return True
    implied = shares * price
    return MIN_FLOAT_COVERAGE <= implied / float_value <= MAX_FLOAT_MULTIPLE


def candidates(
    companyfacts: dict,
    *,
    as_of: ISODate | None = None,
    diluted: float | None = None,
    diluted_source: dict | None = None,
    provider_shares: float | None = None,
    provider_market_cap: float | None = None,
    price: float | None = None,
) -> list[ShareCandidate]:
    """Every share count worth trying, best first.

    Filing-sourced counts come first because they are point-in-time and cited;
    the provider is a fallback, and the provider's market cap divided by price
    is the last resort that rescues a multi-class filer the others all miss.
    """
    from data.normalize import to_facts

    out: list[ShareCandidate] = []
    cik = str(companyfacts.get("cik") or "") or None

    entry = _latest_entry(companyfacts, DEI, DEI_SHARES, as_of)
    if entry:
        out.append(
            ShareCandidate(
                value=float(entry["val"]),
                concept=f"{DEI}:{DEI_SHARES}",
                source_kind=SourceKind.XBRL_REPORTED,
                accession=entry.get("accn"),
                filed_at=entry.get("filed"),
                source_url=to_facts.source_url_for(cik, entry.get("accn")),
                note="cover page share count",
            )
        )

    for concept in concept_map.candidates("shares_outstanding", US_GAAP):
        entry = _latest_entry(companyfacts, US_GAAP, concept, as_of)
        if entry:
            out.append(
                ShareCandidate(
                    value=float(entry["val"]),
                    concept=f"{US_GAAP}:{concept}",
                    source_kind=SourceKind.XBRL_REPORTED,
                    accession=entry.get("accn"),
                    filed_at=entry.get("filed"),
                    source_url=to_facts.source_url_for(cik, entry.get("accn")),
                    note="balance-sheet share count",
                )
            )
            break

    if diluted:
        source = diluted_source or {}
        out.append(
            ShareCandidate(
                value=float(diluted),
                concept=f"{US_GAAP}:WeightedAverageNumberOfDilutedSharesOutstanding",
                source_kind=SourceKind.XBRL_REPORTED,
                accession=source.get("accession"),
                filed_at=source.get("filed_at"),
                source_url=source.get("source_url"),
                note="weighted-average diluted shares; a period average, not a point count",
            )
        )

    if provider_shares:
        out.append(
            ShareCandidate(
                value=float(provider_shares),
                concept="finnhub:shareOutstanding",
                source_kind=SourceKind.MARKET_API,
                note="provider share count",
            )
        )

    if provider_market_cap and price:
        out.append(
            ShareCandidate(
                value=float(provider_market_cap) / float(price),
                concept="finnhub:marketCapitalization/price",
                source_kind=SourceKind.MARKET_API,
                note=(
                    "implied from the provider's market cap, which is the only "
                    "figure that covers every share class"
                ),
            )
        )

    return out


@dataclass
class ShareResolution:
    """The chosen share count, or the reason there is none."""

    candidate: ShareCandidate | None
    rejected: list[tuple[ShareCandidate, str]]
    float_value: float | None

    @property
    def ok(self) -> bool:
        return self.candidate is not None

    def gap(self, ticker: str) -> str | None:
        """A readable data_quality gap, or None when nothing went wrong."""
        if not self.rejected:
            return None
        detail = "; ".join(
            f"{c.concept}={c.value:,.0f} ({reason})" for c, reason in self.rejected
        )
        if self.candidate is None:
            return (
                f"{ticker}: no defensible share count. Rejected {detail}. Market cap "
                "and enterprise value are unavailable."
            )
        return (
            f"{ticker}: share count taken from {self.candidate.concept}; rejected {detail}."
        )


def resolve(
    price: float | None, float_value: float | None, options: list[ShareCandidate]
) -> ShareResolution:
    """First candidate that survives the float check wins."""
    rejected: list[tuple[ShareCandidate, str]] = []
    for option in options:
        if passes_float_check(option.value, price, float_value):
            return ShareResolution(option, rejected, float_value)
        implied = option.value * price if price else None
        reason = (
            f"implies a market cap of {implied / 1e9:,.1f}B against a reported "
            f"public float of {(float_value or 0) / 1e9:,.1f}B"
            if implied
            else "not a usable number"
        )
        rejected.append((option, reason))
    return ShareResolution(None, rejected, float_value)

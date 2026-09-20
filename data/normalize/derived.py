"""When a derived fact became knowable.

ONE RULE, APPLIED EVERYWHERE P1 DERIVES A FACT
    A derived fact's `filed_at` is the LATEST `filed_at` among the facts it was
    derived from. It is never null.

WHY THE MAXIMUM
    The value did not exist until its last input was filed. FY2025 free cash
    flow built from an operating cash flow filed 2025-10-30 and a capex filed
    2026-02-01 was not knowable on 2025-12-01, and a run dated then must not see
    it. The maximum is the first date on which every input was public, which is
    exactly when the derived number became knowable. The minimum - or inheriting
    the date of whichever input the code happened to copy from - leaks a future
    number into a past run, which is the failure ADR 0003 exists to prevent.

    It composes: a fact derived from derived facts still ends up carrying the
    date its last RAW input was filed, as long as every layer follows the rule.

WHY NOT NULL
    `FinancialFact` lets a derived fact leave `filed_at` unset, and treating
    null as "always visible, its inputs were already filtered" holds only while
    the filter and the derivation run in the same pass. It stops holding the
    moment a derived fact is cached, recorded to a fixture, or resolved with a
    different `as_of` - all three of which happen. A real date is checked by the
    same comparison as every other fact, so no consumer needs a special case.
    Raised with P3 and P2 in docs/requests/2026-09-19-p3-report-inputs-response.md.

THE ACCESSION FOLLOWS THE DATE
    A derived fact carries the accession of the input that was filed LAST, so
    `filed_at` and `accession_number` name the same filing. The alternative -
    the date from one input and the accession from another - reads as a filing
    date that the accession does not support, which is worse than carrying
    neither.
"""

from __future__ import annotations

from collections.abc import Iterable

from schema.contracts.common import ISODate
from schema.contracts.facts import FinancialFact


def last_filed(inputs: Iterable[FinancialFact | None]) -> FinancialFact | None:
    """The input filed last: the one that made the derived value knowable.

    Ties break on accession so the choice is deterministic across runs - two
    facts from the same filing have the same date, and an arbitrary winner would
    make the output depend on dict ordering.
    """
    dated = [f for f in inputs if f is not None and f.filed_at]
    if not dated:
        return None
    return max(dated, key=lambda f: (f.filed_at or "", f.accession_number or ""))


def filed_at(inputs: Iterable[FinancialFact | None]) -> ISODate | None:
    """The derived fact's `filed_at`. None only when no input carries one."""
    latest = last_filed(inputs)
    return latest.filed_at if latest else None


def provenance(inputs: Iterable[FinancialFact | None]) -> dict:
    """`filed_at` + `accession_number` + `filing_type` as a model_copy update.

    Returned as a dict so a caller can splat it into `FinancialFact(...)` or
    `fact.model_copy(update=...)` without either forgetting a field or having to
    know that the three travel together.
    """
    inputs = list(inputs)
    latest = last_filed(inputs)
    if latest is None:
        return {}
    return {
        "filed_at": latest.filed_at,
        "accession_number": latest.accession_number,
        "filing_type": latest.filing_type,
    }

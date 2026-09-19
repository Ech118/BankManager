"""Strip identifying detail from filing text before an agent sees it.

Specified by docs/roadmap.md Step 6 and docs/adr/0003.

Passed to orchestrator.run_analysis as the `redact` hook, which applies it to
ALL filing text before any agent call.

What has to go, and why each matters:
  - company name and ticker, in every form the filing uses
  - product and brand names, which identify a company as reliably as its name
  - absolute dates, rewritten to relative periods ("the most recent fiscal year")
  - distinctive round numbers that pin down a specific well-known company

Imperfect by construction: a large enough company is recognisable from its
segment mix alone. That is a reason to report the backtest honestly, not a
reason to skip the redaction.

TODO(roadmap Step 6, P2).
"""

from __future__ import annotations


def build_redactor(company_name: str, ticker: str, aliases: list[str] | None = None):
    """Return a `redact(text) -> text` closure for one company.

    The returned callable is what the orchestrator applies to filing text.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def relative_dates(text: str, as_of: str) -> str:
    """Rewrite absolute dates as relative periods.

    A fiscal year printed in the text tells the model exactly when it is, which
    undoes most of the point of anonymizing the name.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")


def leak_score(text: str, company_name: str, ticker: str) -> float:
    """Fraction of identifying tokens still present after redaction.

    Used as a test assertion, not as a guarantee: a zero score means the obvious
    identifiers are gone, not that the company is unidentifiable.
    """
    raise NotImplementedError("TODO(roadmap Step 6, P2)")

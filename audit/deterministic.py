"""The deterministic half of the verification gate. Seven checks, no LLM.

Specified by docs/verification.md and docs/adr/0005.

These run first and catch most real failures, because most real failures are
mechanical: a citation that does not resolve, a number that does not recompute,
a figure quoted from a filing that was later restated. Cheap, reproducible, and
they never hallucinate a problem.

Each check raises VerificationIssue objects carrying the section they came from,
which is what lets routing.py send a targeted retry to one agent.

TODO(roadmap Step 2, P2).
"""

from __future__ import annotations

from collections.abc import Callable

from schema.contracts.factsheet import Factsheet
from schema.contracts.state import ResearchState
from schema.contracts.verification import VerificationIssue


def check_unresolved_facts(state: ResearchState, resolve: Callable) -> list[VerificationIssue]:
    """Every cited fact_id must exist. A dangling citation is not provenance."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def check_recompute(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """Re-derive every computed number from its inputs and compare.

    Only possible because calc/ is pure and every derived value carries its
    formula and inputs (ADR 0002).
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def check_prose_numbers(state: ResearchState) -> list[VerificationIssue]:
    """Numerals in claim text must match the claim's ValueObject.

    Catches the common failure where an agent computes correctly, then rounds or
    mistypes the number in the sentence a reader actually sees.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def check_superseded_facts(state: ResearchState, resolve: Callable) -> list[VerificationIssue]:
    """No claim may cite a fact a later filing restated."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def check_future_facts(state: ResearchState, resolve: Callable) -> list[VerificationIssue]:
    """No claim may cite a fact filed after the run's as_of.

    The backtest's integrity rests on this one (error A).
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def check_adjusted_as_gaap(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """No non-GAAP figure may be presented as a GAAP one.

    "Adjusted EBITDA" and "EBITDA" are different numbers; using them
    interchangeably flatters every multiple built on top.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def check_cross_agent_contradictions(state: ResearchState) -> list[VerificationIssue]:
    """No two sections may assert incompatible things.

    Agents run in parallel and cannot see each other, so this is where the
    valuation section calling the moat durable while the business section calls
    it eroding gets caught.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P2)")


def run_all(
    state: ResearchState, factsheet: Factsheet, resolve: Callable
) -> list[VerificationIssue]:
    """Run all seven deterministic checks."""
    raise NotImplementedError("TODO(roadmap Step 2, P2)")

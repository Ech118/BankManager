"""Render a ResearchState into a Verdict. Pure, deterministic, no LLM.

Specified by docs/research-state.md and docs/adr/0004.

Rules:
  - Body markdown is built from a section's Claims, in order. Nothing is
    paraphrased or rewritten here.
  - Unverified claims are RENDERED AND MARKED, never dropped. A claim that
    quietly vanished would leave a reader unable to tell a checked report from
    an unchecked one.
  - Every number is formatted from its ValueObject, with its type
    (fact / estimate / assumption) carried through so the UI can colour it.
  - The disclaimer is non-negotiable and appears on every page (error M).
  - The verdict card is rendered FIRST, before any section.

TODO(roadmap Step 2, P3): minimal report.
TODO(roadmap Step 5, P3): full fifteen-section render.
"""

from __future__ import annotations

from schema.contracts.state import ResearchSection, ResearchState
from schema.contracts.verdict import ReportSection, Verdict, VerdictCard

DISCLAIMER = (
    "This is AI-generated research for educational purposes only. It is not "
    "investment advice or a recommendation to buy or sell any security."
)
"""Rendered on every page. A test asserts its presence (error M)."""


def format_value(value: dict) -> str:
    """Format one ValueObject for display.

    `unavailable` renders as "unavailable", never as 0 or a blank - the reader
    must be able to tell a missing number from a zero one.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P3)")


def render_section(section: ResearchSection) -> ReportSection:
    """One section's markdown, built from its Claims.

    Unverified claims are included with a visible marker.
    """
    raise NotImplementedError("TODO(roadmap Step 2, P3)")


def render_card(state: ResearchState) -> VerdictCard:
    """The verdict card. Every number comes from ScenarioResult or Metrics."""
    raise NotImplementedError("TODO(roadmap Step 2, P3)")


def render(state: ResearchState) -> Verdict:
    """The whole report. A pure function of the state."""
    raise NotImplementedError("TODO(roadmap Step 2, P3)")

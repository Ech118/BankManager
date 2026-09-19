"""P2 (Calc, Audit & Eval) owns this file. Public interface of the verifier.

Step 0 STUB: returns the ACME audit fixture. The owner replaces the internals
but MUST NOT change the signature (CONTRACT-CHANGE PR, CONTRIBUTING.md).

BOUNDARY (docs/adr/0007): audit/ reads a ResearchState and a Factsheet, and
nothing else. Both of its external needs are INJECTED as callables:
  - `get_text`     data.api.get_section_text, so audit never imports data/,
  - `verify_claim` an LLM callable, so audit depends on no model SDK.

The gate is mostly deterministic (ADR 0005). Only UNSUPPORTED_CLAIM needs an
LLM; keeping that list short is what keeps the gate cheap and reproducible.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

_MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock"


def run_audit(
    state: dict,
    factsheet: dict,
    get_text: Callable[[str], str],
    verify_claim: Callable[[str, str], bool] | None = None,
) -> dict:
    """Return a VerificationResult (schema/audit.json).

    The REAL implementation runs, in order:
      DETERMINISTIC (docs/verification.md)
        unresolved_fact            every cited fact_id resolves
        recompute_mismatch         every derived number recomputes from its inputs
        prose_number_mismatch      numerals in claim text match their ValueObject
        superseded_fact            no claim cites a restated fact
        future_fact                no claim cites a fact filed after state.as_of
        adjusted_as_gaap           no non-GAAP figure presented as GAAP
        cross_agent_contradiction  no two sections assert incompatible things
      LLM (only this one)
        unsupported_claim          each qualitative claim's quote really appears
                                   in get_text(source_id); verify_claim judges
                                   paraphrase only when the string match fails

    Every issue carries the section it came from, so the orchestrator can route a
    targeted RetryDirective to that section's owning agent.

    Takes no `as_of`: `state["as_of"]` and `factsheet["as_of"]` are authoritative.
    """
    if os.environ.get("MODE", os.environ.get("BM_MODE", "mock")).lower() == "live":
        raise NotImplementedError(
            "audit.api.run_audit: live mode is not implemented yet (P2, roadmap Step 2). "
            "Use MODE=mock."
        )
    return json.loads((_MOCK / "audit.json").read_text(encoding="utf-8"))

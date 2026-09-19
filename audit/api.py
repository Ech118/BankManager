"""P2 (Calc, Audit & Eval) owns this file. Public interface of the auditor.

Step 0 STUB: returns the ACME audit fixture. The owner replaces the internals
but MUST NOT change the signature (plan.txt 15.11).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

_MOCK = Path(__file__).resolve().parents[1] / "fixtures" / "mock"


def run_audit(factsheet: dict, metrics: dict, analyses: list[dict], verdict: dict,
              get_text: Callable[[str], str]) -> dict:
    """Return audit.json.

    REAL implementation checks: (a) every number in the verdict traces to
    factsheet/metrics/scenario_result; (b) every evidence quote appears
    verbatim (whitespace-normalised) in get_text(source_id) (error I);
    (c) disclaimer present (M); (d) consistency. get_text is
    data.api.get_section_text passed in by the orchestrator, so audit never
    imports data/.
    """
    if os.environ.get("BM_MODE", "mock").lower() == "live":
        raise NotImplementedError("audit.api.run_audit: live mode is not implemented yet (P2). Use BM_MODE=mock.")
    return json.loads((_MOCK / "audit.json").read_text())

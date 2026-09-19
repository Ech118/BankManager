"""P2 (Calc, Audit & Eval) owns this file. Public interface of the auditor.

Real implementation (plan.txt 15.14 P2 step 6): checks that (a) every number
in the verdict traces to factsheet/metrics/scenario_result, (b) every
evidence quote appears verbatim in its cited source text, (c) the disclaimer
is present, (d) the verdict is internally consistent. get_text is
data.api.get_section_text, passed in by the orchestrator, so audit never
imports data/ (plan.txt 15.8). Signature MUST NOT change (plan.txt 15.11).
"""
from __future__ import annotations

from typing import Callable

from audit.checks import check_consistency, check_disclaimer, check_evidence_quotes, check_numbers_trace


def run_audit(factsheet: dict, metrics: dict, analyses: list[dict], verdict: dict,
              get_text: Callable[[str], str]) -> dict:
    """Return audit.json (schema/audit.json). passed is False if any issue has
    severity 'error'."""
    issues: list[dict] = []
    issues += check_numbers_trace(verdict, factsheet, metrics)
    issues += check_evidence_quotes(analyses, verdict, get_text)
    issues += check_disclaimer(verdict)
    issues += check_consistency(verdict)

    schema_version = verdict.get("schema_version") or factsheet.get("schema_version", "1.0.0")
    passed = not any(issue["severity"] == "error" for issue in issues)
    return {"schema_version": schema_version, "passed": passed, "issues": issues}

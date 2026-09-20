"""P2 (Calc, Audit & Eval) owns this file. Public interface of the verifier.

MINIMAL REAL IMPLEMENTATION (hackathon cut, 2026-09-20): one deterministic check
runs - every fact_id cited by a Claim must resolve, in the factsheet or in calc/'s
published facts. Every other claim is reported UNVERIFIED rather than verified, so
nothing carries a verification stamp it did not earn (docs/verification.md: a
hallucinating check is worse than a missing one). The remaining six deterministic
checks and the LLM check are still to come.

BOUNDARY (docs/adr/0007): audit/ reads a ResearchState and a Factsheet, and
nothing else. Both of its external needs are INJECTED as callables:
  - `get_text`     data.api.get_section_text, so audit never imports data/,
  - `verify_claim` an LLM callable, so audit depends on no model SDK.

The gate is mostly deterministic (ADR 0005). Only UNSUPPORTED_CLAIM needs an
LLM; keeping that list short is what keeps the gate cheap and reproducible.
"""

from __future__ import annotations

from collections.abc import Callable

SCHEMA_VERSION = "2.1.0"


def _fact_ids(factsheet: dict) -> set[str]:
    """Every fact_id the factsheet and calc/'s output can resolve.

    Real factsheets carry the id on each reported ValueObject's `derived_from`;
    the mock does not, so the documented convention
    `fact:<TICKER>:<metric>:<PERIOD>` is accepted too. calc/ publishes its own in
    `metrics["derived_facts"]` and `metrics["input_facts"]`.
    """
    known: set[str] = set()
    ticker = factsheet.get("ticker", "")

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for candidate in node.get("derived_from") or []:
                if isinstance(candidate, str) and candidate.startswith("fact:"):
                    known.add(candidate)
            if isinstance(node.get("fact_id"), str):
                known.add(node["fact_id"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(factsheet)
    for period in factsheet.get("financials") or []:
        label = period.get("period")
        for field, value in period.items():
            if isinstance(value, dict) and "status" in value:
                known.add(f"fact:{ticker}:{field}:{label}")
    for metrics in (factsheet.get("metrics"), factsheet.get("_calc_metrics")):
        walk(metrics)
    return known


def run_audit(
    state: dict,
    factsheet: dict,
    get_text: Callable[[str], str],
    verify_claim: Callable[[str, str], bool] | None = None,
) -> dict:
    """Return a VerificationResult (schema/audit.json).

    Runs ONE check today - `unresolved_fact`, every cited fact_id resolves - and
    marks every other claim `unverified`. The six other deterministic checks and
    the LLM check are specified in docs/verification.md and not yet built; a claim
    they would have covered is reported as unchecked rather than passed.

    Takes no `as_of`: `state["as_of"]` and `factsheet["as_of"]` are authoritative.
    """
    known = _fact_ids(factsheet)
    known |= {
        fact["fact_id"]
        for key in ("derived_facts", "input_facts")
        for fact in (state.get("metrics") or {}).get(key, []) or []
        if isinstance(fact, dict) and fact.get("fact_id")
    }

    issues: list[dict] = []
    checked = 0
    for section_key, section in (state.get("sections") or {}).items():
        for claim in (section or {}).get("claims") or []:
            checked += 1
            missing = [
                fact_id
                for fact_id in claim.get("fact_ids") or []
                if fact_id not in known
            ]
            for fact_id in missing:
                issues.append(
                    {
                        "issue_type": "unresolved_fact",
                        "severity": "error",
                        "path": f"sections.{section_key}",
                        "message": f"cited fact_id {fact_id} does not resolve",
                        "claim_id": claim.get("claim_id"),
                        "expected": "a fact_id present in the factsheet or in calc/ output",
                        "actual": fact_id,
                        "checked_by_llm": False,
                    }
                )

    errors = sum(1 for issue in issues if issue["severity"] == "error")
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": errors == 0,
        "issues": issues,
        "claims_checked": checked,
        "claims_verified": 0,
        "claims_unverified": checked,
        "llm_checks_run": 0,
        "retries_issued": [],
        "notes": [
            "MINIMAL GATE: only unresolved_fact ran. Every claim is reported "
            "unverified because the other checks in docs/verification.md are not "
            "built yet - an unchecked claim must not read as a verified one."
        ],
    }

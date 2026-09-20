"""P2 (Calc, Audit & Eval) owns this file. Public interface of the verifier.

BOUNDARY (docs/adr/0007): audit/ reads a ResearchState and a Factsheet, and
nothing else. Both of its external needs are INJECTED as callables:
  - `get_text`     data.api.get_section_text, so audit never imports data/,
  - `verify_claim` an LLM callable, so audit depends on no model SDK.

The gate is mostly deterministic (ADR 0005). Only UNSUPPORTED_CLAIM needs an
LLM; keeping that list short is what keeps the gate cheap and reproducible.

Signature MUST NOT change (CONTRACT-CHANGE PR, CONTRIBUTING.md).
"""

from __future__ import annotations

from collections.abc import Callable

from audit import deterministic
from audit.llm_checks import check_unsupported_claims
from audit.routing import MAX_RETRIES, NOT_RETRYABLE, build_directives, section_key_of
from schema.contracts.enums import Severity
from schema.contracts.factsheet import Factsheet
from schema.contracts.state import ResearchState
from schema.contracts.verification import VerificationResult


def run_audit(
    state: dict,
    factsheet: dict,
    get_text: Callable[[str], str],
    verify_claim: Callable[[str, str], bool] | None = None,
) -> dict:
    """Return a VerificationResult (schema/audit.json).

    Runs the seven deterministic checks (docs/verification.md), then the one
    LLM check (verbatim match first, `verify_claim` only on failure). Builds
    one RetryDirective per section that still has a retryable issue AND has
    not yet reached MAX_RETRIES; claims with a non-retryable issue, or whose
    section is already at the cap, are counted as claims_unverified rather
    than retried (ADR 0005: the report ships with those marked, not blocked).

    Takes no `as_of`: `state["as_of"]` and `factsheet["as_of"]` are authoritative.
    """
    st = ResearchState.model_validate(state)
    fs = Factsheet.model_validate(factsheet)

    issues = deterministic.run_all(st, fs)
    llm_issues, llm_calls = check_unsupported_claims(st, get_text, verify_claim)
    issues += llm_issues

    error_claim_ids = {i.claim_id for i in issues if i.severity is Severity.ERROR and i.claim_id}
    terminal_unverified: set[str] = set()
    for issue in issues:
        if issue.severity is not Severity.ERROR or not issue.claim_id:
            continue
        if issue.issue_type in NOT_RETRYABLE:
            terminal_unverified.add(issue.claim_id)
            continue
        key = section_key_of(issue)
        section = getattr(st.sections, key, None) if key else None
        if section is not None and section.retry_count >= MAX_RETRIES:
            terminal_unverified.add(issue.claim_id)

    # attempt = the round about to be requested; every section not yet at cap
    # is on its own next attempt (section.retry_count + 1), but a single
    # RetryDirective batch shares one attempt number for the round.
    attempt = max((s.retry_count for s in st.sections.as_list()), default=0) + 1
    retries_issued = build_directives(st, issues, attempt)

    claims_checked = len(st.all_claims)
    claims_unverified = len(terminal_unverified)
    claims_verified = claims_checked - len(error_claim_ids)

    result = VerificationResult(
        schema_version=fs.schema_version,
        passed=not any(i.severity is Severity.ERROR for i in issues),
        issues=issues,
        claims_checked=claims_checked,
        claims_verified=claims_verified,
        claims_unverified=claims_unverified,
        llm_checks_run=llm_calls,
        retries_issued=retries_issued,
    )
    return result.model_dump(mode="json")

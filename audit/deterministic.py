"""The deterministic half of the verification gate. Seven checks, no LLM.

Specified by docs/verification.md and docs/adr/0005.

These run first and catch most real failures, because most real failures are
mechanical: a citation that does not resolve, a number that does not recompute,
a figure quoted from a filing that was later restated. Cheap, reproducible, and
they never hallucinate a problem.

Each check raises VerificationIssue objects carrying the section they came from,
which is what lets routing.py send a targeted retry to one agent.

SCOPE NOTE (audit/ reads a ResearchState and a Factsheet, and nothing else -
ADR 0005): there is no injected fact-repository callable in run_audit's frozen
signature, so unresolved_fact/superseded_fact/future_fact are checked against
what a Factsheet can actually answer, not a full truth-layer lookup:
  - A canonical current fact_id ("fact:<ticker>:<metric>:<period>", exactly 4
    segments) resolves by reading that field straight off the Factsheet.
  - A fact_id with an extra trailing segment ("fact:<ticker>:<metric>:<period>:
    <variant>", e.g. ":as-filed") is, by that naming convention, an explicit
    reference to a superseded historical snapshot - the Factsheet never holds
    one, by construction (it only ever carries the current value).
  - Both checks apply only to claims that assert a NUMBER (claim.value is not
    None). A claim that only DISCUSSES history in prose - e.g. "operating cash
    flow was restated" - may cite both the current and the historical fact_id
    without asserting either as a number, and is not in scope; the violation
    these checks exist to catch is presenting a stale figure AS IF it were
    current, not mentioning that a restatement happened.
"""

from __future__ import annotations

from calc.metrics.fcf import capex_intensity, ebitda, fcf_conversion, fcf_yield, free_cash_flow
from calc.metrics.working_capital import days_inventory, days_sales_outstanding
from schema.contracts.common import ValueObject
from schema.contracts.enums import IssueType, Severity, Trend, ValueType
from schema.contracts.factsheet import Factsheet
from schema.contracts.state import ResearchSection, ResearchState
from schema.contracts.verification import VerificationIssue

_NON_GAAP_MARKERS = ("adjusted", "non-gaap", "pro forma", "proforma")

_DERIVED_METRIC_FNS = {
    "fcf": free_cash_flow,
    "ebitda": ebitda,
    "fcf_conversion": fcf_conversion,
    "fcf_yield": fcf_yield,
    "capex_intensity": capex_intensity,
    "dso": days_sales_outstanding,
    "days_sales_outstanding": days_sales_outstanding,
    "days_inventory": days_inventory,
}
"""metric name -> calc/metrics per-period function. A fact_id can name either a
RAW reported field (read straight off the FinancialPeriod) or one of these
CALC-DERIVED metrics; both resolve "via the Factsheet" in the sense that ADR
0005 means it - no external truth-layer lookup, just calc/'s own pure
functions over the same Factsheet audit/ was given."""

_OPPOSITE_TRENDS: dict[Trend, frozenset[Trend]] = {
    Trend.STRUCTURALLY_POSITIVE: frozenset({Trend.STRUCTURALLY_NEGATIVE, Trend.TEMPORARILY_NEGATIVE}),
    Trend.TEMPORARILY_POSITIVE: frozenset({Trend.STRUCTURALLY_NEGATIVE, Trend.TEMPORARILY_NEGATIVE}),
    Trend.STRUCTURALLY_NEGATIVE: frozenset({Trend.STRUCTURALLY_POSITIVE, Trend.TEMPORARILY_POSITIVE}),
    Trend.TEMPORARILY_NEGATIVE: frozenset({Trend.STRUCTURALLY_POSITIVE, Trend.TEMPORARILY_POSITIVE}),
}


def _resolve_via_factsheet(factsheet: Factsheet, fact_id: str):
    """A canonical fact_id resolves straight off the Factsheet, or None.

    Returns {"value", "filed_at"} for a 4-segment id that names a real
    period+metric with a known value; None otherwise (including for any
    5+-segment "historical variant" id - the Factsheet never holds one).
    """
    parts = fact_id.split(":")
    if len(parts) != 4 or parts[0] != "fact":
        return None
    _, ticker, metric, period = parts
    if ticker != factsheet.ticker:
        return None
    p = factsheet.period(period)
    if p is None:
        return None

    if hasattr(p, metric):
        vo: ValueObject = getattr(p, metric)
    else:
        fn = _DERIVED_METRIC_FNS.get(metric)
        vo = fn(factsheet, period) if fn else None

    if vo is None or vo.status != "ok":
        return None
    return {"value": vo.value, "filed_at": p.filed_date}


def _is_historical_variant(fact_id: str) -> bool:
    """fact:<ticker>:<metric>:<period>:<anything> - an explicit reference to a
    superseded snapshot, by naming convention (see module docstring)."""
    parts = fact_id.split(":")
    return len(parts) > 4 and parts[0] == "fact"


def _numeric_claims(state: ResearchState):
    """(section, claim) for every claim asserting a number."""
    for section in state.sections.as_list():
        for claim in section.claims:
            if claim.value is not None:
                yield section, claim


def check_unresolved_facts(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """Every cited fact_id on a numeric claim must resolve. A dangling citation
    is not provenance."""
    issues = []
    for section, claim in _numeric_claims(state):
        for fact_id in claim.fact_ids:
            if _is_historical_variant(fact_id):
                continue  # handled by check_superseded_facts
            if _resolve_via_factsheet(factsheet, fact_id) is None:
                issues.append(VerificationIssue(
                    issue_type=IssueType.UNRESOLVED_FACT, severity=Severity.ERROR,
                    path=f"sections.{section.section_key}",
                    message=f"fact_id {fact_id!r} does not resolve against the factsheet",
                    claim_id=claim.claim_id, fact_id=fact_id,
                ))
    return issues


def check_superseded_facts(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """No NUMERIC claim may present a superseded fact as current."""
    issues = []
    for section, claim in _numeric_claims(state):
        for fact_id in claim.fact_ids:
            if _is_historical_variant(fact_id):
                issues.append(VerificationIssue(
                    issue_type=IssueType.SUPERSEDED_FACT, severity=Severity.ERROR,
                    path=f"sections.{section.section_key}",
                    message=f"claim asserts a number citing the superseded fact {fact_id!r}",
                    claim_id=claim.claim_id, fact_id=fact_id,
                ))
    return issues


def check_future_facts(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """No claim may cite a fact filed after the run's as_of.

    Defense in depth: Factsheet already guarantees point-in-time correctness
    (its own model validator rejects anything filed after its as_of), but this
    re-checks independently rather than trusting that guarantee blindly - the
    backtest's integrity rests on this one (error A).
    """
    issues = []
    for section, claim in _numeric_claims(state):
        for fact_id in claim.fact_ids:
            resolved = _resolve_via_factsheet(factsheet, fact_id)
            if resolved and resolved["filed_at"] > state.as_of:
                issues.append(VerificationIssue(
                    issue_type=IssueType.FUTURE_FACT, severity=Severity.ERROR,
                    path=f"sections.{section.section_key}",
                    message=f"fact_id {fact_id!r} was filed {resolved['filed_at']}, after "
                            f"as_of {state.as_of}",
                    claim_id=claim.claim_id, fact_id=fact_id,
                ))
    return issues


def check_recompute(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """Re-derive every computed number from its inputs and compare.

    Only possible because calc/ is pure and every derived value carries its
    formula and inputs (ADR 0002). Recomputes by calling calc.api.compute_metrics
    on the SAME factsheet (both live in P2; this is not an external input) and
    matching claim.value.derived_from against a metrics field with the same
    derived_from - a stable fingerprint for "which metric is this".
    """
    from calc.api import compute_metrics

    metrics = compute_metrics(factsheet.model_dump(mode="json"))
    index: dict[tuple[str, ...], float | None] = {}
    for _, vo in _walk_value_objects(metrics):
        key = tuple(vo.get("derived_from") or [])
        if key and key not in index:
            index[key] = vo.get("value")

    issues = []
    for section, claim in _numeric_claims(state):
        v = claim.value
        if v.type is not ValueType.FACT or not v.derived_from:
            continue
        recomputed = index.get(tuple(v.derived_from))
        if recomputed is None or v.value is None:
            continue
        tolerance = max(1e-6, abs(recomputed) * 1e-6)
        if abs(recomputed - v.value) > tolerance:
            issues.append(VerificationIssue(
                issue_type=IssueType.RECOMPUTE_MISMATCH, severity=Severity.ERROR,
                path=f"sections.{section.section_key}",
                message=f"{claim.claim_id}: claim value does not recompute from its inputs",
                claim_id=claim.claim_id,
                expected=str(recomputed), actual=str(v.value),
            ))
    return issues


def _walk_value_objects(obj, path: str = ""):
    if isinstance(obj, dict):
        if {"value", "unit", "type", "status"} <= set(obj):
            yield path, obj
        for k, v in obj.items():
            yield from _walk_value_objects(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_value_objects(v, f"{path}[{i}]")


def check_prose_numbers(state: ResearchState) -> list[VerificationIssue]:
    """Numerals in claim text must match the claim's ValueObject.

    Catches the common failure where an agent computes correctly, then rounds or
    mistypes the number in the sentence a reader actually sees.
    """
    issues = []
    for section, claim in _numeric_claims(state):
        prose_numbers = set(claim.prose_numbers)
        if not prose_numbers:
            continue
        candidates = _formatted_candidates(claim.value)
        if candidates and not (prose_numbers & candidates):
            issues.append(VerificationIssue(
                issue_type=IssueType.PROSE_NUMBER_MISMATCH, severity=Severity.ERROR,
                path=f"sections.{section.section_key}",
                message=f"{claim.claim_id}: claim text numerals do not match its ValueObject",
                claim_id=claim.claim_id,
                expected=str(claim.value.value), actual=", ".join(sorted(prose_numbers)),
            ))
    return issues


def _formatted_candidates(vo: ValueObject) -> set[str]:
    if vo.value is None:
        return set()
    v = vo.value
    candidates = {f"{v:.{nd}f}" for nd in (0, 1, 2)}
    if vo.unit == "fraction":
        pct = v * 100
        candidates |= {f"{pct:.{nd}f}" for nd in (0, 1, 2)}
    elif vo.unit == "usd":
        if abs(v) >= 1e9:
            candidates |= {f"{v / 1e9:.{nd}f}" for nd in (0, 1)}
        if abs(v) >= 1e6:
            candidates |= {f"{v / 1e6:.{nd}f}" for nd in (0, 1)}
        candidates.add(f"{v:,.0f}".replace(",", ""))
    return candidates


def check_adjusted_as_gaap(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """No non-GAAP figure may be presented as a GAAP one.

    "Adjusted EBITDA" and "EBITDA" are different numbers; using them
    interchangeably flatters every multiple built on top. calc/ only ever
    computes unadjusted figures, so the only way a non-GAAP number enters the
    system is an agent asserting one in prose - flagged when it is presented
    with type 'fact' (as if reported/computed the normal way) rather than
    called out as an adjustment.
    """
    issues = []
    for section, claim in _numeric_claims(state):
        if claim.value.type is not ValueType.FACT:
            continue
        haystack = " ".join([claim.text.lower()] + [e.quote.lower() for e in claim.evidence])
        if any(marker in haystack for marker in _NON_GAAP_MARKERS):
            issues.append(VerificationIssue(
                issue_type=IssueType.ADJUSTED_AS_GAAP, severity=Severity.WARN,
                path=f"sections.{section.section_key}",
                message=f"{claim.claim_id}: a non-GAAP-flavoured figure is presented as type 'fact'",
                claim_id=claim.claim_id,
            ))
    return issues


def check_cross_agent_contradictions(state: ResearchState) -> list[VerificationIssue]:
    """No two sections may assert incompatible things.

    Agents run in parallel and cannot see each other. Starts narrow (ADR 0005):
    flags two claims from DIFFERENT sections' owning agents that cite the same
    fact_id with opposing trend polarity.
    """
    by_fact: dict[str, list[tuple[ResearchSection, object]]] = {}
    for section in state.sections.as_list():
        for claim in section.claims:
            for fact_id in claim.fact_ids:
                by_fact.setdefault(fact_id, []).append((section, claim))

    issues = []
    for fact_id, pairs in by_fact.items():
        for i in range(len(pairs)):
            sec_a, claim_a = pairs[i]
            for sec_b, claim_b in pairs[i + 1:]:
                if sec_a.owner == sec_b.owner:
                    continue
                if claim_b.trend in _OPPOSITE_TRENDS.get(claim_a.trend, frozenset()):
                    issues.append(VerificationIssue(
                        issue_type=IssueType.CROSS_AGENT_CONTRADICTION, severity=Severity.WARN,
                        path=f"sections.{sec_a.section_key}",
                        message=f"{claim_a.claim_id} ({claim_a.trend.value}) and {claim_b.claim_id} "
                                f"({claim_b.trend.value}) both cite {fact_id!r} with opposing trends",
                        claim_id=claim_a.claim_id, fact_id=fact_id,
                    ))
    return issues


def run_all(state: ResearchState, factsheet: Factsheet) -> list[VerificationIssue]:
    """Run all seven deterministic checks."""
    return [
        *check_unresolved_facts(state, factsheet),
        *check_recompute(state, factsheet),
        *check_prose_numbers(state),
        *check_superseded_facts(state, factsheet),
        *check_future_facts(state, factsheet),
        *check_adjusted_as_gaap(state, factsheet),
        *check_cross_agent_contradictions(state),
    ]

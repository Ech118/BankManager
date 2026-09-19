"""Individual audit checks (plan.txt 15.14 P2 step 6). No I/O of our own -
get_text is injected by the caller (data.api.get_section_text), so audit never
imports data/ directly (plan.txt 15.8).
"""
from __future__ import annotations

import re
from typing import Callable, Iterable

ALLOWED_EXTERNAL_SOURCE_PREFIXES = ("src:llm:", "src:config:")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _walk(obj, path: str = ""):
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _is_value_object(node) -> bool:
    return isinstance(node, dict) and {"value", "unit", "type", "status"} <= set(node)


def value_objects(obj) -> list[tuple[str, dict]]:
    return [(p, n) for p, n in _walk(obj) if _is_value_object(n)]


def evidence_items(obj) -> list[tuple[str, dict]]:
    return [(p, n) for p, n in _walk(obj) if isinstance(n, dict) and {"quote", "source_id"} <= set(n)]


def check_numbers_trace(verdict: dict, factsheet: dict, metrics: dict) -> list[dict]:
    """(a) every number in the verdict traces to factsheet/metrics/scenario_result:
    status "ok" numbers must carry either a source_id that resolves in
    factsheet.sources (or an allowed external prefix) or a non-empty
    derived_from. This re-checks at audit time, independent of schema
    validation, so a fabricated/injected number is still caught (plan.txt
    "Done when: audit catches an injected fake number")."""
    issues = []
    known_sources = set(factsheet.get("sources", {}))
    for path, vo in value_objects(verdict):
        if vo.get("status") != "ok":
            continue
        source_id = vo.get("source_id")
        derived_from = vo.get("derived_from") or []
        if source_id:
            if source_id not in known_sources and not source_id.startswith(ALLOWED_EXTERNAL_SOURCE_PREFIXES):
                issues.append({
                    "severity": "error",
                    "path": path,
                    "message": f"source_id {source_id!r} does not resolve in factsheet.sources",
                })
            continue
        if derived_from:
            continue
        issues.append({
            "severity": "error",
            "path": path,
            "message": "value has status 'ok' but neither a resolvable source_id nor derived_from",
        })
    return issues


def check_evidence_quotes(analyses: Iterable[dict], verdict: dict, get_text: Callable[[str], str]) -> list[dict]:
    """(b) every qualitative claim's quote appears verbatim (whitespace-
    normalised) in the text behind its source_id (plan.txt error I)."""
    issues = []
    seen: set[tuple[str, str]] = set()

    def _check(path: str, ev: dict) -> None:
        quote, source_id = ev.get("quote"), ev.get("source_id")
        key = (quote, source_id)
        if key in seen:
            return
        seen.add(key)
        try:
            text = get_text(source_id)
        except KeyError:
            issues.append({
                "severity": "error",
                "path": path,
                "message": f"evidence cites unknown source_id {source_id!r}",
            })
            return
        if _norm(quote) not in _norm(text):
            issues.append({
                "severity": "error",
                "path": path,
                "message": f"quote not found verbatim in {source_id!r}: {quote!r}",
            })

    for i, analysis in enumerate(analyses):
        for path, ev in evidence_items(analysis):
            _check(f"agent_outputs[{i}].{path}", ev)
    for path, ev in evidence_items(verdict.get("sections", [])):
        _check(f"sections.{path}", ev)
    return issues


def check_disclaimer(verdict: dict) -> list[dict]:
    """(c) disclaimer present and non-trivial (plan.txt error M)."""
    disclaimer = (verdict.get("disclaimer") or "").strip()
    if len(disclaimer) < 20:
        return [{
            "severity": "error",
            "path": "disclaimer",
            "message": "disclaimer is missing or too short",
        }]
    return []


def check_consistency(verdict: dict) -> list[dict]:
    """(d) consistency: score, P(beat S&P), expected return and verdict must
    agree (plan.txt 15.14 P2 step 5/6)."""
    from calc.consistency import validate_consistency

    scenario_result = verdict.get("scenario_result")
    card = verdict.get("card")
    if not scenario_result or not card:
        return [{"severity": "error", "path": "<root>", "message": "verdict missing scenario_result or card"}]
    result = validate_consistency(scenario_result, card)
    return [{"severity": "error", "path": "consistency", "message": issue} for issue in result["issues"]]

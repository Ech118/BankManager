"""Number references: the LLM never types a financial figure.

The DATA REFERENCE TABLE lists every value object by path. Agents attach numbers
to findings with number_refs (paths); resolve() returns the real value objects
from the factsheet / metrics / scenario_result, so figures stay code-computed.
"""
from __future__ import annotations

import copy


def _is_vo(x) -> bool:
    return isinstance(x, dict) and {"value", "unit", "type", "status"} <= set(x)


def _walk(obj, prefix: str):
    if _is_vo(obj):
        yield prefix, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{prefix}.{i}")


def build_index(factsheet: dict, metrics: dict, scenario_result: dict | None = None) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for key in ("market", "sp500_baseline", "consensus"):
        for p, vo in _walk(factsheet.get(key, {}), key):
            idx[p] = vo
    for period in factsheet.get("financials", []):
        for field, vo in period.items():
            if _is_vo(vo):
                idx[f"financials.{period['period']}.{field}"] = vo
    for peer in factsheet.get("peers", []):
        for p, vo in _walk({k: v for k, v in peer.items() if k != "ticker"}, f"peers.{peer['ticker']}"):
            idx[p] = vo
    for p, vo in _walk(metrics, "metrics"):
        idx[p] = vo
    if scenario_result:
        for p, vo in _walk(scenario_result, "scenario_result"):
            idx[p] = vo
    return idx


def _fmt(vo: dict) -> str:
    if vo["status"] != "ok" or vo["value"] is None:
        return "unavailable"
    v = vo["value"]
    return f"{v:.6g}"


def format_table(index: dict[str, dict], prefixes: tuple[str, ...] | None = None) -> str:
    lines = []
    for path in sorted(index):
        if prefixes and not path.startswith(prefixes):
            continue
        vo = index[path]
        lines.append(f"{path} = {_fmt(vo)} ({vo['unit']}, {vo['type']})")
    return "\n".join(lines)


def resolve(paths: list[str], index: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Return (value objects, unresolved paths). Duplicates are collapsed."""
    found, missing, seen = [], [], set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        if p in index:
            found.append(copy.deepcopy(index[p]))
        else:
            missing.append(p)
    return found, missing

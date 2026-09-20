"""Plain-text renderings of calc results for prompts. Formatting only: no arithmetic."""

from __future__ import annotations


def _num(vo: dict | None) -> str:
    if not vo or vo.get("status") != "ok" or vo.get("value") is None:
        return "unavailable"
    return f"{vo['value']:.6g} ({vo['unit']}, {vo['type']})"


def scenario_table(sr: dict) -> str:
    """The parts of a ScenarioResult the Synthesizer needs to pick a consistent verdict word."""
    if not sr:
        return "(not available)"
    lines = [
        f"expected_annualized_return = {_num(sr.get('expected_annualized_return'))}",
        f"sp500_expected_return = {_num(sr.get('sp500_expected_return'))}",
    ]
    for h in ("short_term", "medium_term", "long_term"):
        lines.append(
            f"expected_return_vs_sp500.{h} = {_num((sr.get('expected_return_vs_sp500') or {}).get(h))}"
        )
        lines.append(f"p_beat_sp500.{h} = {(sr.get('p_beat_sp500') or {}).get(h)}")
        lines.append(f"scores.{h} = {(sr.get('scores') or {}).get(h)}")
    for case, out in (sr.get("scenarios") or {}).items():
        lines.append(f"scenarios.{case}.price_target = {_num(out.get('price_target'))}")
        lines.append(f"scenarios.{case}.annualized_return = {_num(out.get('annualized_return'))}")
    weights = sr.get("weights") or {}
    lines.append(f"weights.any_clamped = {weights.get('any_clamped')}")
    return "\n".join(lines)

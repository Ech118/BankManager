"""Render verdict.sections from agent outputs and calc results (no LLM, no new numbers).

Sections 1-10 come from analyst findings, 11-12 from scenario_result, 13-15 from the
synthesizer's text plus code-inserted figures. The UI prefers the structured
agent_outputs (so it can colour numbers by fact/estimate/assumption); body_markdown
is the plain-text rendering of the same content.
"""
from __future__ import annotations

SECTION_DEFS = [  # (id, title, agent)
    ("financial_quality", "1. Financial quality", "forensic"),
    ("income_statement", "2. Income statement deep dive", "forensic"),
    ("balance_sheet", "3. Balance sheet strength", "balance_sheet"),
    ("free_cash_flow", "4. Free cash flow", "balance_sheet"),
    ("management_guidance", "5. Management and guidance", "business"),
    ("competitive_position", "6. Competitive position", "business"),
    ("valuation", "7. Valuation", "valuation"),
    ("expectations_vs_reality", "8. Expectations vs reality", "valuation"),
    ("catalysts", "9. Catalysts", "business"),
    ("risks", "10. Risks", "red_team"),
    ("scenarios", "11. Bull / base / bear", "calc"),
    ("sp500_test", "12. S&P 500 outperformance test", "calc"),
    ("buyability", "13. Buyability score", "synthesizer"),
    ("buy_more_or_sell", "14. What would make me buy more or sell", "synthesizer"),
    ("committee_verdict", "15. Investment committee verdict", "synthesizer"),
]


def fmt(vo: dict) -> str:
    if vo.get("status") != "ok" or vo.get("value") is None:
        return "unavailable"
    v, u = vo["value"], vo["unit"]
    if u == "fraction":
        return f"{v * 100:.1f}%"
    if u == "usd":
        a = abs(v)
        return f"${v / 1e9:.2f}B" if a >= 1e9 else f"${v / 1e6:.1f}M" if a >= 1e6 else f"${v:,.0f}"
    if u == "usd_per_share":
        return f"${v:.2f}"
    if u == "multiple":
        return f"{v:.1f}x"
    if u == "shares":
        return f"{v / 1e6:.1f}M shares"
    if u == "days":
        return f"{v:.0f} days"
    return f"{v:.2f}"


def _finding_md(f: dict) -> str:
    lines = [f"- **{f['claim']}** _({f['trend'].replace('_', ' ')}; {f['confidence']} confidence)_"]
    if f.get("numbers"):
        lines.append("  - Figures: " + "; ".join(f"{fmt(n)} [{n['type']}]" for n in f["numbers"]))
    for ev in f["evidence"]:
        lines.append(f"  > \"{ev['quote']}\" ({ev['source_id']})")
    return "\n".join(lines)


def _analysis_section(sid: str, agent: str, analyses: dict) -> tuple[str, list[dict]]:
    a = analyses.get(agent)
    if not a:
        return "_No analysis available._", []
    mine = [f for f in a["findings"] if f.get("section") == sid]
    first = next((d[0] for d in SECTION_DEFS if d[2] == agent), None)
    parts = [f"_{a['summary']}_"] if sid == first else []
    parts += [_finding_md(f) for f in mine] or ["_No findings in this section._"]
    ev = [e for f in mine for e in f["evidence"]]
    return "\n\n".join(parts), ev


def _scenario_md(sr: dict, scen: dict) -> str:
    rows = ["| Case | Probability | Price target | Annualized return | Rationale |", "|---|---|---|---|---|"]
    for k in ("bear", "base", "bull"):
        r = sr["scenarios"][k]
        why = scen["scenarios"][k]["rationale"] if scen else ""
        rows.append(f"| {k.title()} | {r['probability'] * 100:.0f}% | {fmt(r['price_target'])} | "
                    f"{fmt(r['annualized_return'])} | {why} |")
    rows.append(f"\nProbability-weighted annualized return: **{fmt(sr['expected_annualized_return'])}** "
                f"versus S&P 500 assumption {fmt(sr['sp500_expected_return'])} [assumption].")
    return "\n".join(rows)


def _sp_md(sr: dict) -> str:
    p, pr = sr["p_beat_sp500"], sr["prior"]
    rows = ["| Horizon | Probability of beating the S&P 500 | Base rate |", "|---|---|---|"]
    for h in ("1y", "3y", "5y"):
        rows.append(f"| {h} | {p[h] * 100:.0f}% | {pr['base_rate'][h] * 100:.0f}% |")
    rows.append(f"\nShift applied to the base rate: {pr['applied_shift'] * 100:+.0f} pts "
                f"(requested {pr['requested_shift'] * 100:+.0f}, cap ±{pr['cap'] * 100:.0f}).")
    return "\n".join(rows)


def render_sections(analyses: dict, scenario_result: dict, scenarios: dict | None,
                    synthesis: dict, card: dict) -> list[dict]:
    out = []
    for sid, title, agent in SECTION_DEFS:
        evidence: list[dict] = []
        if agent in ("forensic", "business", "balance_sheet", "valuation", "red_team"):
            body, evidence = _analysis_section(sid, agent, analyses)
        elif sid == "scenarios":
            body = _scenario_md(scenario_result, scenarios or {})
        elif sid == "sp500_test":
            body = _sp_md(scenario_result)
        elif sid == "buyability":
            s = card["scores"]
            body = (f"| Horizon | Score (1-10) |\n|---|---|\n| Short term (0-12 months) | {s['short_term']} |\n"
                    f"| Medium term (1-3 years) | {s['medium_term']} |\n| Long term (3-5+ years) | {s['long_term']} |\n\n"
                    + synthesis["buyability_text"])
        elif sid == "buy_more_or_sell":
            body = ("**Buy more if:**\n" + "\n".join(f"- {x}" for x in synthesis["buy_more_if"])
                    + "\n\n**Sell / avoid if:**\n" + "\n".join(f"- {x}" for x in synthesis["sell_if"]))
        else:
            a = card["ten_thousand_dollar_answer"]
            body = (f"**Verdict: {card['verdict'].replace('_', ' ').upper()}**\n\n{card['thesis']}\n\n"
                    f"{synthesis['committee_verdict_text']}\n\n"
                    f"With $10,000 for five years: **{'this stock' if a['choice'] == 'this_stock' else 'the S&P 500'}**. {a['reason']}")
        out.append({"id": sid, "title": title, "body_markdown": body, "agent": agent, "evidence": evidence})
    return out

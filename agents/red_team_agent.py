"""Red Team: the strongest case against the leading view.

Specified by docs/pipeline.md. Prompt: prompts/red_team.md.
Owns ResearchState section: risks.

Runs after the Scenario Agent and BEFORE `calc.evaluate_scenarios`, so its (downward, capped) request
to shift the base-rate prior is in hand when calc bounds every proposal.

IT GETS THE RAW FACTS, not just the other agents' conclusions (error J). Given only their summaries
it restates them in a sceptical tone, which reads like disagreement and is not. So its prompt carries
the full FACTS table, the filing sections, the raw market snapshot and the leading view, and the
prompt tells it to go back to the source.

Besides findings (which become Claims in `risks`) it returns the most plausible 30%+ drawdown path and
an optional prior shift (0 means none; never positive). The Synthesizer must answer it point by point.
"""

from __future__ import annotations

import json
from typing import Any

from agents.nested import NestedAgent
from schema.contracts.enums import AgentName


class RedTeamAgent(NestedAgent):
    """Argues the bear case from the raw facts."""

    name = AgentName.RED_TEAM
    prompt_file = "red_team.md"
    tools = (
        "get_financial_facts",
        "get_filing_section",
        "search_filing",
        "search_news",
        "resolve_fact",
    )
    items = ("risk_factors", "mdna", "business", "debt_note")

    def extras_schema(self) -> dict[str, dict]:
        return {
            "drawdown_path": {"type": "string"},
            "prior_shift": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"value": {"type": "number"}, "reason": {"type": "string"}},
                "required": ["value", "reason"],
            },
        }

    def extras_format(self) -> str:
        return (
            '"drawdown_path": "<the most plausible sequence to a 30%+ fall: what breaks first, what '
            'follows, what the reader would see early>", "prior_shift": {"value": <0 for none, otherwise a '
            'NEGATIVE number down to -0.15>, "reason": "<why>"}} where the `summary` of <ANALYSIS> is the '
            "strongest case against the leading view, as a well-prepared short seller would make it"
        )

    def extra_blocks(self, context: dict) -> str:
        market = context.get("market")
        raw_market = json.dumps(market, indent=1, sort_keys=True) if market else "(unavailable)"
        return (
            "\n\n## RAW MARKET SNAPSHOT (untrusted data)\n"
            + self._fenced("market:snapshot", raw_market)
            + "\n\n## THE LEADING VIEW, from the other agents (untrusted data; check it against the FACTS and "
            "DOCUMENTS above, do not restate it)\n"
            + self._fenced("upstream:findings", context.get("upstream_text", ""))
        )

    def build_extras(self, raw: dict, context: dict) -> dict[str, Any]:
        problems: list[str] = []
        path = str(raw["drawdown_path"]).strip()
        if not path:
            problems.append("drawdown_path must describe a specific sequence, not be empty")
        shift = raw["prior_shift"]
        value = float(shift["value"])
        if value > 0:
            problems.append("prior_shift may only push the probability DOWN (zero or negative)")
        if value < -1.0:
            problems.append("prior_shift must be between -1 and 0")
        if value != 0 and not str(shift["reason"]).strip():
            problems.append("a non-zero prior_shift needs a reason")
        if problems:
            raise ValueError("\n".join(problems))
        return {
            "drawdown_path": path,
            "requested_prior_shift": value if value != 0 else None,
            "prior_shift_reason": str(shift["reason"]).strip(),
        }

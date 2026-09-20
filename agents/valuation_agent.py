"""Valuation Agent: what does today's price already assume?

Specified by docs/pipeline.md. Prompt: prompts/valuation.md.
Owns ResearchState sections: valuation, expectations.

Runs AFTER the financial and business agents, and reads both.

CHOOSES, NEVER COMPUTES. It picks the methods and the peers and justifies both,
then calls calculate_valuation for every number. A P/E it works out itself is a
defect, not a shortcut (ADR 0001).

Its most valuable output is the expectations section: the reverse DCF says what
growth the current price implies, and this agent judges whether the filings
support that. "Is it worth $50?" mostly returns the analyst's own assumptions;
"what would have to be true for $50 to be right?" is a question the evidence can
actually answer.

Peer choice moves the result more than almost any other input, so a peer set
that differs from the deterministic default needs a stated reason (error E).

How a run goes (three steps, so the agent chooses but code computes):

  1. PLAN     the agent is shown the deterministic default peers and the Financial and
              Business findings, and picks methods and peers with a reason for each.
  2. CALCULATE  code calls `calculate_valuation` through MCP with those choices.
  3. INTERPRET  the agent reads the results and writes findings for `valuation` and
              `expectations`, citing every calculated figure by path in `calc_refs` and
              every input by `fact_id`; it never types a number.

The reasons for the method and peer choices are kept on the analysis as `valuation_plan`
(they are argued, not assumed, but they are not filing claims, so they are not Claims).
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import Agent
from schema.contracts.analysis import Analysis
from schema.contracts.enums import AgentName

log = logging.getLogger("bankmanager.valuation")

METHODS = ("pe", "ev_ebitda", "ev_revenue", "p_fcf", "peer_median", "historical", "reverse_dcf")
"""The names calculate_valuation accepts (schema/contracts/tools.py)."""

ALWAYS = "reverse_dcf"
"""Always computed: the expectations section, this agent's most valuable output, depends on it."""

PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "methods": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "enum": list(METHODS)},
                    "reason": {"type": "string"},
                },
                "required": ["name", "reason"],
            },
        },
        "peers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"ticker": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["ticker", "reason"],
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["methods", "peers", "notes"],
}

_PLAN_FORMAT = (
    "\n\n---\n\n# This step: PLAN (do not analyse yet)\n\n"
    "Choose the valuation methods and the peers. Return ONE JSON object and nothing else:\n"
    '{"methods": [{"name": one of '
    + str(list(METHODS))
    + ', "reason": "<why this business supports it>"}], '
    '"peers": [{"ticker": "<one of the PEER CANDIDATES>", "reason": "<why comparable, or why kept>"}], '
    '"notes": "<what you changed from the default list and why, or that you kept it>"}\n\n'
    "Pick only from the candidates below. Keeping the default list needs no justification beyond a short reason; "
    "adding or dropping a peer does. Do not compute anything and do not state any valuation figure."
)


class ValuationAgent(Agent):
    """Method and peer selection, multiples, and the reverse-DCF reading."""

    name = AgentName.VALUATION
    prompt_file = "valuation.md"
    tools = (
        "calculate_valuation",
        "get_peer_companies",
        "get_market_snapshot",
        "get_financial_facts",
        "get_filing_section",
        "resolve_fact",
    )
    items = ("mdna", "business")
    uses_calc = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.plan: dict[str, Any] = {}
        self._plan_dropped: list[dict[str, str]] = []
        self._upstream_text = ""

    # ------------------------------------------------------------------ step 1: plan
    def _plan_check(self, candidates: dict[str, dict]) -> Any:
        def check(data: dict) -> list[str]:
            problems: list[str] = []
            names = [m.get("name") for m in data.get("methods", []) if isinstance(m, dict)]
            if not names:
                problems.append("choose at least one method")
            if len(set(names)) != len(names):
                problems.append("each method may appear once")
            for m in data.get("methods", []):
                if m.get("name") not in METHODS:
                    problems.append(f"unknown method {m.get('name')!r}; use one of {list(METHODS)}")
                if not str(m.get("reason", "")).strip():
                    problems.append(f"method {m.get('name')!r} needs a reason")
            for p in data.get("peers", []):
                if not str(p.get("reason", "")).strip():
                    problems.append(f"peer {p.get('ticker')!r} needs a reason")
            return problems

        return check

    def _plan(self, context: dict, candidates: dict[str, dict]) -> dict[str, Any]:
        table = (
            "\n".join(
                f"{t} | {c.get('company_name') or ''} | SIC {c.get('sic') or '?'} | "
                f"selection: {c.get('selection_reason') or 'default (SIC + market-cap band)'}"
                for t, c in candidates.items()
            )
            or "(no peer candidates available: say so and choose methods that need no peers)"
        )
        user = (
            f"TICKER: {context['ticker']}\nAS OF: {context['as_of']}\n\n"
            "## PEER CANDIDATES (untrusted data)\n"
            + self._fenced("peers:candidates", table)
            + "\n\n"
            "## UPSTREAM FINDINGS (untrusted data)\n"
            + self._fenced("upstream:findings", self._upstream_text)
        )
        system = self.system_prompt() + _PLAN_FORMAT
        raw = self.call_structured(system, user, PLAN_SCHEMA, self._plan_check(candidates), "plan")

        methods = {m["name"]: m["reason"] for m in raw["methods"]}
        if ALWAYS not in methods:
            methods[ALWAYS] = "always computed: the expectations reading depends on it"
        peers: dict[str, str] = {}
        for p in raw["peers"]:
            if p["ticker"] in candidates:
                peers[p["ticker"]] = p["reason"]
            else:
                self._plan_dropped.append(
                    {
                        "where": "valuation.plan",
                        "reason": f"peer {p['ticker']!r} is not a candidate",
                    }
                )
                log.warning("valuation: dropped non-candidate peer %r", p["ticker"])
        if not peers:  # keep the deterministic default rather than compute against nothing
            peers = dict.fromkeys(candidates, "default list (the plan named no usable peer)")
        if "peer_median" in methods and not peers:
            methods.pop("peer_median")
        return {"methods": methods, "peers": peers, "notes": raw.get("notes", "")}

    # --------------------------------------------------------------- step 3 prompt
    def extra_blocks(self, context: dict) -> str:
        calc_lines = "\n".join(
            f"{path} = {'unavailable' if vo['value'] is None else format(vo['value'], '.6g')} "
            f"({vo['unit']}, {vo['type']})"
            for path, vo in sorted(self._calc.items())
        )
        plan = self.plan
        chosen = (
            "methods: "
            + ", ".join(plan.get("methods", {}))
            + "\npeers: "
            + ", ".join(plan.get("peers", {}))
        )
        return (
            "\n\n## YOUR PLAN (already executed; the results are below)\n"
            + chosen
            + "\n\n## CALCULATION RESULTS (from calculate_valuation; cite paths in calc_refs)\n"
            + (calc_lines or "(none)")
            + "\n\n## UPSTREAM FINDINGS (untrusted data)\n"
            + self._fenced("upstream:findings", self._upstream_text)
        )

    # ------------------------------------------------------------------------ run
    def run(self, context: dict, feedback: list[str] | None = None) -> Analysis:
        self.raw_outputs, self._plan_dropped = [], []
        self._upstream_text = context.get("upstream_text", "")
        ticker, as_of = context["ticker"], context["as_of"]

        candidates = {
            p["ticker"]: p
            for p in self.call_tool("get_peer_companies", {"ticker": ticker, "as_of": as_of})[
                "peers"
            ]
        }
        self.plan = self._plan(context, candidates)
        calc = self.call_tool(
            "calculate_valuation",
            {
                "ticker": ticker,
                "methods": list(self.plan["methods"]),
                **({"peer_tickers": list(self.plan["peers"])} if self.plan["peers"] else {}),
            },
        )
        self.set_calc_results(calc)
        plan_flags = list(self.guard_flags)  # base.run resets flags and drops; keep the plan step's
        analysis = super().run(
            context, feedback
        )  # usage keeps accumulating: plan call + interpret call
        self.guard_flags = plan_flags + self.guard_flags
        self.dropped = self._plan_dropped + self.dropped
        analysis.valuation_plan = {  # type: ignore[attr-defined]
            "methods": self.plan["methods"],
            "peers": self.plan["peers"],
            "notes": self.plan["notes"],
            "calc_notes": calc.get("notes", []),
        }
        return analysis

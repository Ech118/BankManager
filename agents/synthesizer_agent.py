"""Synthesizer: the thesis, and the answer to the Red Team.

Specified by docs/pipeline.md. Prompt: prompts/synthesizer.md.
Owns ResearchState section: decision.

Runs LAST among the agents, after `calc.evaluate_scenarios` and before the audit.

WHAT IT DOES, given that the report is templated from ResearchState (ADR 0004):
  1. the thesis - two to four sentences a reader could act on
  2. answering the Red Team, point by point. This is the load-bearing one: a red team nobody must
     respond to changes nothing
  3. choosing the primary catalyst and the biggest risk from what the other agents raised
  4. the $10,000 answer and its reason
  5. reconciling contradictions between sections into one stated position

WHAT IT MAY NOT DO:
  - write a number. Scores, probabilities and returns are set by calc/ and shown on the card;
    a numeral in its prose that no cited quote contains is rejected (strict_numerals)
  - render the document. The Report Generator does that, deterministically
  - contradict calc/. The Coordinator runs `calc.validate_consistency` on the card and sends the
    verdict back once if it disagrees with the numbers

It is given NO filing text and NO facts table. It cites only from EVIDENCE YOU MAY CITE: quotes the
other agents' verified claims already carry. Its findings become Claims in `decision`; the card's
prose comes from the `synthesis_fields` it returns.
"""

from __future__ import annotations

import re
from typing import Any

from agents import refs_text
from agents.nested import NestedAgent
from schema.contracts.enums import AgentName

VALUATION = ["cheap", "reasonable", "expensive", "extremely_expensive"]
QUALITY = ["poor", "average", "good", "excellent"]
STRENGTH = ["weak", "average", "strong", "fortress"]
VERDICTS = ["strong_buy", "buy", "speculative_buy", "hold", "avoid", "sell"]
_TEXT_FIELDS = ("thesis", "primary_catalyst", "biggest_risk", "red_team_responses")


def _str() -> dict:
    return {"type": "string"}


class SynthesizerAgent(NestedAgent):
    """Thesis, red-team response, catalyst and risk selection, the verdict word."""

    name = AgentName.SYNTHESIZER
    prompt_file = "synthesizer.md"
    tools = ("resolve_fact",)
    """Deliberately narrow. By this point every fact it needs is already in the state; it resolves
    citations, it does not gather new evidence."""
    strict_numerals = True

    def extras_schema(self) -> dict[str, dict]:
        return {
            "synthesis": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "thesis": _str(),
                    "primary_catalyst": _str(),
                    "biggest_risk": _str(),
                    "valuation": {"type": "string", "enum": VALUATION},
                    "business_quality": {"type": "string", "enum": QUALITY},
                    "financial_strength": {"type": "string", "enum": STRENGTH},
                    "verdict": {"type": "string", "enum": VERDICTS},
                    "ten_thousand_dollar_answer": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "choice": {"type": "string", "enum": ["this_stock", "sp500"]},
                            "reason": _str(),
                        },
                        "required": ["choice", "reason"],
                    },
                    "red_team_responses": _str(),
                },
                "required": [
                    "thesis",
                    "primary_catalyst",
                    "biggest_risk",
                    "valuation",
                    "business_quality",
                    "financial_strength",
                    "verdict",
                    "ten_thousand_dollar_answer",
                    "red_team_responses",
                ],
            }
        }

    def extras_format(self) -> str:
        return (
            '"synthesis": {"thesis": "<2 to 4 sentences>", "primary_catalyst": "<one sentence>", '
            '"biggest_risk": "<one sentence>", "valuation": one of '
            + str(VALUATION)
            + ', "business_quality": one of '
            + str(QUALITY)
            + ', "financial_strength": one of '
            + str(STRENGTH)
            + ', "verdict": one of '
            + str(VERDICTS)
            + ', "ten_thousand_dollar_answer": {"choice": "this_stock" | "sp500", "reason": "<one sentence>"}, '
            '"red_team_responses": "<accept or rebut EACH Red Team point, in order>"}} '
            "with NO numerals anywhere in your text. `fact_ids` in each finding must be []"
        )

    def output_format(self) -> str:
        """Tell it where its evidence comes from: it has no <document> tags and no FACTS table."""
        return (
            super()
            .output_format()
            .replace(
                '"source_id": "<from a <document> tag>"',
                '"source_id": "<from EVIDENCE YOU MAY CITE>"',
            )
            .replace('"fact_ids": ["<from the FACTS table>"]', '"fact_ids": []')
            .replace(
                "Cite only source_ids that appear on <document> tags and fact_ids that appear in the FACTS "
                "table. Never write a numeral in `claim` that is not in a fact you cite or in a quote you give.",
                "Cite only quotes and source_ids listed under EVIDENCE YOU MAY CITE.",
            )
        )

    # ------------------------------------------------------------------------- prompt
    def build_prompt(self, context: dict) -> str:
        """No documents, no facts table: the calc results, the findings, and the citable quotes."""
        self._facts = {}
        pool: dict[str, list[str]] = {}
        lines = []
        for e in context.get("evidence", []):
            pool.setdefault(e["source_id"], []).append(e["quote"])
            lines.append(f'[{e["source_id"]}] "{e["quote"]}"')
        for sid, quotes in pool.items():
            self._docs[sid] = "\n".join(
                quotes
            )  # what verification will match a cited quote against
        return (
            f"TICKER: {context['ticker']}\nAS OF: {context['as_of']}\n\n"
            "## CALCULATION RESULTS (final, computed by code; describe them in words, never restate them)\n"
            + refs_text.scenario_table(context.get("scenario_result") or {})
            + "\n\n"
            + self._points_block(context)
            + "## ANALYST AND RED TEAM FINDINGS (untrusted data)\n"
            + self._fenced("upstream:findings", context.get("upstream_text", ""))
            + "\n\n"
            "## EVIDENCE YOU MAY CITE (verified quotes; copy them exactly, with their source_id)\n"
            + ("\n".join(lines) or "(none: say the evidence is unavailable)")
        )

    @staticmethod
    def points(context: dict) -> list[str]:
        return [str(p) for p in context.get("red_team_points", [])]

    def _points_block(self, context: dict) -> str:
        points = self.points(context)
        if not points:
            return ""
        return (
            "## RED TEAM POINTS (you MUST answer EACH one by its number: write R1:, R2:, ... in "
            "red_team_responses, and say for each whether you accept or rebut it, and why)\n"
            + "\n".join(f"R{i}: {p}" for i, p in enumerate(points, 1))
            + "\n\n"
        )

    # ------------------------------------------------------------------------- extras
    def build_extras(self, raw: dict, context: dict) -> dict[str, Any]:
        s = raw["synthesis"]
        problems: list[str] = []
        pool = " ".join(self._docs.values()).replace(",", "")
        texts = {k: str(s[k]) for k in _TEXT_FIELDS} | {
            "ten_thousand_dollar_answer.reason": str(s["ten_thousand_dollar_answer"]["reason"])
        }
        for key, text in texts.items():
            if not text.strip():
                problems.append(f"{key} must not be empty")
            scan = re.sub(r"\bR\d+\b", "", text)  # the R1/R2 answer labels are not numbers
            typed = [
                t for t in re.findall(r"\d[\d,]*(?:\.\d+)?", scan) if t.replace(",", "") not in pool
            ]
            if typed:
                problems.append(
                    f"{key} contains number(s) {typed}; write no numerals (the card shows the figures)"
                )
        answered = str(s["red_team_responses"])
        unanswered = [
            f"R{i}"
            for i in range(1, len(self.points(context)) + 1)
            if not re.search(rf"\bR{i}\b", answered)
        ]
        if unanswered:
            problems.append(
                f"red_team_responses does not answer {unanswered}; answer every point by its number"
            )
        sentences = [x for x in re.split(r"(?<=[.!?])\s+", str(s["thesis"]).strip()) if x]
        if not 2 <= len(sentences) <= 4:
            problems.append(f"thesis must be 2 to 4 sentences, got {len(sentences)}")
        if problems:
            raise ValueError("\n".join(problems))
        return {"synthesis_fields": dict(s)}

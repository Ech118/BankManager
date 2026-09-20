"""Agents whose output is {"analysis": {summary, findings}, ...structured extras}.

The scenario agent (a proposal), the red team (a drawdown path and a prior shift) and the
synthesizer (the card's prose) all produce findings that become Claims AND a small structured
object that is not a Claim. The findings go through exactly the same checks as every other
agent's (verbatim quotes, fact ids, no bare numbers); the extras are validated by the subclass and
attached to the Analysis as extra fields, so they travel with the ResearchState.
"""

from __future__ import annotations

import json
from typing import Any

from agents.base import Agent
from schema.contracts.analysis import Analysis


class NestedAgent(Agent):
    """Base for agents that return findings plus structured extras."""

    def extras_schema(self) -> dict[str, dict]:
        """JSON-schema property definitions for the extras (everything except `analysis`)."""
        raise NotImplementedError

    def extras_format(self) -> str:
        """Prose description of the extras for the output-format block of the system prompt."""
        raise NotImplementedError

    def build_extras(self, raw: dict, context: dict) -> dict[str, Any]:
        """Validate the extras and return {attribute_name: value} to attach to the Analysis.

        Raise ValueError with one problem per line: it becomes the model's retry feedback."""
        raise NotImplementedError

    # ---------------------------------------------------------------- schema and prompt
    def wire_schema(self) -> dict:
        extras = self.extras_schema()
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {"analysis": self.analysis_schema(), **extras},
            "required": ["analysis", *extras],
        }

    def output_format(self) -> str:
        return (
            "# Output format for this run\n\n"
            'Return ONE JSON object and nothing else: {"analysis": <ANALYSIS>, '
            + self.extras_format()
            + "}\n\n<ANALYSIS> is:\n\n"
            + super().output_format().split("Return ONE JSON object and nothing else:\n", 1)[1]
        )

    # -------------------------------------------------------------------------- parse
    def _to_analysis(self, res: dict, context: dict) -> Analysis:
        try:
            raw = json.loads(res["text"])
        except json.JSONDecodeError as e:
            raise ValueError(f"output is not valid JSON: {e}") from e
        if not isinstance(raw, dict) or not isinstance(raw.get("analysis"), dict):
            raise ValueError(
                'output must be an object with an "analysis" object and the required extras'
            )
        missing = [k for k in self.extras_schema() if k not in raw]
        if missing:
            raise ValueError(f"missing required field(s): {missing}")
        analysis = super()._to_analysis({**res, "text": json.dumps(raw["analysis"])}, context)
        for name, value in self.build_extras(raw, context).items():
            setattr(analysis, name, value)
        return analysis

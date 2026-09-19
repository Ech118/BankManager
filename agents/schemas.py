"""LLM-facing JSON Schemas (the shapes agents are asked to return).

These are deliberately SIMPLER than schema/*.json: the model never types value
objects or source registries. It returns plain claims, quotes and number_refs;
agents/runner.py turns that into schema-valid analysis.json / scenarios.json.
Only a conservative JSON-Schema subset is used so it is accepted by
output_config.format; stricter checks (quote must be verbatim, probabilities sum
to 1) happen in code after the call.
"""
from __future__ import annotations

TRENDS = ["structurally_positive", "temporarily_positive", "structurally_negative",
          "temporarily_negative", "neutral"]
CONFIDENCE = ["low", "medium", "high"]

EVIDENCE = {
    "type": "object",
    "properties": {"quote": {"type": "string"}, "source_id": {"type": "string"}},
    "required": ["quote", "source_id"],
    "additionalProperties": False,
}


def finding(sections: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "claim": {"type": "string"},
            "trend": {"type": "string", "enum": TRENDS},
            "section": {"type": "string", "enum": sections},
            "evidence": {"type": "array", "items": EVIDENCE},
            "number_refs": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": CONFIDENCE},
        },
        "required": ["claim", "trend", "section", "evidence", "number_refs", "confidence"],
        "additionalProperties": False,
    }


def analysis_out(sections: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "findings": {"type": "array", "items": finding(sections)},
        },
        "required": ["summary", "findings"],
        "additionalProperties": False,
    }


_SCENARIO = {
    "type": "object",
    "properties": {
        "probability": {"type": "number"},
        "horizon_years": {"type": "integer"},
        "revenue_cagr": {"type": "number"},
        "terminal_margin": {"type": "number"},
        "eps_at_horizon": {"type": "number"},
        "exit_multiple": {"type": "number"},
        "rationale": {"type": "string"},
        "evidence": {"type": "array", "items": EVIDENCE},
    },
    "required": ["probability", "horizon_years", "revenue_cagr", "terminal_margin",
                 "eps_at_horizon", "exit_multiple", "rationale", "evidence"],
    "additionalProperties": False,
}


def valuation_out(sections: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "analysis": analysis_out(sections),
            "scenarios": {
                "type": "object",
                "properties": {"bear": _SCENARIO, "base": _SCENARIO, "bull": _SCENARIO},
                "required": ["bear", "base", "bull"],
                "additionalProperties": False,
            },
            "prior_shift": {
                "type": "object",
                "properties": {"value": {"type": "number"}, "reason": {"type": "string"}},
                "required": ["value", "reason"],
                "additionalProperties": False,
            },
        },
        "required": ["analysis", "scenarios", "prior_shift"],
        "additionalProperties": False,
    }


VERDICTS = ["strong_buy", "buy", "speculative_buy", "hold", "avoid", "sell"]

SYNTHESIS_OUT = {
    "type": "object",
    "properties": {
        "thesis": {"type": "string"},
        "primary_catalyst": {"type": "string"},
        "biggest_risk": {"type": "string"},
        "valuation": {"type": "string", "enum": ["cheap", "reasonable", "expensive", "extremely_expensive"]},
        "business_quality": {"type": "string", "enum": ["poor", "average", "good", "excellent"]},
        "financial_strength": {"type": "string", "enum": ["weak", "average", "strong", "fortress"]},
        "verdict": {"type": "string", "enum": VERDICTS},
        "ten_thousand_dollar_answer": {
            "type": "object",
            "properties": {"choice": {"type": "string", "enum": ["this_stock", "sp500"]},
                           "reason": {"type": "string"}},
            "required": ["choice", "reason"],
            "additionalProperties": False,
        },
        "red_team_responses": {"type": "string"},
        "buyability_text": {"type": "string"},
        "buy_more_if": {"type": "array", "items": {"type": "string"}},
        "sell_if": {"type": "array", "items": {"type": "string"}},
        "committee_verdict_text": {"type": "string"},
    },
    "required": ["thesis", "primary_catalyst", "biggest_risk", "valuation", "business_quality",
                 "financial_strength", "verdict", "ten_thousand_dollar_answer",
                 "red_team_responses", "buyability_text", "buy_more_if", "sell_if",
                 "committee_verdict_text"],
    "additionalProperties": False,
}

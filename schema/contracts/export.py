"""Export the pydantic contracts to JSON Schema in schema/*.json.

Run with `make gen-schema`. The models are the source of truth; the JSON is a
GENERATED artifact, committed so that non-Python consumers (web/) and the
jsonschema-based contract tests have something to read.

`tests/contracts/test_schema_export.py` regenerates in memory and fails if the
committed files drift, so the two can never disagree silently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from schema.contracts.analysis import Analysis
from schema.contracts.claims import Claim
from schema.contracts.common import ValueObject
from schema.contracts.facts import FinancialFact
from schema.contracts.factsheet import Factsheet
from schema.contracts.filings import Filing
from schema.contracts.market import CompanyProfile, MarketSnapshot
from schema.contracts.metrics import Metrics
from schema.contracts.scenario_result import ScenarioResult
from schema.contracts.scenarios import Scenarios
from schema.contracts.state import ResearchState
from schema.contracts.tools import TOOL_REQUESTS, TOOL_RESPONSES
from schema.contracts.verdict import Verdict
from schema.contracts.verification import VerificationResult

SCHEMA_DIR = Path(__file__).resolve().parents[1]
BASE_ID = "https://bankmanager.local/schema"

EXPORTS: dict[str, tuple[type[BaseModel], str, str]] = {
    "common.json": (
        ValueObject,
        "Shared definitions",
        "GENERATED from schema/contracts/common.py. The ValueObject and its four "
        "conditional rules, shared by every other contract.",
    ),
    "factsheet.json": (
        Factsheet,
        "Fact sheet",
        "GENERATED from schema/contracts/factsheet.py. PRODUCED BY P1 "
        "(data.api.build_factsheet). Reported values only.",
    ),
    "metrics.json": (
        Metrics,
        "Computed metrics",
        "GENERATED from schema/contracts/metrics.py. PRODUCED BY P2 "
        "(calc.api.compute_metrics). Every leaf computed in code.",
    ),
    "analysis.json": (
        Analysis,
        "Agent analysis",
        "GENERATED from schema/contracts/analysis.py. PRODUCED BY each P3 agent.",
    ),
    "scenarios.json": (
        Scenarios,
        "Valuation scenarios (LLM proposal)",
        "GENERATED from schema/contracts/scenarios.py. PRODUCED BY the P3 Scenario "
        "Agent. Weights are REQUESTS; calc/ bounds them.",
    ),
    "scenario_result.json": (
        ScenarioResult,
        "Scenario result (computed)",
        "GENERATED from schema/contracts/scenario_result.py. PRODUCED BY P2 "
        "(calc.api.evaluate_scenarios). Records every weight clamp and the prior cap.",
    ),
    "audit.json": (
        VerificationResult,
        "Verification result",
        "GENERATED from schema/contracts/verification.py. PRODUCED BY P2 "
        "(audit.api.run_audit).",
    ),
    "verdict.json": (
        Verdict,
        "Final verdict",
        "GENERATED from schema/contracts/verdict.py. PRODUCED BY P3 "
        "(orchestrator.api.run_analysis). Rendered from ResearchState.",
    ),
    "research_state.json": (
        ResearchState,
        "Research state",
        "GENERATED from schema/contracts/state.py. The single object the report is "
        "rendered from (ADR 0004).",
    ),
    "claim.json": (
        Claim,
        "Claim",
        "GENERATED from schema/contracts/claims.py. The unit an agent may assert; "
        "numbers must cite fact_ids.",
    ),
    "financial_fact.json": (
        FinancialFact,
        "Financial fact",
        "GENERATED from schema/contracts/facts.py. The row type of the truth layer.",
    ),
    "filing.json": (
        Filing,
        "Filing",
        "GENERATED from schema/contracts/filings.py. One SEC submission.",
    ),
    "market_snapshot.json": (
        MarketSnapshot,
        "Market snapshot",
        "GENERATED from schema/contracts/market.py. Every field at ONE as_of instant.",
    ),
    "company_profile.json": (
        CompanyProfile,
        "Company profile",
        "GENERATED from schema/contracts/market.py. Identity and SIC classification.",
    ),
}
"""Filename -> (model, title, description). One file per cross-partition artifact."""


def build_schema(model: type[BaseModel], filename: str, title: str, description: str) -> dict[str, Any]:
    """Generate one JSON Schema document with a stable $id and header."""
    body = model.model_json_schema(mode="validation")
    body.pop("title", None)
    body.pop("description", None)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_ID}/{filename}",
        "title": title,
        "description": description,
        **body,
    }


def build_tools_schema() -> dict[str, Any]:
    """One document holding every MCP tool's request and response shape."""
    defs: dict[str, Any] = {}
    tools: dict[str, Any] = {}
    for name in sorted(TOOL_REQUESTS):
        req = TOOL_REQUESTS[name].model_json_schema(mode="validation")
        res = TOOL_RESPONSES[name].model_json_schema(mode="validation")
        for doc in (req, res):
            defs.update(doc.pop("$defs", {}))
        tools[name] = {"request": req, "response": res}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_ID}/tools.json",
        "title": "MCP tools",
        "description": "GENERATED from schema/contracts/tools.py. The ten tools "
        "mcp_server/ exposes. Every data tool requires as_of.",
        "type": "object",
        "properties": tools,
        "$defs": defs,
    }


def render_all() -> dict[str, str]:
    """Return {filename: file content} for every schema, without writing anything."""
    out: dict[str, str] = {}
    for filename, (model, title, description) in EXPORTS.items():
        doc = build_schema(model, filename, title, description)
        out[filename] = json.dumps(doc, indent=2) + "\n"
    out["tools.json"] = json.dumps(build_tools_schema(), indent=2) + "\n"
    return out


def write_all(target: Path | None = None) -> list[Path]:
    """Write every schema to disk. Returns the paths written."""
    directory = target or SCHEMA_DIR
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, content in render_all().items():
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in write_all():
        print(f"wrote {path.relative_to(SCHEMA_DIR.parent)}")

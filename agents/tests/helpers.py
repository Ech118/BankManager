"""Test helpers: build an agent context from the frozen ACME fixtures, and script the model."""

import json
from pathlib import Path

from agents import client
from schema.contracts.enums import AgentName

MOCK = Path(__file__).resolve().parents[2] / "fixtures" / "mock"
MDNA_ID = "src:edgar:0001234567-26-000010:mdna"
QUOTE = "Gross margin improved to 40.0% from 38.9%"


def make_context(extra_text: str = "") -> dict:
    facts = json.loads((MOCK / "facts.json").read_text())
    sections = []
    for name in ("mdna", "sbc_note", "debt_note"):
        text = (MOCK / "sections" / f"{name}.txt").read_text()
        sections.append(
            {
                "section_id": f"sec:0001234567-26-000010:{name}",
                "source_id": f"src:edgar:0001234567-26-000010:{name}",
                "item": name,
                "form": "10-K",
                "fiscal_period": "FY2025",
                "text": text + (extra_text if name == "mdna" else ""),
            }
        )
    return {"ticker": "ACME", "as_of": "2026-09-19", "facts": facts, "sections": sections}


def finding(
    claim="Gross margin expanded on price and mix.",
    quote=QUOTE,
    source_id=MDNA_ID,
    fact_ids=("fact:ACME:revenue:FY2025",),
    section="financials",
    **over,
):
    f = {
        "claim": claim,
        "trend": "temporarily_positive",
        "section": section,
        "evidence": [{"quote": quote, "source_id": source_id}] if quote else [],
        "fact_ids": list(fact_ids),
        "confidence": "medium",
    }
    f.update(over)
    return f


DEFAULT_PLAN = {
    "methods": [{"name": "pe", "reason": "Earnings are representative."}],
    "peers": [{"ticker": "PRAA", "reason": "Kept from the default list."}],
    "notes": "default kept",
}


def script_model(monkeypatch, responder):
    """Replace client.complete. `responder(system, user, attempt) -> dict|str`. Returns the call log."""
    calls = []

    def fake(agent, system, user, max_tokens=4096, schema=None, kind="analysis"):
        calls.append(
            {"agent": agent, "system": system, "user": user, "schema": schema, "kind": kind}
        )
        out = DEFAULT_PLAN if kind == "plan" else responder(system, user, len(calls))
        text = out if isinstance(out, str) else json.dumps(out)
        return {
            "text": text,
            "model": "test-model",
            "tokens_in": 100,
            "tokens_out": 20,
            "seconds": 0.01,
        }

    monkeypatch.setattr(client, "complete", fake)
    return calls


def analysis_payload(*findings, summary="ok"):
    return {"summary": summary, "findings": list(findings)}


FINANCIAL = AgentName.FINANCIAL

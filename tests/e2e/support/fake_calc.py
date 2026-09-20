"""P3-owned TEST DOUBLES for the two things P3 may not import: calc/ and audit/.

They exist so the decision pipeline (scenario -> red team -> calc -> synthesizer -> audit -> report)
can be exercised end to end before P2's v2 port lands. They read the frozen ACME fixtures and apply
only behaviour the docs specify:

  FakeCalc.evaluate_scenarios   rejects weights that do not sum to 1; SUMS the requested prior shifts,
                                caps the sum, and adds it to the base rate (docs/pipeline.md).
                                It does NOT recompute price targets or weights (that is P2's job), so
                                it records what it was asked, for tests to assert on.
  FakeCalc.validate_consistency P2's rules (calc/consistency.py on their branch) on the v2 field names:
                                a bullish verdict below the index assumption, or a bearish verdict
                                more than 5 points above it, is inconsistent.
  simple_auditor                every evidence quote must appear verbatim in its cited text; failures
                                are `unsupported_claim` errors (no retry directives).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

MOCK = Path(__file__).resolve().parents[3] / "fixtures" / "mock"
CAP = 0.15
BULLISH = {"strong_buy", "buy", "speculative_buy"}
BEARISH = {"sell", "avoid"}
BEARISH_EXCESS_CONTRADICTION = 0.05


def _load(name: str) -> dict:
    return json.loads((MOCK / name).read_text(encoding="utf-8"))


def factsheet_provider(context: dict) -> dict:
    return _load("factsheet.json")


def _v(vo: dict | None):
    return None if not vo or vo.get("status") != "ok" else vo.get("value")


class FakeCalc:
    def __init__(self, result: dict | None = None):
        self.result = result
        self.calls: dict[str, list] = {"evaluate_scenarios": [], "validate_consistency": []}

    def compute_metrics(self, factsheet: dict) -> dict:
        return _load("metrics.json")

    def evaluate_scenarios(
        self, scenarios: dict, factsheet: dict, metrics: dict, prior_shifts=None
    ) -> dict:
        total = sum(s["probability"] for s in scenarios["scenarios"].values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Scenario probabilities must sum to 1.0, got {total}")
        self.calls["evaluate_scenarios"].append(
            {"scenarios": scenarios, "prior_shifts": copy.deepcopy(prior_shifts)}
        )
        sr = copy.deepcopy(self.result or _load("scenario_result.json"))
        shifts = prior_shifts if prior_shifts is not None else [scenarios["prior_shift"]]
        requested = sum(s["value"] for s in shifts)
        applied = max(-CAP, min(CAP, requested))
        base = sr["prior"]["base_rate"]
        sr["prior"].update(
            requested_shift=requested,
            applied_shift=applied,
            cap=CAP,
            shift_reasons=[f"{s.get('source', 'scenario')}: {s['reason']}" for s in shifts],
        )
        sr["p_beat_sp500"] = {h: round(min(1.0, max(0.0, base[h] + applied)), 6) for h in base}
        return sr

    def validate_consistency(self, scenario_result: dict, verdict_card: dict) -> dict:
        self.calls["validate_consistency"].append(verdict_card.get("verdict"))
        issues: list[str] = []
        verdict = verdict_card.get("verdict")
        expected = _v(scenario_result.get("expected_annualized_return"))
        index = _v(scenario_result.get("sp500_expected_return"))
        excess = _v((scenario_result.get("expected_return_vs_sp500") or {}).get("long_term"))
        if verdict in BULLISH and expected is not None and index is not None and expected < index:
            issues.append(
                f"verdict '{verdict}' but expected return is below the S&P 500 assumption"
            )
        if verdict in BEARISH and excess is not None and excess > BEARISH_EXCESS_CONTRADICTION:
            issues.append(
                f"verdict '{verdict}' despite excess return {excess:.3f} well above the S&P 500"
            )
        return {"ok": not issues, "issues": issues}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def simple_auditor(state: dict, factsheet: dict, get_text, verify_claim=None) -> dict:
    """A stand-in for audit.run_audit: every evidence quote must appear in the text it cites."""
    issues, checked = [], 0
    for key, section in state["sections"].items():
        for claim in section["claims"]:
            checked += 1
            for ev in claim["evidence"]:
                try:
                    text = _norm(get_text(ev["source_id"]))
                except KeyError:
                    text = ""
                if _norm(ev["quote"]) not in text:
                    issues.append(
                        {
                            "issue_type": "unsupported_claim",
                            "severity": "error",
                            "path": f"sections.{key}",
                            "message": "quote not found in its source",
                            "claim_id": claim["claim_id"],
                            "section_id": None,
                            "checked_by_llm": False,
                        }
                    )
                    break
    bad = len({i["claim_id"] for i in issues})
    return {
        "schema_version": "2.0.0",
        "passed": not issues,
        "issues": issues,
        "claims_checked": checked,
        "claims_verified": checked - bad,
        "claims_unverified": bad,
        "llm_checks_run": 0,
        "retries_issued": [],
    }

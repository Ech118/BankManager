"""The committed schema/*.json must match the pydantic models exactly.

The models in schema/contracts/ are the source of truth. This test regenerates
every schema in memory and compares it byte for byte with what is on disk, so
the two can never drift apart silently. If it fails, run `make gen-schema`.
"""

import pytest
from helpers import SCHEMA_DIR

from schema.contracts.export import EXPORTS, render_all

RENDERED = render_all()


@pytest.mark.parametrize("filename", sorted(RENDERED))
def test_committed_schema_matches_the_models(filename):
    path = SCHEMA_DIR / filename
    assert path.exists(), f"{filename} is missing; run `make gen-schema`"
    on_disk = path.read_text(encoding="utf-8")
    assert on_disk == RENDERED[filename], (
        f"{filename} is out of date with schema/contracts/. Run `make gen-schema` "
        "and commit the result."
    )


def test_no_orphan_schema_files():
    """Every schema/*.json must be produced by the exporter, not hand-written."""
    on_disk = {p.name for p in SCHEMA_DIR.glob("*.json")}
    assert on_disk == set(RENDERED), (
        f"unexpected schema files: {sorted(on_disk - set(RENDERED))}; "
        f"missing: {sorted(set(RENDERED) - on_disk)}"
    )


def test_every_artifact_has_an_export():
    """A new cross-partition artifact must ship a schema for non-Python consumers."""
    expected = {
        "common.json", "factsheet.json", "metrics.json", "analysis.json",
        "scenarios.json", "scenario_result.json", "audit.json", "verdict.json",
        "research_state.json", "claim.json", "financial_fact.json", "filing.json",
        "market_snapshot.json", "company_profile.json",
    }
    assert expected <= set(EXPORTS), sorted(expected - set(EXPORTS))

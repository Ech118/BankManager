"""Schema loading and fixture-walking helpers.

Shared by every contract test. Updated for contract v2.0.0: the pydantic models
in schema/contracts/ are the source of truth and schema/*.json is generated from
them, so fixtures are checked BOTH ways - against the generated JSON Schema and
against the models themselves.
"""

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schema"
MOCK_DIR = ROOT / "fixtures" / "mock"

# Object-shaped fixtures, validated against a generated JSON Schema file.
FIXTURE_SCHEMAS = {
    "factsheet.json": "factsheet.json",
    "metrics.json": "metrics.json",
    "scenarios.json": "scenarios.json",
    "scenario_result.json": "scenario_result.json",
    "analysis_financial.json": "analysis.json",
    "analysis_business.json": "analysis.json",
    "analysis_valuation.json": "analysis.json",
    "analysis_red_team.json": "analysis.json",
    "audit.json": "audit.json",
    "verdict.json": "verdict.json",
    "research_state.json": "research_state.json",
    "market_snapshot.json": "market_snapshot.json",
    "company_profile.json": "company_profile.json",
}

# List-shaped fixtures (and ScenarioWeights, which has no standalone schema
# file). These are validated with pydantic in test_models.py instead.
MODEL_ONLY_FIXTURES = {
    "facts.json",
    "filings.json",
    "peers.json",
    "scenario_weights_clamped.json",
}

ALL_FIXTURES = set(FIXTURE_SCHEMAS) | MODEL_ONLY_FIXTURES


def _registry():
    resources = []
    for p in SCHEMA_DIR.glob("*.json"):
        s = json.loads(p.read_text(encoding="utf-8"))
        resources.append((s["$id"], Resource.from_contents(s)))
    return Registry().with_resources(resources)


_REG = _registry()


def load_schema(name):
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validator(schema_name):
    return Draft202012Validator(load_schema(schema_name), registry=_REG)


def validation_errors(obj, schema_name):
    errs = sorted(validator(schema_name).iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [
        f"{'/'.join(str(x) for x in e.absolute_path) or '<root>'}: {e.message[:200]}"
        for e in errs
    ]


def load_fixture(name):
    return json.loads((MOCK_DIR / name).read_text(encoding="utf-8"))


def is_value_object(x):
    return isinstance(x, dict) and {"value", "unit", "type", "status"} <= set(x)


def walk(obj, path=""):
    """Yield (path, node) for every dict/list node."""
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def value_objects(obj):
    return [(p, n) for p, n in walk(obj) if is_value_object(n)]


def evidence_items(obj):
    return [
        (p, n)
        for p, n in walk(obj)
        if isinstance(n, dict) and set(n) >= {"quote", "source_id"}
    ]


def norm(text):
    return re.sub(r"\s+", " ", text).strip()

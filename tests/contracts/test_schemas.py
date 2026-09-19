"""Rule 1: every mock fixture validates against its generated JSON Schema."""

import pytest
from helpers import (
    ALL_FIXTURES,
    FIXTURE_SCHEMAS,
    MOCK_DIR,
    SCHEMA_DIR,
    load_fixture,
    load_schema,
    validation_errors,
)
from jsonschema import Draft202012Validator


@pytest.mark.parametrize("schema_file", sorted(p.name for p in SCHEMA_DIR.glob("*.json")))
def test_schema_is_valid_json_schema(schema_file):
    Draft202012Validator.check_schema(load_schema(schema_file))


@pytest.mark.parametrize("fixture,schema", sorted(FIXTURE_SCHEMAS.items()))
def test_fixture_validates(fixture, schema):
    errors = validation_errors(load_fixture(fixture), schema)
    assert not errors, "\n".join(errors)


def test_every_mock_json_is_covered():
    on_disk = {p.name for p in MOCK_DIR.glob("*.json")}
    assert on_disk == ALL_FIXTURES, (
        "Add new mock fixtures to FIXTURE_SCHEMAS or MODEL_ONLY_FIXTURES in "
        "tests/contracts/helpers.py (coordinator only)."
    )


def test_every_schema_has_a_stable_id():
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        schema = load_schema(path.name)
        assert schema["$id"].endswith(f"/{path.name}"), path.name
        assert schema["description"].startswith("GENERATED"), (
            f"{path.name}: schema/*.json is generated from schema/contracts/; "
            "run `make gen-schema` rather than hand-editing it"
        )

"""Rule 1: every mock fixture validates against its schema. FROZEN (Step 0)."""
import pytest
from helpers import FIXTURE_SCHEMAS, MOCK_DIR, SCHEMA_DIR, load_fixture, load_schema, validation_errors
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
    assert on_disk == set(FIXTURE_SCHEMAS), (
        "Add new mock fixtures to FIXTURE_SCHEMAS in tests/contracts/helpers.py (coordinator only).")


def test_value_object_rejects_bad_data():
    ok = {"value": 1.0, "unit": "usd", "type": "fact", "status": "ok", "source_id": "src:market:quote"}
    schema = {"$ref": "https://bankmanager.local/schema/common.json#/$defs/value"}
    from helpers import _REG
    v = Draft202012Validator(schema, registry=_REG)
    assert not list(v.iter_errors(ok))
    assert list(v.iter_errors({**ok, "value": None}))                      # ok needs a number
    assert list(v.iter_errors({**ok, "source_id": None}))                  # ok needs source or derived_from
    assert list(v.iter_errors({**ok, "status": "unavailable"}))            # unavailable needs null value
    assert not list(v.iter_errors({**ok, "value": None, "status": "unavailable", "source_id": None}))
    assert list(v.iter_errors({**ok, "unit": "percent"}))                  # unknown unit

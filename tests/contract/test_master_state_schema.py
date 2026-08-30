import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = Path(__file__).parent.parent.parent / "schemas" / "master-state-v1.schema.json"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_schema_file_exists():
    assert SCHEMA_PATH.is_file(), f"Schema file not found at {SCHEMA_PATH}"


@pytest.fixture
def master_schema():
    assert SCHEMA_PATH.is_file(), f"Schema file not found at {SCHEMA_PATH}"
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def test_valid_synthetic_master_state(master_schema):
    fixture_file = FIXTURES_DIR / "master-state-v1.synthetic.json"
    assert fixture_file.is_file(), f"Synthetic fixture not found at {fixture_file}"
    with open(fixture_file, encoding="utf-8") as f:
        data = json.load(f)

    validator = jsonschema.Draft202012Validator(master_schema)
    validator.validate(data)


@pytest.mark.parametrize(
    "mutator,expected_error",
    [
        (lambda d: d.update({"schema_version": 2}), "schema_version"),
        (lambda d: d["identity"].update({"auth_server_url": "https://attacker.com"}), "auth_server_url"),
        (lambda d: d["identity"].update({"auth_server_url": "http://auth.samsungosp.com"}), "auth_server_url"),
        (lambda d: d.pop("generation"), "generation"),
        (lambda d: d.update({"extra_top_level": "value"}), "extra_top_level"),
        (lambda d: d["account"].update({"extra_account": "value"}), "extra_account"),
        (lambda d: d.update({"schema": "io.github.other.schema"}), "schema"),
    ],
)
def test_invalid_master_state_variations(master_schema, mutator, expected_error):
    fixture_file = FIXTURES_DIR / "master-state-v1.synthetic.json"
    with open(fixture_file, encoding="utf-8") as f:
        data = json.load(f)

    mutator(data)
    validator = jsonschema.Draft202012Validator(master_schema)
    errors = list(validator.iter_errors(data))
    assert len(errors) > 0, f"Expected validation failure for variation modifying {expected_error}"


def test_fixture_contains_no_real_secrets():
    fixture_file = FIXTURES_DIR / "master-state-v1.synthetic.json"
    if not fixture_file.is_file():
        pytest.fail("Fixture file not found")
    content = fixture_file.read_text(encoding="utf-8")
    assert "synthetic" in content or "example" in content or "test" in content
    assert "ghp_" not in content
    assert "eyJ" not in content  # no real JWTs

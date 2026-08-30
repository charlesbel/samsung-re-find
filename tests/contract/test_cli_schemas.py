import json
from pathlib import Path

import jsonschema
import pytest

from samsung_find.serialization import serialize_error, serialize_response

SCHEMAS_DIR = Path(__file__).parent.parent.parent / "schemas" / "cli" / "v1"


@pytest.fixture
def envelope_schema():
    schema_file = SCHEMAS_DIR / "cli-response-envelope.schema.json"
    assert schema_file.is_file(), f"Envelope schema file not found at {schema_file}"
    with open(schema_file, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def test_success_envelope_schema_validation(envelope_schema):
    payload = serialize_response(
        data={"devices": [{"name": "Galaxy S24", "model": "SM-S928B"}]},
        meta={"count": 1},
    )
    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is True
    assert payload["schema_version"] == "1.0"
    assert payload["data"]["devices"][0]["name"] == "Galaxy S24"


def test_error_envelope_schema_validation(envelope_schema):
    payload = serialize_error(
        code="auth_required",
        message="Authentication required: run 'samsung-find auth-start'",
    )
    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is False
    assert payload["schema_version"] == "1.0"
    assert payload["error"]["code"] == "auth_required"

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from samsung_find.cli import main
from samsung_find.models import Device, DeviceCapabilities, LocationResult, OperationResult
from samsung_find.serialization import serialize_error, serialize_response

SCHEMAS_DIR = Path(__file__).parent.parent.parent / "schemas" / "cli" / "v1"


def _load_schema(filename: str) -> dict[str, Any]:
    schema_file = SCHEMAS_DIR / filename
    assert schema_file.is_file(), f"Schema file not found at {schema_file}"
    with open(schema_file, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


@pytest.fixture
def envelope_schema() -> dict[str, Any]:
    return _load_schema("cli-response-envelope.schema.json")


@pytest.fixture
def capabilities_schema() -> dict[str, Any]:
    return _load_schema("capabilities-response.schema.json")


@pytest.fixture
def location_schema() -> dict[str, Any]:
    return _load_schema("location-response.schema.json")


@pytest.fixture
def operation_schema() -> dict[str, Any]:
    return _load_schema("operation-response.schema.json")


@pytest.fixture
def devices_schema() -> dict[str, Any]:
    return _load_schema("devices-response.schema.json")


@pytest.fixture
def status_schema() -> dict[str, Any]:
    return _load_schema("status-response.schema.json")


class SyntheticMockService:
    """Mock FindService returning well-formed synthetic domain models."""

    def close(self) -> None:
        pass

    def list_devices(self, *, include_ids: bool = False) -> list[Device]:
        return [
            Device(
                name="Galaxy S24 Ultra",
                id="synthetic-dev-id-1" if include_ids else None,
                model="SM-S928B",
                location_type="1",
                device_type="PHONE",
            )
        ]

    def get_capabilities(self, query: str) -> DeviceCapabilities:
        return DeviceCapabilities(
            can_ring=True,
            can_track=True,
            can_locate=True,
            can_check_connection=True,
            passive_location=True,
            active_location=True,
            battery_status=True,
        )

    def get_last_location(self, query: str) -> LocationResult:
        return LocationResult(
            latitude=37.7749,
            longitude=-122.4194,
            accuracy_m=12.5,
            timestamp="2026-08-30T12:00:00+00:00",
            is_fresh=False,
            is_precise=True,
            map_url="https://maps.google.com/?q=37.7749,-122.4194",
            address="San Francisco, CA",
        )

    def request_location(self, query: str, *, poll_seconds: int = 180) -> LocationResult:
        return LocationResult(
            latitude=37.7749,
            longitude=-122.4194,
            accuracy_m=5.0,
            timestamp="2026-08-30T12:00:00+00:00",
            is_fresh=True,
            is_precise=True,
            map_url="https://maps.google.com/?q=37.7749,-122.4194",
            active_refresh_requested=True,
            address="San Francisco, CA",
        )

    def check_connection(self, query: str, *, poll_seconds: int = 40) -> OperationResult:
        return OperationResult(
            operation="CHECK_CONNECTION",
            accepted=True,
            success=True,
            request_id="req-synthetic-check",
            status_code="200",
            battery="85",
            message="Device is reachable",
        )

    def ring(
        self,
        query: str,
        *,
        status: str = "start",
        message: str | None = None,
        poll_seconds: int = 40,
    ) -> OperationResult:
        return OperationResult(
            operation="RING",
            accepted=True,
            success=True,
            request_id="req-synthetic-ring",
            status_code="200",
            message="Ring initiated",
        )

    def set_tracking(
        self,
        query: str,
        *,
        enabled: bool = True,
        poll_seconds: int = 30,
    ) -> OperationResult:
        return OperationResult(
            operation="TRACK_LOCATION_START" if enabled else "TRACK_LOCATION_STOP",
            accepted=True,
            success=True,
            request_id="req-synthetic-track",
            status_code="2100",
            message="Tracking mode set",
        )


class SyntheticMockAuth:
    """Mock SamsungAuth returning synthetic authentication status."""

    def close(self) -> None:
        pass

    def public_status(self) -> dict[str, Any]:
        return {
            "authenticated": True,
            "user_id_present": True,
            "device_id_present": True,
            "find_token_present": True,
            "iot_token_present": True,
        }

    def account_status(self) -> dict[str, bool | int]:
        return {
            "authenticated": True,
            "user_id_present": True,
            "device_id_present": True,
            "schema_version": 1,
        }


def test_cli_account_status_reports_only_shared_master_readiness(capsys, envelope_schema):
    ret = main(["account-status"], auth=SyntheticMockAuth())  # type: ignore[arg-type]
    assert ret == 0

    payload = json.loads(capsys.readouterr().out)
    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["data"] == {
        "authenticated": True,
        "user_id_present": True,
        "device_id_present": True,
        "schema_version": 1,
    }


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
        message="Authentication required: run 'samsung-re-find auth-start'",
    )
    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is False
    assert payload["schema_version"] == "1.0"
    assert payload["error"]["code"] == "auth_required"


def test_cli_capabilities_contract(capsys, envelope_schema, capabilities_schema):
    service = SyntheticMockService()
    ret = main(["capabilities", "Galaxy S24"], service=service)
    assert ret == 0

    out = capsys.readouterr().out
    payload = json.loads(out)

    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is True
    jsonschema.Draft202012Validator(capabilities_schema).validate(payload["data"])
    assert payload["data"]["can_ring"] is True
    assert payload["data"]["can_track"] is True
    assert payload["data"]["can_locate"] is True
    assert payload["data"]["can_check_connection"] is True


def test_cli_capabilities_legacy_json_contract(capsys, capabilities_schema):
    service = SyntheticMockService()
    ret = main(["--legacy-json", "capabilities", "Galaxy S24"], service=service)
    assert ret == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    jsonschema.Draft202012Validator(capabilities_schema).validate(payload)


@pytest.mark.parametrize(
    "argv,is_fresh",
    [
        (["locate", "Galaxy S24"], True),
        (["locate", "Galaxy S24", "--passive"], False),
    ],
)
def test_cli_location_contract(capsys, envelope_schema, location_schema, argv, is_fresh):
    service = SyntheticMockService()
    ret = main(argv, service=service)
    assert ret == 0

    out = capsys.readouterr().out
    payload = json.loads(out)

    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is True
    jsonschema.Draft202012Validator(location_schema).validate(payload["data"])
    assert payload["data"]["latitude"] == 37.7749
    assert payload["data"]["longitude"] == -122.4194
    assert payload["data"]["is_fresh"] is is_fresh
    assert payload["data"]["is_precise"] is True


@pytest.mark.parametrize(
    "argv,expected_op",
    [
        (["check", "Galaxy S24"], "CHECK_CONNECTION"),
        (["ring", "Galaxy S24", "--yes"], "RING"),
        (["track", "Galaxy S24", "start", "--yes"], "TRACK_LOCATION_START"),
    ],
)
def test_cli_operation_contract(capsys, envelope_schema, operation_schema, argv, expected_op):
    service = SyntheticMockService()
    ret = main(argv, service=service)
    assert ret == 0

    out = capsys.readouterr().out
    payload = json.loads(out)

    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is True
    jsonschema.Draft202012Validator(operation_schema).validate(payload["data"])
    assert payload["data"]["operation"] == expected_op
    assert payload["data"]["success"] is True


@pytest.mark.parametrize("include_ids", [False, True])
def test_cli_devices_contract(capsys, envelope_schema, devices_schema, include_ids):
    service = SyntheticMockService()
    argv = ["devices", "--include-ids"] if include_ids else ["devices"]
    ret = main(argv, service=service)
    assert ret == 0

    out = capsys.readouterr().out
    payload = json.loads(out)

    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is True
    jsonschema.Draft202012Validator(devices_schema).validate(payload["data"])
    assert len(payload["data"]) == 1
    assert payload["data"][0]["name"] == "Galaxy S24 Ultra"
    if include_ids:
        assert payload["data"][0]["id"] == "synthetic-dev-id-1"
    else:
        assert "id" not in payload["data"][0]


def test_cli_status_contract(capsys, envelope_schema, status_schema):
    auth = SyntheticMockAuth()
    ret = main(["status"], auth=auth)
    assert ret == 0

    out = capsys.readouterr().out
    payload = json.loads(out)

    jsonschema.Draft202012Validator(envelope_schema).validate(payload)
    assert payload["ok"] is True
    jsonschema.Draft202012Validator(status_schema).validate(payload["data"])
    assert payload["data"]["authenticated"] is True

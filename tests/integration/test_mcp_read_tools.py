from unittest.mock import MagicMock

import pytest

from samsung_find.mcp_server import create_mcp_server, execute_tool
from samsung_find.models import Device, DeviceCapabilities, LocationResult, OperationResult


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.list_devices.return_value = [
        Device(
            id="synthetic-dev-1",
            name="Galaxy S24",
            model="SM-S928B",
            location_type="precise",
        )
    ]
    service.get_capabilities.return_value = DeviceCapabilities(
        can_ring=True, can_track=False, can_locate=True, can_check_connection=True
    )
    service.get_last_location.return_value = LocationResult(
        latitude=48.8566,
        longitude=2.3522,
        accuracy_m=10.0,
        is_fresh=True,
        timestamp="2026-08-30T12:00:00Z",
    )
    service.check_connection.return_value = OperationResult(
        operation="CHECK_CONNECTION",
        success=True,
        battery="85",
    )
    return service


def test_mcp_list_devices_tool(mock_service):
    server = create_mcp_server(service=mock_service)
    result = execute_tool(server, "samsung_find_list_devices", {})
    assert result["ok"] is True
    assert len(result["data"]) == 1
    assert result["data"][0]["name"] == "Galaxy S24"
    assert result["data"][0]["model"] == "SM-S928B"


def test_mcp_get_capabilities_tool(mock_service):
    server = create_mcp_server(service=mock_service)
    result = execute_tool(server, "samsung_find_get_capabilities", {"query": "Galaxy S24"})
    assert result["ok"] is True
    assert result["data"]["can_ring"] is True
    assert result["data"]["can_track"] is False


def test_mcp_get_last_location_tool(mock_service):
    server = create_mcp_server(service=mock_service)
    result = execute_tool(server, "samsung_find_get_last_location", {"query": "Galaxy S24"})
    assert result["ok"] is True
    assert result["data"]["latitude"] == 48.8566
    assert result["data"]["longitude"] == 2.3522
    assert result["data"]["is_fresh"] is True


def test_mcp_check_connection_tool(mock_service):
    server = create_mcp_server(service=mock_service)
    result = execute_tool(server, "samsung_find_check_connection", {"query": "Galaxy S24"})
    assert result["ok"] is True
    assert result["data"]["battery"] == "85"
    assert result["data"]["success"] is True


@pytest.mark.parametrize(
    "invalid_query",
    [
        "",
        "   ",
        "a" * 300,  # too long (>256)
    ],
)
def test_mcp_query_bounds_validation(mock_service, invalid_query):
    server = create_mcp_server(service=mock_service)
    result = execute_tool(server, "samsung_find_get_capabilities", {"query": invalid_query})
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_parameter"


@pytest.mark.parametrize("invalid_poll", [-1, 0, 700, "fast"])
def test_mcp_poll_seconds_bounds_validation(mock_service, invalid_poll):
    server = create_mcp_server(service=mock_service)
    result = execute_tool(
        server,
        "samsung_find_request_location",
        {"query": "Galaxy S24", "poll_seconds": invalid_poll},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_parameter"


def test_mcp_sanitizes_generic_exceptions(mock_service):
    mock_service.list_devices.side_effect = RuntimeError("sensitive internal database trace /tmp/secret")
    server = create_mcp_server(service=mock_service)
    result = execute_tool(server, "samsung_find_list_devices", {})
    assert result["ok"] is False
    assert result["error"]["code"] == "internal_error"
    assert "sensitive" not in result["error"]["message"]
    assert "internal" in result["error"]["message"].lower()

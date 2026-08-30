from unittest.mock import MagicMock

import pytest

from samsung_find.mcp_server import create_mcp_server, execute_tool
from samsung_find.models import OperationResult


def test_mcp_effects_gated_by_default():
    mock_service = MagicMock()
    server = create_mcp_server(service=mock_service, allow_effects=frozenset())

    # Ring tool should fail / not be executable
    result = execute_tool(
        server,
        "samsung_find_ring",
        {"query": "synthetic-test-device", "status": "start", "confirm": True},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "effect_disabled"
    assert mock_service.ring.call_count == 0


@pytest.mark.parametrize(
    "invalid_confirm",
    [
        {},  # missing confirm
        {"confirm": False},  # confirm is false
        {"confirm": "true"},  # non-boolean string
        {"confirm": 1},  # non-boolean int
        {"confirm": None},
    ],
)
def test_mcp_effects_require_explicit_confirm_true(invalid_confirm):
    mock_service = MagicMock()
    server = create_mcp_server(service=mock_service, allow_effects=frozenset({"ring", "tracking"}))

    args = {"query": "synthetic-test-device", "status": "start", **invalid_confirm}
    result = execute_tool(server, "samsung_find_ring", args)
    assert result["ok"] is False
    assert result["error"]["code"] == "confirmation_required"
    assert mock_service.ring.call_count == 0

    track_args = {"query": "synthetic-test-device", "enabled": True, **invalid_confirm}
    track_result = execute_tool(server, "samsung_find_set_tracking", track_args)
    assert track_result["ok"] is False
    assert track_result["error"]["code"] == "confirmation_required"
    assert mock_service.set_tracking.call_count == 0


def test_mcp_effects_executable_when_allowed_and_confirmed():
    mock_service = MagicMock()
    mock_service.ring.return_value = OperationResult(
        operation="RING",
        success=True,
        request_id="synthetic-test-ring-req-1",
    )
    server = create_mcp_server(service=mock_service, allow_effects=frozenset({"ring"}))

    result = execute_tool(
        server,
        "samsung_find_ring",
        {"query": "synthetic-test-device", "status": "start", "confirm": True},
    )
    assert result["ok"] is True
    assert result["data"]["operation"] == "RING"
    assert mock_service.ring.call_count == 1

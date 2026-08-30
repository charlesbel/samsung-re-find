from unittest.mock import MagicMock

from samsung_find.mcp_server import create_mcp_server, execute_tool
from samsung_find.models import OperationResult


def test_mcp_effects_gated_by_default():
    mock_service = MagicMock()
    server = create_mcp_server(service=mock_service, allow_effects=frozenset())

    # Ring tool should fail / not be executable
    result = execute_tool(server, "samsung_find_ring", {"query": "Tag", "status": "start"})
    assert result["ok"] is False
    assert result["error"]["code"] == "effect_disabled"
    assert mock_service.ring.call_count == 0


def test_mcp_effects_executable_when_explicitly_allowed():
    mock_service = MagicMock()
    mock_service.ring.return_value = OperationResult(
        operation="RING",
        success=True,
        request_id="req-ring-1",
    )
    server = create_mcp_server(service=mock_service, allow_effects=frozenset({"ring"}))

    result = execute_tool(server, "samsung_find_ring", {"query": "Tag", "status": "start"})
    assert result["ok"] is True
    assert result["data"]["operation"] == "RING"
    assert mock_service.ring.call_count == 1

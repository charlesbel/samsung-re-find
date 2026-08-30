import json
import os
import queue
import subprocess
import sys
import threading
from unittest.mock import MagicMock

import pytest

from samsung_find.mcp_server import create_mcp_server
from samsung_find.models import Device, DeviceCapabilities, LocationResult, OperationResult
from samsung_find.service import FindService


def test_mcp_server_direct_protocol_and_id_inclusion():
    mock_service = MagicMock(spec=FindService)
    mock_service.list_devices.return_value = [
        Device(name="Galaxy S24", id="secret-device-id-999", model="SM-S928B", location_type="PHONE"),
    ]
    mock_service.get_capabilities.return_value = DeviceCapabilities(
        can_ring=True, can_track=True, can_locate=True, can_check_connection=True, battery_status=True
    )
    mock_service.get_last_location.return_value = LocationResult(
        latitude=48.8566, longitude=2.3522, accuracy_m=10.0, is_fresh=True, is_precise=True
    )
    mock_service.ring.return_value = OperationResult(operation="RING", accepted=True, success=True)

    server = create_mcp_server(service=mock_service, allow_effects={"ring"})

    # 1. Test list_devices without include_ids (default)
    res_no_ids = server.call_tool("samsung_find_list_devices", {})
    assert res_no_ids["ok"] is True
    data_no_ids = res_no_ids["data"]
    assert len(data_no_ids) == 1
    assert "id" not in data_no_ids[0]
    mock_service.list_devices.assert_called_with(include_ids=False)

    # 2. Test list_devices with include_ids=True
    mock_service.list_devices.reset_mock()
    res_with_ids = server.call_tool("samsung_find_list_devices", {"include_ids": True})
    assert res_with_ids["ok"] is True
    data_with_ids = res_with_ids["data"]
    assert len(data_with_ids) == 1
    assert data_with_ids[0]["id"] == "secret-device-id-999"
    mock_service.list_devices.assert_called_with(include_ids=True)

    # 3. Test get_capabilities
    res_caps = server.call_tool("samsung_find_get_capabilities", {"query": "Galaxy S24"})
    assert res_caps["ok"] is True
    assert res_caps["data"]["can_ring"] is True

    # 4. Test effect tool without confirmation
    res_ring_no_conf = server.call_tool("samsung_find_ring", {"query": "Galaxy S24"})
    assert res_ring_no_conf["ok"] is False
    assert res_ring_no_conf["error"]["code"] == "confirmation_required"

    # 5. Test effect tool with confirmation
    res_ring_conf = server.call_tool("samsung_find_ring", {"query": "Galaxy S24", "confirm": True})
    assert res_ring_conf["ok"] is True
    assert res_ring_conf["data"]["operation"] == "RING"


def test_mcp_server_translates_device_not_found_error():
    from samsung_find.exceptions import DeviceNotFoundError

    mock_service = MagicMock(spec=FindService)
    mock_service.get_last_location.side_effect = DeviceNotFoundError("No device matched 'NonExistent'")

    server = create_mcp_server(service=mock_service)
    res = server.call_tool("samsung_find_get_last_location", {"query": "NonExistent"})

    assert res["ok"] is False
    assert res["error"]["code"] == "device_not_found"
    assert "No device matched" in res["error"]["message"]


@pytest.mark.parametrize("invalid", ["false", 0, 1, None, [], {}])
def test_mcp_include_ids_requires_exact_boolean(invalid):
    mock_service = MagicMock(spec=FindService)
    server = create_mcp_server(service=mock_service)

    result = server.call_tool("samsung_find_list_devices", {"include_ids": invalid})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_parameter"
    mock_service.list_devices.assert_not_called()


def test_official_mcp_stdio_negotiation_and_tool_contracts(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    proc = subprocess.Popen(
        [sys.executable, "-m", "samsung_find.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    def send(message):
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def receive(timeout=10):
        stdout = proc.stdout
        assert stdout is not None
        lines = queue.Queue(maxsize=1)
        threading.Thread(target=lambda: lines.put(stdout.readline()), daemon=True).start()
        try:
            line = lines.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("timed out waiting for MCP response") from exc
        assert line, proc.stderr.read() if proc.stderr is not None else "MCP stdout closed"
        return json.loads(line)

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "synthetic-audit-client", "version": "1.0"},
                },
            }
        )
        initialized = receive()
        assert initialized["id"] == 1
        assert initialized["result"]["protocolVersion"]

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = receive()
        assert listed["id"] == 2
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        assert tools
        for tool in tools.values():
            assert tool["inputSchema"]["additionalProperties"] is False
            assert tool["annotations"] == {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            }
        assert tools["samsung_find_list_devices"]["inputSchema"]["properties"]["include_ids"]["type"] == "boolean"
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


def test_mcp_server_fails_closed_on_unsupported_sdk_version(monkeypatch):
    import importlib.metadata

    from samsung_find.mcp_server import main

    monkeypatch.setattr(importlib.metadata, "version", lambda pkg: "9.9.9" if pkg == "mcp" else "1.0")
    with pytest.raises(RuntimeError, match="Unsupported MCP SDK version: 9.9.9"):
        main([])


def test_mcp_server_fails_closed_on_internal_structure_mismatch(monkeypatch):
    import mcp.server.fastmcp

    from samsung_find.mcp_server import main

    original_fastmcp = mcp.server.fastmcp.FastMCP

    class BrokenFastMCP(original_fastmcp):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            del self._tool_manager

    monkeypatch.setattr(mcp.server.fastmcp, "FastMCP", BrokenFastMCP)
    with pytest.raises(RuntimeError, match="MCP SDK internal structure mismatch"):
        main([])

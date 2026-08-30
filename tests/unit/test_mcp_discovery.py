from samsung_find.mcp_server import create_mcp_server, get_registered_tool_names


def test_mcp_server_initialization_default_read_only():
    server = create_mcp_server(allow_effects=frozenset())
    tool_names = get_registered_tool_names(server)

    expected_read_tools = {
        "samsung_find_status",
        "samsung_find_list_devices",
        "samsung_find_get_capabilities",
        "samsung_find_get_last_location",
        "samsung_find_request_location",
        "samsung_find_check_connection",
    }
    for tool in expected_read_tools:
        assert tool in tool_names, f"Expected read-only tool {tool} not found"

    # Side-effect tools must NOT be present by default
    assert "samsung_find_ring" not in tool_names
    assert "samsung_find_set_tracking" not in tool_names


def test_mcp_server_with_effects_enabled():
    server = create_mcp_server(allow_effects=frozenset({"ring", "tracking"}))
    tool_names = get_registered_tool_names(server)

    assert "samsung_find_ring" in tool_names
    assert "samsung_find_set_tracking" in tool_names

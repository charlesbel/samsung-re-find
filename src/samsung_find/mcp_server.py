"""Samsung Find Stdio Model Context Protocol (MCP) Server."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Set
from typing import Any

from .config import FindConfig
from .credentials import MasterStateStore
from .exceptions import (
    AuthError,
    DeviceNotFoundError,
    NetworkError,
    OperationError,
    RateLimitError,
    SecurityError,
    StorageError,
)
from .serialization import serialize_error, serialize_response, to_serializable
from .service import FindService


class SamsungFindMCPServer:
    """In-process MCP Server adapter for Samsung Find."""

    def __init__(
        self,
        service: FindService | None = None,
        config: FindConfig | None = None,
        allow_effects: Set[str] = frozenset(),
    ):
        self.config = config or FindConfig()
        self._service = service
        self.allow_effects = frozenset(s.lower().strip() for s in allow_effects)
        self._tools: dict[str, dict[str, Any]] = {}
        self._register_tools()

    def get_service(self) -> FindService:
        if self._service is None:
            self._service = FindService.from_config(self.config)
        return self._service

    def _register_tools(self) -> None:
        self._tools["samsung_find_status"] = {
            "name": "samsung_find_status",
            "description": "Check local Samsung Account authentication state and validity.",
            "parameters": {},
            "handler": self._handle_status,
            "is_effect": False,
        }
        self._tools["samsung_find_list_devices"] = {
            "name": "samsung_find_list_devices",
            "description": "List all registered devices in Samsung Find account.",
            "parameters": {
                "include_ids": {"type": "boolean", "description": "Include internal device IDs", "default": False}
            },
            "handler": self._handle_list_devices,
            "is_effect": False,
        }
        self._tools["samsung_find_get_capabilities"] = {
            "name": "samsung_find_get_capabilities",
            "description": "Get safe supported features and capabilities for a specific device.",
            "parameters": {"query": {"type": "string", "description": "Device name or identifier", "required": True}},
            "handler": self._handle_get_capabilities,
            "is_effect": False,
        }
        self._tools["samsung_find_get_last_location"] = {
            "name": "samsung_find_get_last_location",
            "description": "Get the last known passive GPS location for a device without triggering fresh active fix.",
            "parameters": {"query": {"type": "string", "description": "Device name or identifier", "required": True}},
            "handler": self._handle_get_last_location,
            "is_effect": False,
        }
        self._tools["samsung_find_request_location"] = {
            "name": "samsung_find_request_location",
            "description": "Request an active GPS location refresh from device and wait for coordinates.",
            "parameters": {
                "query": {"type": "string", "description": "Device name or identifier", "required": True},
                "poll_seconds": {"type": "integer", "description": "Max seconds to poll for fix", "default": 180},
            },
            "handler": self._handle_request_location,
            "is_effect": False,
        }
        self._tools["samsung_find_check_connection"] = {
            "name": "samsung_find_check_connection",
            "description": "Ping device to test reachability and return battery status.",
            "parameters": {
                "query": {"type": "string", "description": "Device name or identifier", "required": True},
                "poll_seconds": {"type": "integer", "description": "Max seconds to poll", "default": 40},
            },
            "handler": self._handle_check_connection,
            "is_effect": False,
        }

        if "ring" in self.allow_effects or "all" in self.allow_effects:
            self._tools["samsung_find_ring"] = {
                "name": "samsung_find_ring",
                "description": "Audibly ring a device or stop ringing alarm.",
                "parameters": {
                    "query": {"type": "string", "description": "Device name or identifier", "required": True},
                    "status": {"type": "string", "enum": ["start", "stop"], "default": "start"},
                    "message": {"type": "string", "description": "Optional ring message"},
                    "poll_seconds": {"type": "integer", "default": 40},
                },
                "handler": self._handle_ring,
                "is_effect": True,
            }

        if "tracking" in self.allow_effects or "track" in self.allow_effects or "all" in self.allow_effects:
            self._tools["samsung_find_set_tracking"] = {
                "name": "samsung_find_set_tracking",
                "description": "Toggle continuous lost-mode location tracking for a device.",
                "parameters": {
                    "query": {"type": "string", "description": "Device name or identifier", "required": True},
                    "enabled": {
                        "type": "boolean",
                        "description": "True to start tracking, False to stop",
                        "required": True,
                    },
                    "poll_seconds": {"type": "integer", "default": 30},
                },
                "handler": self._handle_set_tracking,
                "is_effect": True,
            }

    def _handle_status(self, args: dict[str, Any]) -> Any:
        store = MasterStateStore(master_path=self.config.master_state_path, legacy_path=self.config.state_path)
        master = store.load(allow_legacy_fallback=True)
        return {
            "authenticated": bool(master and master.identity.userauth_token),
            "master_state_exists": store.exists(),
            "schema_version": master.schema_version if master else None,
        }

    def _handle_list_devices(self, args: dict[str, Any]) -> Any:
        include_ids = bool(args.get("include_ids", False))
        service = self.get_service()
        devices = service.list_devices()
        return [d.to_dict(include_id=include_ids) for d in devices]

    def _handle_get_capabilities(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("query parameter is required")
        service = self.get_service()
        return service.get_capabilities(query).to_dict()

    def _handle_get_last_location(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("query parameter is required")
        service = self.get_service()
        return service.get_last_location(query).to_dict()

    def _handle_request_location(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("query parameter is required")
        poll_seconds = int(args.get("poll_seconds", 180))
        service = self.get_service()
        return service.request_location(query, poll_seconds=poll_seconds).to_dict()

    def _handle_check_connection(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("query parameter is required")
        poll_seconds = int(args.get("poll_seconds", 40))
        service = self.get_service()
        return service.check_connection(query, poll_seconds=poll_seconds).to_dict()

    def _handle_ring(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("query parameter is required")
        status = str(args.get("status", "start"))
        message = args.get("message")
        poll_seconds = int(args.get("poll_seconds", 40))
        service = self.get_service()
        return service.ring(query, status=status, message=message, poll_seconds=poll_seconds).to_dict()

    def _handle_set_tracking(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("query parameter is required")
        enabled = bool(args.get("enabled", True))
        poll_seconds = int(args.get("poll_seconds", 30))
        service = self.get_service()
        return service.set_tracking(query, enabled=enabled, poll_seconds=poll_seconds).to_dict()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            if name in ("samsung_find_ring", "samsung_find_set_tracking"):
                effect_name = name.removeprefix("samsung_find_")
                return serialize_error(
                    code="effect_disabled",
                    message=f"Side-effect tool {name!r} is disabled. Start server with --allow-effects {effect_name}",
                )
            return serialize_error(
                code="tool_not_found",
                message=f"Unknown tool: {name!r}",
            )

        tool_meta = self._tools[name]
        try:
            raw_result = tool_meta["handler"](arguments)
            return serialize_response(to_serializable(raw_result))
        except AuthError as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except (SecurityError, StorageError) as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except (DeviceNotFoundError, OperationError, RateLimitError) as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except NetworkError as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except Exception as exc:
            return serialize_error(code="execution_error", message=str(exc))


def create_mcp_server(
    service: FindService | None = None,
    config: FindConfig | None = None,
    allow_effects: Set[str] = frozenset(),
) -> SamsungFindMCPServer:
    return SamsungFindMCPServer(service=service, config=config, allow_effects=allow_effects)


def get_registered_tool_names(server: SamsungFindMCPServer) -> list[str]:
    return list(server._tools.keys())


def execute_tool(server: SamsungFindMCPServer, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return server.call_tool(name, arguments)


def parse_effects_arg(value: str | None) -> set[str]:
    if not value:
        return set()
    return {v.strip().lower() for v in value.split(",") if v.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="samsung-find-mcp",
        description="Samsung Find stdio Model Context Protocol (MCP) server",
    )
    parser.add_argument(
        "--allow-effects",
        default="",
        help="Comma-separated list of allowed side-effect tools ('ring', 'tracking', or 'all')",
    )
    parser.add_argument("--master-state", default=None, help="Path to shared Samsung master state v1")
    parser.add_argument("--state", default=None, help="Path to service state")
    parser.add_argument("--country", default="US", help="Country code")
    parser.add_argument("--language", default="en", help="Language code")
    parser.add_argument("--timezone", default="UTC", help="IANA timezone")

    args = parser.parse_args(argv)
    allowed_effects = parse_effects_arg(args.allow_effects)

    config = FindConfig(
        country=args.country,
        language=args.language,
        timezone=args.timezone,
        master_state_path=args.master_state,
        state_path=args.state,
    )

    server = create_mcp_server(config=config, allow_effects=allowed_effects)

    try:
        import anyio
        from mcp.server.fastmcp import FastMCP

        mcp_app = FastMCP("samsung-find")

        for tool_name, tool_info in server._tools.items():
            desc = tool_info["description"]

            if tool_name == "samsung_find_status":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_status() -> dict[str, Any]:
                    return server.call_tool("samsung_find_status", {})

            elif tool_name == "samsung_find_list_devices":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_list_devices(include_ids: bool = False) -> dict[str, Any]:
                    return server.call_tool("samsung_find_list_devices", {"include_ids": include_ids})

            elif tool_name == "samsung_find_get_capabilities":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_capabilities(query: str) -> dict[str, Any]:
                    return server.call_tool("samsung_find_get_capabilities", {"query": query})

            elif tool_name == "samsung_find_get_last_location":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_last_location(query: str) -> dict[str, Any]:
                    return server.call_tool("samsung_find_get_last_location", {"query": query})

            elif tool_name == "samsung_find_request_location":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_request_loc(query: str, poll_seconds: int = 180) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_request_location",
                        {"query": query, "poll_seconds": poll_seconds},
                    )

            elif tool_name == "samsung_find_check_connection":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_check(query: str, poll_seconds: int = 40) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_check_connection",
                        {"query": query, "poll_seconds": poll_seconds},
                    )

            elif tool_name == "samsung_find_ring":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_ring(
                    query: str,
                    status: str = "start",
                    message: str | None = None,
                    poll_seconds: int = 40,
                ) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_ring",
                        {
                            "query": query,
                            "status": status,
                            "message": message,
                            "poll_seconds": poll_seconds,
                        },
                    )

            elif tool_name == "samsung_find_set_tracking":

                @mcp_app.tool(name=tool_name, description=desc)
                def handle_track(
                    query: str,
                    enabled: bool = True,
                    poll_seconds: int = 30,
                ) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_set_tracking",
                        {"query": query, "enabled": enabled, "poll_seconds": poll_seconds},
                    )

        anyio.run(mcp_app.run_stdio_async)
        return 0
    except ImportError:
        print(
            "Error: The 'mcp' package is required to run the MCP server.\n"
            "Install it via: pip install 'samsung-find[mcp]'",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

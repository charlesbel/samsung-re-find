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


def _validate_query(raw: Any) -> str:
    if not isinstance(raw, str):
        raise ValueError("query must be a non-empty string between 1 and 256 characters")
    cleaned = raw.strip()
    if not (1 <= len(cleaned) <= 256):
        raise ValueError("query must be a non-empty string between 1 and 256 characters")
    return cleaned


def _validate_poll_seconds(raw: Any, default: int = 180) -> int:
    if raw is None:
        return default
    try:
        val = int(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("poll_seconds must be an integer between 1 and 600") from exc
    if not (1 <= val <= 600):
        raise ValueError("poll_seconds must be an integer between 1 and 600")
    return val


def _validate_message(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw) > 256:
        raise ValueError("message must be a string up to 256 characters")
    return raw


def _validate_status(raw: Any) -> str:
    status = str(raw or "start").lower().strip()
    if status not in ("start", "stop"):
        raise ValueError("status must be 'start' or 'stop'")
    return status


def _validate_enabled(raw: Any) -> bool:
    if raw is True:
        return True
    if raw is False:
        return False
    raise ValueError("enabled must be a boolean (True or False)")


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
                "description": "Audibly ring a device or stop ringing alarm. Requires confirm: true.",
                "parameters": {
                    "query": {"type": "string", "description": "Device name or identifier", "required": True},
                    "confirm": {"type": "boolean", "description": "Explicit user confirmation", "required": True},
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
                "description": "Toggle continuous lost-mode location tracking for a device. Requires confirm: true.",
                "parameters": {
                    "query": {"type": "string", "description": "Device name or identifier", "required": True},
                    "confirm": {"type": "boolean", "description": "Explicit user confirmation", "required": True},
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
        include_ids = args.get("include_ids", False)
        if type(include_ids) is not bool:
            raise ValueError("include_ids must be a boolean (True or False)")
        service = self.get_service()
        devices = service.list_devices(include_ids=include_ids)
        return [d.to_dict(include_id=include_ids) for d in devices]

    def _handle_get_capabilities(self, args: dict[str, Any]) -> Any:
        query = _validate_query(args.get("query"))
        service = self.get_service()
        return service.get_capabilities(query).to_dict()

    def _handle_get_last_location(self, args: dict[str, Any]) -> Any:
        query = _validate_query(args.get("query"))
        service = self.get_service()
        return service.get_last_location(query).to_dict()

    def _handle_request_location(self, args: dict[str, Any]) -> Any:
        query = _validate_query(args.get("query"))
        poll_seconds = _validate_poll_seconds(args.get("poll_seconds"), default=180)
        service = self.get_service()
        return service.request_location(query, poll_seconds=poll_seconds).to_dict()

    def _handle_check_connection(self, args: dict[str, Any]) -> Any:
        query = _validate_query(args.get("query"))
        poll_seconds = _validate_poll_seconds(args.get("poll_seconds"), default=40)
        service = self.get_service()
        return service.check_connection(query, poll_seconds=poll_seconds).to_dict()

    def _handle_ring(self, args: dict[str, Any]) -> Any:
        query = _validate_query(args.get("query"))
        status = _validate_status(args.get("status"))
        message = _validate_message(args.get("message"))
        poll_seconds = _validate_poll_seconds(args.get("poll_seconds"), default=40)
        service = self.get_service()
        return service.ring(query, status=status, message=message, poll_seconds=poll_seconds).to_dict()

    def _handle_set_tracking(self, args: dict[str, Any]) -> Any:
        query = _validate_query(args.get("query"))
        enabled = _validate_enabled(args.get("enabled"))
        poll_seconds = _validate_poll_seconds(args.get("poll_seconds"), default=30)
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

        # Side-effect tools require explicit per-call confirm: true
        if tool_meta.get("is_effect") and arguments.get("confirm") is not True:
            return serialize_error(
                code="confirmation_required",
                message=f"Side-effect tool {name!r} requires explicit confirm=true parameter",
            )

        try:
            raw_result = tool_meta["handler"](arguments)
            return serialize_response(to_serializable(raw_result))
        except ValueError as exc:
            return serialize_error(code="invalid_parameter", message=str(exc))
        except AuthError as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except (SecurityError, StorageError) as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except (DeviceNotFoundError, OperationError, RateLimitError) as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except NetworkError as exc:
            return serialize_error(code=exc.code, message=str(exc))
        except Exception:
            return serialize_error(code="internal_error", message="An internal execution error occurred")


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
        prog="samsung-re-find-mcp",
        description="Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server",
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
        import importlib.metadata

        import anyio
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations

        try:
            mcp_version = importlib.metadata.version("mcp")
        except Exception as exc:
            raise RuntimeError("MCP SDK version cannot be determined.") from exc

        if mcp_version != "1.29.1":
            raise RuntimeError(
                f"Unsupported MCP SDK version: {mcp_version}. "
                "samsung-re-find requires exactly mcp==1.29.1 for deterministic protocol schema guarantees."
            )

        mcp_app = FastMCP("samsung-re-find")

        if not hasattr(mcp_app, "_tool_manager") or not hasattr(mcp_app._tool_manager, "_tools"):
            raise RuntimeError(
                "MCP SDK internal structure mismatch: FastMCP._tool_manager._tools is missing. "
                "samsung-re-find requires FastMCP tool manager support."
            )

        for tool_name, tool_info in server._tools.items():
            desc = tool_info["description"]
            is_effect = bool(tool_info["is_effect"])
            annotations = ToolAnnotations(
                readOnlyHint=not is_effect,
                destructiveHint=False,
                idempotentHint=not is_effect,
                openWorldHint=True,
            )

            if tool_name == "samsung_find_status":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_status() -> dict[str, Any]:
                    return server.call_tool("samsung_find_status", {})

            elif tool_name == "samsung_find_list_devices":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_list_devices(include_ids: bool = False) -> dict[str, Any]:
                    return server.call_tool("samsung_find_list_devices", {"include_ids": include_ids})

            elif tool_name == "samsung_find_get_capabilities":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_capabilities(query: str) -> dict[str, Any]:
                    return server.call_tool("samsung_find_get_capabilities", {"query": query})

            elif tool_name == "samsung_find_get_last_location":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_last_location(query: str) -> dict[str, Any]:
                    return server.call_tool("samsung_find_get_last_location", {"query": query})

            elif tool_name == "samsung_find_request_location":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_request_loc(query: str, poll_seconds: int = 180) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_request_location",
                        {"query": query, "poll_seconds": poll_seconds},
                    )

            elif tool_name == "samsung_find_check_connection":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_check(query: str, poll_seconds: int = 40) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_check_connection",
                        {"query": query, "poll_seconds": poll_seconds},
                    )

            elif tool_name == "samsung_find_ring":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_ring(
                    query: str,
                    confirm: bool,
                    status: str = "start",
                    message: str | None = None,
                    poll_seconds: int = 40,
                ) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_ring",
                        {
                            "query": query,
                            "confirm": confirm,
                            "status": status,
                            "message": message,
                            "poll_seconds": poll_seconds,
                        },
                    )

            elif tool_name == "samsung_find_set_tracking":

                @mcp_app.tool(name=tool_name, description=desc, annotations=annotations)
                def handle_track(
                    query: str,
                    confirm: bool,
                    enabled: bool = True,
                    poll_seconds: int = 30,
                ) -> dict[str, Any]:
                    return server.call_tool(
                        "samsung_find_set_tracking",
                        {
                            "query": query,
                            "confirm": confirm,
                            "enabled": enabled,
                            "poll_seconds": poll_seconds,
                        },
                    )

        # FastMCP derives closed argument models but omits the JSON Schema marker;
        # publish the exact pre-I/O contract required by MCP clients.
        for registered_tool in mcp_app._tool_manager._tools.values():
            if not hasattr(registered_tool, "parameters") or not isinstance(registered_tool.parameters, dict):
                raise RuntimeError("MCP SDK internal structure mismatch: Tool parameters object missing or invalid.")
            registered_tool.parameters["additionalProperties"] = False

        anyio.run(mcp_app.run_stdio_async)
        return 0
    except ImportError:
        print(
            "Error: The 'mcp' package is required to run the MCP server.\n"
            "Install it via: pip install 'samsung-re-find[mcp]'",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

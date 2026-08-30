"""Smoke-test CLI and official MCP protocol from an isolated wheel environment."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any


def _send_json(proc: subprocess.Popen[str], message: dict[str, Any]) -> None:
    if proc.stdin is None:
        raise RuntimeError("MCP stdin pipe is unavailable")
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def _recv_json(proc: subprocess.Popen[str], timeout: float = 10.0) -> dict[str, Any]:
    stdout = proc.stdout
    if stdout is None:
        raise RuntimeError("MCP stdout pipe is unavailable")
    lines: queue.Queue[str] = queue.Queue(maxsize=1)
    threading.Thread(target=lambda: lines.put(stdout.readline()), daemon=True).start()
    try:
        line = lines.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError("timed out waiting for MCP JSON-RPC response") from exc
    if not line:
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise RuntimeError(f"MCP server closed stdout before responding: {stderr}")
    return json.loads(line)


def _smoke_mcp(executable: Path, env: dict[str, str]) -> None:
    proc = subprocess.Popen(
        [str(executable)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        _send_json(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "wheel-smoke", "version": "1.0"},
                },
            },
        )
        initialized = _recv_json(proc)
        if initialized.get("id") != 1 or not initialized.get("result", {}).get("protocolVersion"):
            raise RuntimeError(f"MCP protocol negotiation failed for {executable.name}")
        if initialized["result"].get("serverInfo", {}).get("name") != "samsung-re-find":
            raise RuntimeError(f"MCP server identity mismatch for {executable.name}")

        _send_json(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send_json(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = _recv_json(proc)
        if listed.get("id") != 2:
            raise RuntimeError(f"MCP tools/list response mismatch for {executable.name}")
        tools = listed.get("result", {}).get("tools") or []
        if not tools:
            raise RuntimeError(f"MCP tools/list returned no tools for {executable.name}")
        for tool in tools:
            if tool["inputSchema"].get("additionalProperties") is not False:
                raise RuntimeError(f"MCP tool schema is not closed in {executable.name}")
            if not tool.get("annotations"):
                raise RuntimeError(f"MCP tool annotations missing in {executable.name}")
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


def main() -> int:
    bindir = Path(sys.executable).parent
    cli_canonical = bindir / ("samsung-re-find.exe" if os.name == "nt" else "samsung-re-find")
    cli_compat = bindir / ("samsung-find.exe" if os.name == "nt" else "samsung-find")
    mcp_canonical = bindir / ("samsung-re-find-mcp.exe" if os.name == "nt" else "samsung-re-find-mcp")
    mcp_compat = bindir / ("samsung-find-mcp.exe" if os.name == "nt" else "samsung-find-mcp")

    with tempfile.TemporaryDirectory(prefix="samsung-re-find-wheel-home-") as home:
        env = os.environ.copy()
        env["HOME"] = home
        env["XDG_CONFIG_HOME"] = str(Path(home) / ".config")
        env["XDG_STATE_HOME"] = str(Path(home) / ".local" / "state")

        for cli in (cli_canonical, cli_compat):
            if not cli.is_file():
                raise RuntimeError(f"CLI executable not found: {cli.name}")
            cli_result = subprocess.run(
                [str(cli), "--help"],
                text=True,
                capture_output=True,
                env=env,
                timeout=15,
                check=False,
            )
            if cli_result.returncode != 0:
                raise RuntimeError(f"isolated wheel CLI smoke failed for {cli.name}")
            if "Unofficial reverse-engineered Samsung Find SDK" not in cli_result.stdout:
                raise RuntimeError(f"CLI --help output missing standard tagline for {cli.name}")

        for mcp in (mcp_canonical, mcp_compat):
            if not mcp.is_file():
                raise RuntimeError(f"MCP executable not found: {mcp.name}")
            _smoke_mcp(mcp, env)

    print("Isolated built-wheel canonical and compatibility CLI/MCP smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

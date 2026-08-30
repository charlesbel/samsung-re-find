# AI-Agent Integration Guide

`samsung-re-find` provides both a structured JSON CLI and a standard stdio Model Context Protocol (MCP) server for integration into agent frameworks (such as Hermes, Claude Desktop, Goose, Cursor). Legacy aliases `samsung-find` and `samsung-find-mcp` are preserved for backward compatibility.

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

## Integration Options

1. **MCP (Recommended for Agent Environments):**
   - Run stdio MCP server: `samsung-re-find-mcp` (or with `--allow-effects ring,tracking`).
   - Narrow, typed tools with safety boundaries and default read-only access.

2. **CLI JSON Mode (Recommended for Scripting):**
   - Output on `stdout` is wrapped in versioned envelopes (`schema_version: "1.0"`).
   - Strict exit codes (0, 2, 3, 4, 5, 6).

## Recommended Decision Flow

1. Check authentication health using `samsung_find_status` (MCP) or `samsung-re-find verify` (CLI).
2. Run `samsung_find_list_devices` when identifying user devices.
3. Check supported capabilities with `samsung_find_get_capabilities`.
4. Prefer passive location (`samsung_find_get_last_location`) for inventory/status checks.
5. Use active GPS refresh (`samsung_find_request_location`) only when real-time fix is needed.
6. Require explicit user confirmation before audible ringing or toggling continuous tracking.
7. Never attempt to synthesize unsupported lock, wipe, lost-mode, or payment operations.

## Installing the Bundled Skills

The portable skills are located under `.skills/` at the repository root:

- `.skills/samsung-re-find/SKILL.md`
- `.skills/samsung-account-auth/SKILL.md`

For Hermes Agent:

```bash
mkdir -p ~/.hermes/skills/smart-home
cp -R .skills/samsung-re-find ~/.hermes/skills/smart-home/
cp -R .skills/samsung-account-auth ~/.hermes/skills/smart-home/
```

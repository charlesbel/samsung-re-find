# AI-Agent Integration Guide

`samsung-re-find` provides both a structured JSON CLI and a standard stdio Model Context Protocol (MCP) server for integration into agent frameworks (such as Hermes, Claude Desktop, Goose, Cursor). Legacy aliases `samsung-find` and `samsung-find-mcp` are preserved for backward compatibility.

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

## Integration Options

1. **MCP (Recommended for Agent Environments):**
   - Run stdio MCP server: `samsung-re-find-mcp` (or with `--allow-effects ring,tracking`).
   - Narrow, typed tools with explicit effect boundaries. Ring and tracking are disabled by default, but active location and connectivity tools are enabled and may contact or wake a device.

2. **CLI JSON Mode (Recommended for Scripting):**
   - Output on `stdout` is wrapped in versioned envelopes (`schema_version: "1.0"`).
   - Exit codes `0` through `5`; see [CLI Reference](cli.md#exit-codes) for the normative mapping.

## Recommended Decision Flow

1. Check authentication health using `samsung_find_status` (MCP) or `samsung-re-find verify` (CLI).
2. Run `samsung_find_list_devices` when identifying user devices.
3. Check supported capabilities with `samsung_find_get_capabilities`.
4. Prefer passive location (`samsung_find_get_last_location`) for inventory/status checks.
5. Use an active location request (`samsung_find_request_location`) only when a newer fix is needed.
6. Require explicit user confirmation before audible ringing or toggling continuous tracking.
7. Never attempt to synthesize unsupported lock, wipe, lost-mode, or payment operations.

## Installing the Bundled Skills

The portable skills are located under `.skills/` at the repository root:

- `.skills/samsung-re-find/SKILL.md`
- `.skills/samsung-account-auth/SKILL.md`

Determine the skills directory configured by the agent runtime instead of assuming a framework-specific path. Then copy both skill directories:

```bash
AGENT_SKILLS_DIR="/path/configured/by/your-agent"
mkdir -p "$AGENT_SKILLS_DIR"
cp -R .skills/samsung-re-find "$AGENT_SKILLS_DIR/"
cp -R .skills/samsung-account-auth "$AGENT_SKILLS_DIR/"
```

If that directory is unknown, consult the runtime's documentation or configuration before copying the skills.

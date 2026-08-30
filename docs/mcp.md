# Samsung Find MCP Server

The `samsung-re-find-mcp` executable (legacy alias `samsung-find-mcp`) implements the Model Context Protocol (MCP) over `stdio`, allowing local AI agents (such as Hermes, Claude Desktop, Goose, Cursor) to securely inspect device status and retrieve locations without manual credential management.

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

## Installation

```bash
pip install 'samsung-re-find[mcp]'
```

## Running the Server

```bash
# Default: read-only tools only (canonical: samsung-re-find-mcp; legacy alias: samsung-find-mcp)
samsung-re-find-mcp

# With explicit side-effects enabled
samsung-re-find-mcp --allow-effects ring,tracking
```

## Exposed MCP Tools

### Read-Only Tools (Enabled by Default)

1. `samsung_find_status`
   - Description: Check local authentication status and master state validity.
   - Parameters: none

2. `samsung_find_list_devices`
   - Description: List registered devices in Samsung Find.
   - Parameters: `include_ids` (boolean, optional)

3. `samsung_find_get_capabilities`
   - Description: Inspect supported capabilities for a specific device.
   - Parameters: `query` (string, required)

4. `samsung_find_get_last_location`
   - Description: Retrieve the last known passive GPS fix without triggering fresh device polling.
   - Parameters: `query` (string, required)

5. `samsung_find_request_location`
   - Description: Request an active GPS location refresh from device and wait for fix.
   - Parameters: `query` (string, required), `poll_seconds` (integer, default 180)

6. `samsung_find_check_connection`
   - Description: Ping device for reachability and battery percentage.
   - Parameters: `query` (string, required), `poll_seconds` (integer, default 40)

### Side-Effect Tools (Gated / Disabled by Default)

These tools perform physical or audible changes to user devices. They are disabled by default and require `--allow-effects ring` or `--allow-effects tracking`:

1. `samsung_find_ring`
   - Description: Audibly ring a device or stop ringing.
   - Parameters: `query` (string, required), `status` (`"start"` or `"stop"`), `message` (string, optional), `confirm` (must be exactly `true`).

2. `samsung_find_set_tracking`
   - Description: Toggle continuous lost-device tracking.
   - Parameters: `query` (string, required), `enabled` (boolean, required), `confirm` (must be exactly `true`).

Enabling a tool at server startup does not authorize an individual effect: each call must also include `confirm: true` after the user has explicitly approved the target and action.

## Configuration Options

- `--allow-effects <tools>` - Comma-separated list of enabled side-effects (`ring`, `tracking`, or `all`).
- `--master-state <path>` - Path to neutral `master-state-v1` file.
- `--country <country_code>` - ISO 2-letter country code (default: `US`).
- `--language <language_code>` - Language code (default: `en`).
- `--timezone <timezone>` - IANA timezone (default: `UTC`).

## Security Guarantees

- **No Remote Network Listening:** MCP server runs strictly via local `stdio`.
- **No Arbitrary Dispatchers:** Only narrow, hardcoded, allowlisted functions are exposed.
- **Redaction:** Device IDs and sensitive internal parameters are masked unless explicitly requested.
- **Fail-Closed:** Calling disabled side-effect tools fails immediately before network I/O.

# Samsung Find MCP Server

The `samsung-re-find-mcp` executable (legacy alias `samsung-find-mcp`) implements the Model Context Protocol (MCP) over `stdio`. After the initial interactive account setup, local AI agents can reuse the protected local state to inspect device status and retrieve locations through narrow tools.

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

## Installation

```bash
pip install 'samsung-re-find[mcp]'
```

## Running the Server

```bash
# Default tools; active checks are included, audible/persistent effects are not
samsung-re-find-mcp

# With explicit side-effects enabled
samsung-re-find-mcp --allow-effects ring,tracking
```

## Exposed MCP Tools

### Tools enabled by default

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
   - Description: Retrieve the last known location without requesting a new device fix.
   - Parameters: `query` (string, required)

5. `samsung_find_request_location`
   - Description: Request an active location update from the device and wait for a fix. This can wake the device or consume battery; its MCP annotations are not read-only or idempotent.
   - Parameters: `query` (string, required), `poll_seconds` (integer, default 180)

6. `samsung_find_check_connection`
   - Description: Ping the device for reachability and battery percentage. This is an active request and is not annotated as read-only or idempotent.
   - Parameters: `query` (string, required), `poll_seconds` (integer, default 40)

### Side-Effect Tools (Gated / Disabled by Default)

These tools perform physical or audible changes to user devices. They are disabled by default and require `--allow-effects ring` or `--allow-effects tracking`:

1. `samsung_find_ring`
   - Description: Audibly ring a device or stop ringing.
   - Parameters: `query` (string, required), `status` (`"start"` or `"stop"`), `message` (string, optional), `confirm` (must be exactly `true`).

2. `samsung_find_set_tracking`
   - Description: Toggle the continuous-tracking operation exposed by the backend.
   - Parameters: `query` (string, required), `enabled` (boolean, required), `confirm` (must be exactly `true`).

Enabling a tool at server startup does not authorize an individual effect: each call must also include `confirm: true` after the user has explicitly approved the target and action.

## Configuration Options

- `--allow-effects <tools>` - Comma-separated list of enabled side-effects (`ring`, `tracking`, or `all`).
- `--master-state <path>` - Path to neutral `master-state-v1` file.
- `--country <country_code>` - ISO 2-letter country code (default: `US`).
- `--language <language_code>` - Language code (default: `en`).
- `--timezone <timezone>` - IANA timezone (default: `UTC`).

## Security Guarantees

- **No Inbound Network Listener:** MCP transport uses local `stdio`; tool calls still make outbound HTTPS requests to allowlisted Samsung services.
- **No Arbitrary Dispatchers:** Only narrow, hardcoded, allowlisted functions are exposed.
- **Redaction:** Device IDs and sensitive internal parameters are masked unless explicitly requested.
- **Fail-Closed:** Calling disabled side-effect tools fails immediately before network I/O.

# samsung-find

[![CI](https://github.com/charlesbel/samsung-find/actions/workflows/ci.yml/badge.svg)](https://github.com/charlesbel/samsung-find/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/samsung-find.svg)](https://pypi.org/project/samsung-find/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)

**Persistent Samsung SmartThings Find Python SDK, versioned JSON CLI, and stdio Model Context Protocol (MCP) server.**

`samsung-find` is an unofficial, production-ready toolkit for discovering, locating, and inspecting Samsung devices (Galaxy phones, tablets, SmartTags, Galaxy Buds, Galaxy Watches). Unlike fragile cookie-scraping tools, `samsung-find` implements Samsung's official OAuth application flow: retaining the Samsung Account master token (`userauth_token`), automatically rotating scoped tokens, and regenerating sessions without repeated browser logins.

> **Disclaimer:** This project is unofficial, community-driven, and NOT affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings. It relies on reverse-engineered cloud APIs that may change without notice. Use solely with your own personal accounts and devices.

---

## Key Features

- **Python SDK:** Typed, synchronous, context-managed facade (`SamsungFindClient`, `FindConfig`, `Device`, `LocationResult`).
- **Versioned JSON CLI:** Stable JSON output wrapped in standardized envelopes (`schema_version: "1.0"`), strict exit codes, and automated machine consumption.
- **Model Context Protocol (MCP) Server:** Stdio MCP server (`samsung-find-mcp`) exposing narrow, safe tools for AI agents (Hermes, Claude Desktop, Cursor, Goose).
- **Shared Master State v1:** Unified, neutral Samsung Account authentication contract (`master-state-v1`) shared with companion tools like [`samsung-health-cloud`](https://github.com/charlesbel/samsung-health-cloud).
- **Strict Security Boundaries:** Hardened URL validation, rejection of untrusted/hostile pagination, no generic dispatchers, and gated side-effects.

---

## Companion Projects

This project belongs to the Samsung reverse-engineering ecosystem:

| Repository | Scope | Focus |
|---|---|---|
| **[`samsung-find`](https://github.com/charlesbel/samsung-find)** (this repository) | Device Tracking & Management | Discovers devices, fetches GPS coordinates, checks reachability, powers location automations. |
| **[`samsung-health-cloud`](https://github.com/charlesbel/samsung-health-cloud)** | Health Cloud Analytics | Read-only access to Samsung Health sync mirrors (sleep, heart rate, workouts, steps). |

### Shared Authentication Architecture

Both services share the identical, neutral `master-state-v1` contract without credential duplication:

```text
Samsung Account interactive login (samsung-find)
                    │
                    ▼
     Shared Neutral Master State v1
     (samsung-account/master.json)
           │                  │
           ▼                  ▼
  Samsung Find State   Samsung Health Cloud State
  (derived tokens)     (derived tokens & mirror)
           │                  │
           ▼                  ▼
      SDK/CLI/MCP        SDK/CLI/MCP
```

- `samsung-find` acts as the primary interactive login provider.
- `samsung-health-cloud` consumes `master.json` in strict read-only mode.
- Derived tokens and service caches remain strictly isolated in their respective service directories.

---

## Installation

```bash
# Basic SDK and CLI
pip install samsung-find

# With MCP server support
pip install 'samsung-find[mcp]'
```

---

## Quick Start

### 1. Interactive Authentication

Run the setup flow once to generate your shared master state:

```bash
# 1. Register the local redirect URI handler (Linux desktop)
samsung-find install-handler

# 2. Generate the Samsung Account login URL
samsung-find auth-start --country us --locale en-US

# 3. Complete login in browser, then exchange credentials:
samsung-find auth-complete
samsung-find status
samsung-find verify
```

*(If upgrading from v0.1 `samsung-find-agent`, migrate seamlessly without re-login: `samsung-find migrate-master`)*.

---

### 2. Python SDK

```python
from samsung_find import FindConfig, SamsungFindClient

config = FindConfig(timezone="UTC")

with SamsungFindClient.from_config(config) as client:
    # List all registered devices (IDs masked by default)
    for device in client.list_devices():
        print(f"{device.name} ({device.model or 'Unknown'})")

    # Get passive GPS fix (last known)
    loc = client.get_last_location("Galaxy S24")
    if loc.latitude is not None:
        print(f"Location: {loc.latitude}, {loc.longitude} (fresh: {loc.is_fresh})")

    # Check connection and battery
    status = client.check_connection("SmartTag2")
    print(f"Reachable: {status.success}, Battery: {status.battery}%")
```

---

### 3. CLI Usage

All CLI outputs on `stdout` are contractually schema-wrapped JSON:

```bash
# List devices
samsung-find devices

# Check capabilities
samsung-find capabilities "Galaxy S24"

# Get location (passive or active GPS poll)
samsung-find locate "Galaxy S24" --passive
samsung-find locate "Galaxy S24" --poll-seconds 180

# Check reachability and battery
samsung-find check "SmartTag2"
```

Output example:

```json
{
  "ok": true,
  "schema_version": "1.0",
  "data": {
    "latitude": 48.8566,
    "longitude": 2.3522,
    "accuracy_m": 12.0,
    "is_fresh": true,
    "is_precise": true,
    "timestamp": "2026-08-30T12:00:00Z"
  }
}
```

---

### 4. Model Context Protocol (MCP) Server

Launch the stdio MCP server for agent environments:

```bash
# Default: read-only safe tools
samsung-find-mcp

# Enable physical side effects (audible alarms / continuous tracking)
samsung-find-mcp --allow-effects ring,tracking
```

---

## Safety & Security Boundaries

1. **Strict Operation Allowlist:** Only 5 non-destructive operations are permitted (`CHECK_CONNECTION`, `LOCATION`, `RING`, `TRACK_LOCATION_START`, `TRACK_LOCATION_STOP`).
2. **No Destructive Operations:** Device locking, remote wiping, lost-mode PIN locks, and payment locks are deliberately omitted.
3. **Opt-in Side Effects:** Audible ringing and continuous tracking require explicit confirmation (`--yes` in CLI, `--allow-effects` in MCP).
4. **Transport Hardening:** Destination URLs and redirect targets are validated against an allowlist before attaching Bearer tokens. Non-idempotent actions are never blindly auto-retried.
5. **Private Credentials:** Master state and service files use POSIX mode `0600` in `0700` directories. In-memory models implement strict `repr` redaction to prevent secret leakage in logs.

---

## Documentation

- [Shared Master State Specification](docs/shared-master-state-v1.md)
- [Python SDK Reference](docs/sdk.md)
- [CLI Reference & JSON Schemas](docs/cli.md)
- [MCP Server Reference](docs/mcp.md)
- [AI-Agent Integration Guide](docs/agent-integration.md)
- [Migration Guide from 0.1](docs/migration-0.2.md)
- [Authentication Architecture](docs/authentication.md)
- [Technical Findings & Reverse Engineering](docs/technical-findings.md)

---

## License

MIT License. Copyright (c) 2026 Charles Bel, Hermes Agent, and contributors. See [LICENSE](LICENSE) for details.

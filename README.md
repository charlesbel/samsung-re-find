# samsung-re-find

[![CI](https://github.com/charlesbel/samsung-re-find/actions/workflows/ci.yml/badge.svg)](https://github.com/charlesbel/samsung-re-find/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/samsung-re-find.svg)](https://pypi.org/project/samsung-re-find/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)

**Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server.**

`samsung-re-find` is a typed toolkit for discovering, locating, and inspecting Samsung devices (Galaxy phones, tablets, SmartTags, Galaxy Buds, and Galaxy Watches). It implements Samsung Account application authentication, retains the account master token locally, rotates scoped tokens, and can regenerate derived sessions without repeated browser logins while that master authorization remains valid.

> **Disclaimer:** This project is unofficial, reverse-engineered, community-driven, and NOT affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings. It relies on private cloud APIs that may change without notice. Use solely with your own personal accounts and devices.

---

## Key Features

- **Python SDK:** Typed, synchronous, context-managed facade (`from samsung_find import SamsungFindClient, FindConfig, Device, LocationResult`).
- **Versioned JSON CLI:** Canonical command `samsung-re-find` (with compatibility alias `samsung-find`) providing stable JSON wrapped in standardized envelopes (`schema_version: "1.0"`), strict exit codes, and automated machine consumption.
- **Model Context Protocol (MCP) Server:** Stdio MCP server (`samsung-re-find-mcp`, legacy alias `samsung-find-mcp`) exposing narrow, safe tools for AI agents (Hermes, Claude Desktop, Cursor, Goose).
- **Shared Master State v1:** Unified, neutral Samsung Account authentication contract (`master-state-v1`) shared with companion tools like [`samsung-re-health`](https://github.com/charlesbel/samsung-re-health).
- **Strict Security Boundaries:** Hardened URL validation, rejection of untrusted/hostile pagination, no generic dispatchers, and gated side-effects.

---

## Companion Projects

This project belongs to the Samsung reverse-engineering ecosystem following the `samsung-re-{domain}` convention:

| Repository | Distribution / CLI | Scope | Focus |
|---|---|---|---|
| **[`samsung-re-find`](https://github.com/charlesbel/samsung-re-find)** (this repository) | `samsung-re-find` | Device Tracking & Management | Discovers devices, fetches GPS coordinates, checks reachability, powers location automations. |
| **[`samsung-re-health`](https://github.com/charlesbel/samsung-re-health)** | `samsung-re-health` | Health Cloud Analytics | Read-only access to Samsung Health sync mirrors (sleep, heart rate, workouts, steps). |

### Shared Authentication Architecture

Both services share the identical, neutral `master-state-v1` contract without credential duplication:

```text
Samsung Account interactive login (samsung-re-find)
                    │
                    ▼
     Shared Neutral Master State v1
     (samsung-account/master.json)
           │                  │
           ▼                  ▼
  Samsung Find State   Samsung Health State
  (derived tokens)     (derived tokens & mirror)
           │                  │
           ▼                  ▼
      SDK/CLI/MCP        SDK/CLI/MCP
```

- `samsung-re-find` acts as the primary interactive login provider.
- `samsung-re-health` consumes `master.json` in strict read-only mode.
- Derived tokens and service caches remain strictly isolated in their respective service directories.

---

## Installation

Python 3.11 or newer is required. Install into a virtual environment or an isolated application environment:

```bash
# SDK and JSON CLI
python -m pip install samsung-re-find

# SDK, CLI, and MCP stdio server
python -m pip install 'samsung-re-find[mcp]'
```

The distribution name is `samsung-re-find`, while the Python import remains `samsung_find`. The canonical executables are `samsung-re-find` and `samsung-re-find-mcp`; `samsung-find` and `samsung-find-mcp` are temporary compatibility aliases.

Verify the installation without credentials or network access:

```bash
samsung-re-find --help
samsung-re-find-mcp --help
python -c "import samsung_find; print(samsung_find.__version__)"
```

The repository and source distribution contain portable agent skills under `.skills/`. See [AI-Agent Integration](docs/agent-integration.md) for explicit installation; installing the wheel never modifies an agent profile automatically.

---

## Quick Start

### 1. Interactive Authentication

Run the setup flow once to generate your shared master state. Passwords and second factors are entered only on Samsung's sign-in page and are never handled by this project:

```bash
# 1. Register the private redirect handler on a supported desktop
samsung-re-find install-handler

# 2. Generate the Samsung Account login URL
samsung-re-find auth-start --country us --locale en-US

# 3. Complete login in the browser, then consume the captured callback
samsung-re-find auth-complete
samsung-re-find status
samsung-re-find verify
```

`status` inspects local readiness; `verify` performs live Samsung connectivity checks and may renew derived session state. Headless or unsupported desktop environments should follow the secure callback-file procedure in [Authentication Architecture](docs/authentication.md); never paste the callback URI into chat, shell history, or an issue.

If upgrading from v0.1 `samsung-find-agent`, first back up the private state, then migrate without re-login using `samsung-re-find migrate-master`. The source is left untouched; review [Migration Guide from 0.1](docs/migration-0.2.md) before using `--force`.

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
    print(f"Reachable: {status.success}, Battery: {status.battery or 'unknown'}")
```

---

### 3. CLI Usage

Executed CLI commands emit contractually schema-wrapped JSON on `stdout`. Informational `--help` output remains ordinary human-readable text:

```bash
# List devices (canonical CLI: samsung-re-find; legacy alias: samsung-find)
samsung-re-find devices

# Check capabilities
samsung-re-find capabilities "Galaxy S24"

# Get location (passive or active GPS poll)
samsung-re-find locate "Galaxy S24" --passive
samsung-re-find locate "Galaxy S24" --poll-seconds 180

# Check reachability and battery
samsung-re-find check "SmartTag2"
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
# Default: six read-only/safe tools
samsung-re-find-mcp

# Make effect tools available to the MCP host configuration
samsung-re-find-mcp --allow-effects ring,tracking
```

Default tools are `samsung_find_status`, `samsung_find_list_devices`, `samsung_find_get_capabilities`, `samsung_find_get_last_location`, `samsung_find_request_location`, and `samsung_find_check_connection`. `samsung_find_ring` and `samsung_find_set_tracking` are absent unless enabled at server startup and still require explicit confirmation in the tool call. Device IDs are hidden by default.

See [MCP Server Reference](docs/mcp.md) for schemas, parameters, configuration, and safety guarantees.

---

## Safety & Security Boundaries

1. **Strict Operation Allowlist:** Only 5 non-destructive operations are permitted (`CHECK_CONNECTION`, `LOCATION`, `RING`, `TRACK_LOCATION_START`, `TRACK_LOCATION_STOP`).
2. **No Destructive Operations:** Device locking, remote wiping, lost-mode PIN locks, and payment locks are deliberately omitted.
3. **Opt-in Side Effects:** Audible ringing and continuous tracking require explicit confirmation (`--yes` in CLI, `--allow-effects` in MCP).
4. **Transport Hardening:** Destination URLs and redirect targets are validated against an allowlist before attaching Bearer tokens. Non-idempotent actions are never blindly auto-retried.
5. **Private Credentials:** Master state and service files use owner-only permissions where the platform supports POSIX modes, reject unsafe symlinked paths, and redact secret-bearing model representations. Never copy state files into issues or bug reports.

## Known Limitations

- Samsung Find and SmartThings endpoints used here are private and may change without notice.
- Persistent authentication lasts only while Samsung accepts the master authorization; account-security changes or revocation can require another browser sign-in.
- A server-accepted active request does not prove that an offline or power-constrained device returned a fresh location. Check freshness, timestamp, age, accuracy, and operation state together.
- Some end-to-end encrypted location payloads may not be usable by this client.
- Device capabilities vary; absent capability data is treated as unsupported.
- The project intentionally exposes no lock, wipe, payment-lock, arbitrary dispatcher, or generic HTTP interface.

---

## Documentation

- [Project Naming & Boundaries ADR](docs/adr/0001-project-naming.md)
- [Shared Master State Specification](docs/shared-master-state-v1.md)
- [Python SDK Reference](docs/sdk.md)
- [CLI Reference & JSON Schemas](docs/cli.md)
- [MCP Server Reference](docs/mcp.md)
- [AI-Agent Integration Guide](docs/agent-integration.md)
- [Migration Guide from 0.1](docs/migration-0.2.md)
- [Release Process & Verification](docs/release.md)
- [Authentication Architecture](docs/authentication.md)
- [Technical Findings & Reverse Engineering](docs/technical-findings.md)

---

## License

MIT License. Copyright (c) 2026 Charles Bel, Hermes Agent, and contributors. See [LICENSE](LICENSE) for details.

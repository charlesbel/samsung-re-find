# samsung-re-find

[![CI](https://github.com/charlesbel/samsung-re-find/actions/workflows/ci.yml/badge.svg)](https://github.com/charlesbel/samsung-re-find/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/samsung-re-find.svg)](https://pypi.org/project/samsung-re-find/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)

An unofficial Python SDK, JSON CLI and MCP server for Samsung Find.

`samsung-re-find` can list devices returned by Samsung Find, read an available unencrypted last location, request a new location, check connectivity and battery information, and run the ring or continuous-tracking operations currently implemented by this project. Phones, tablets, SmartTags, Buds and Watches can appear in the device list, but operation support varies by category and by the data Samsung returns.

> This project is reverse-engineered and is not affiliated with or endorsed by Samsung or SmartThings. It uses private APIs that may change without notice. Use it only with accounts and devices you are authorized to access.

## Why this project exists

`samsung-re-find` targets headless Python automation. The community projects reviewed below solve useful but different problems:

- Samsung's official SmartThings Find application and website are the functional reference for locating and controlling Galaxy devices, but they are human-facing surfaces rather than a documented developer API.[4]
- The inspected public SmartThings Core SDK exposes SmartThings devices, locations, rooms and automations, but no documented Samsung Find endpoint; its `locations` are SmartThings place containers, not the live positions of Find devices.[5]
- [uTag](https://github.com/KieronQuinn/uTag) is an Android application focused on bringing extensive SmartTag functionality to non-Samsung Android devices.[1]
- [Samsung Pinger](https://github.com/VityaSchel/samsung-pinger) is a macOS ringing widget whose documented setup requires manually copying web cookies and a device ID.[2]
- [HA-SmartThings-Find](https://github.com/coldfire88/HA-SmartThings-Find) integrates location, battery and ringing into Home Assistant and now documents persistent OAuth/PKCE authentication, but its public surface is a Home Assistant integration rather than a standalone Python SDK, JSON CLI or MCP server.[3]

`samsung-re-find` is for scripts, agents and services that need a reusable **headless interface**: one interactive Samsung Account login, persistent recovery of service tokens and the Find web session, then the same typed operations through a Python SDK, versioned JSON CLI and gated stdio MCP server. It does not replace uTag's richer on-device SmartTag experience or Home Assistant's entity model, and it does not yet decode end-to-end-encrypted SmartTag locations.

What this project adds for that use case:

- persistent recovery beyond manually copied web cookies, including scoped-token rotation/reissue and web-session regeneration;
- one standalone operation model shared by the SDK, JSON CLI and MCP tools rather than an Android or Home Assistant-only surface;
- explicit separation between passive reads, active device contact, audible ringing and persistent tracking;
- versioned JSON envelopes, typed models and local state suitable for scripts, cron jobs and AI agents.

## What is included

- a typed synchronous SDK, imported as `samsung_find`;
- a JSON CLI named `samsung-re-find`;
- a stdio MCP server named `samsung-re-find-mcp`;
- a reusable Samsung Account login flow that stores a neutral master authorization locally;
- portable agent skills in `.skills/`.

<details>
<summary><strong>If you are an AI agent, install the bundled skills first</strong></summary>

First determine the local skills directory configured by your agent runtime; do not assume a framework-specific path. Set `AGENT_SKILLS_DIR` to that existing or intended directory, then copy the repository's two portable skills before operating the CLI or MCP server:

```bash
AGENT_SKILLS_DIR="/path/configured/by/your-agent"
mkdir -p "$AGENT_SKILLS_DIR"
cp -R .skills/samsung-re-find "$AGENT_SKILLS_DIR/"
cp -R .skills/samsung-account-auth "$AGENT_SKILLS_DIR/"
```

Consult your agent runtime's documentation or configuration if its skills directory is unknown. The operational skill defines device selection, location freshness and effect-confirmation rules; the account skill defines the interactive login and repair flow. Installing a skill does not install the Python package itself.

</details>

The current command set is implemented and covered by automated tests; live-device validation varies by operation and device category. It is not a complete list of operations supported by Samsung's servers. Contributions for additional devices, decoded payloads and carefully designed operations are welcome. See [Contributing](#contributing).

## Samsung RE projects

The `samsung-re-*` repositories are independent tools built around reverse-engineered Samsung services:

| Project | Install | Purpose |
| --- | --- | --- |
| [`samsung-re-find`](https://github.com/charlesbel/samsung-re-find) | `pip install samsung-re-find` | Devices, location, connectivity, ring and tracking |
| [`samsung-re-health`](https://github.com/charlesbel/samsung-re-health) | `pip install samsung-re-health` | Health Cloud synchronization, local queries and analytics |

Each project includes its own account-setup procedure. When both are installed, they reuse the same neutral Samsung Account master state while keeping their service tokens and data separate.

## Installation

Python 3.11 or newer is required. A virtual environment is recommended.

```bash
# SDK and CLI
python -m pip install samsung-re-find

# SDK, CLI and MCP server
python -m pip install 'samsung-re-find[mcp]'
```

To install from source:

```bash
git clone https://github.com/charlesbel/samsung-re-find.git
cd samsung-re-find
python -m pip install -e '.[dev,mcp]'
```

The distribution is named `samsung-re-find`; the Python import remains `samsung_find`. The old `samsung-find` and `samsung-find-mcp` executables are kept as temporary compatibility aliases.

Check the installation without contacting Samsung:

```bash
samsung-re-find --help
samsung-re-find-mcp --help
python -c "import samsung_find; print(samsung_find.__version__)"
```

## Account setup

The login flow opens Samsung's own sign-in page. This project never asks for or receives your password or second factor.

On a Linux desktop:

```bash
# Register the private ms-app:// callback handler
samsung-re-find install-handler

# Generate a Samsung login URL, then open the URL in a browser
samsung-re-find auth-start --country us --locale en-US

# After the browser returns to the local handler
samsung-re-find auth-complete
samsung-re-find account-status
samsung-re-find status
```

`install-handler` currently uses `xdg-mime` and is Linux-specific. The package does not yet provide automatic callback helpers for macOS or Windows; those platforms require an independently configured private handler for the exact `ms-app://` callback.

Successful login creates `samsung-account/master.json` in the platform's user configuration directory. It contains a private Samsung Account authorization that can be reused to derive service-specific sessions. The file is JSON protected by user-only filesystem permissions; it is not encrypted at rest. `samsung-re-health` understands the same file and also provides its own account-setup commands; neither package must be installed for the other to work.

If you are upgrading from `samsung-find-agent` 0.1, use the non-destructive migration command after reading [docs/migration-0.2.md](docs/migration-0.2.md):

```bash
samsung-re-find migrate-master
```

## CLI examples

Commands return versioned JSON envelopes on standard output. `--help` remains human-readable.

```bash
# List registered devices; internal IDs are hidden by default
samsung-re-find devices

# Inspect the operations exposed for one device
samsung-re-find capabilities "Galaxy S24"

# Read the last known location without requesting a new fix
samsung-re-find locate "Galaxy S24" --passive

# Ask the device for a new location and poll for up to 180 seconds
samsung-re-find locate "Galaxy S24" --poll-seconds 180

# Check reachability and battery information
samsung-re-find check "SmartTag2"
```

The CLI requires `--yes` before ringing a device or changing continuous tracking:

```bash
samsung-re-find ring "Galaxy S24" --status start --yes
samsung-re-find track "Galaxy S24" start --yes
```

See [docs/cli.md](docs/cli.md) for every option, output schema and exit code.

## Python SDK

```python
from samsung_find import FindConfig, SamsungFindClient

config = FindConfig(timezone="UTC")

with SamsungFindClient.from_config(config) as client:
    for device in client.list_devices():
        print(device.name, device.model)

    location = client.get_last_location("Galaxy S24")
    if location.latitude is not None:
        print(location.latitude, location.longitude, location.is_fresh)

    status = client.check_connection("SmartTag2")
    battery = status.battery if status.battery is not None else "unknown"
    print(status.success, battery)
```

The SDK exposes ring and tracking methods directly. An application using the SDK is responsible for obtaining the user's consent before calling them. The SDK reference is in [docs/sdk.md](docs/sdk.md).

## MCP server

Start the stdio server with:

```bash
samsung-re-find-mcp
```

It exposes six tools by default:

- `samsung_find_status`
- `samsung_find_list_devices`
- `samsung_find_get_capabilities`
- `samsung_find_get_last_location`
- `samsung_find_request_location`
- `samsung_find_check_connection`

The first four tools read Samsung-hosted account/device state without explicitly requesting a new device measurement; they are not offline local-cache tools. `request_location` and `check_connection` contact the device actively and may wake it or consume battery; they are therefore not annotated as read-only or idempotent.

The ring and tracking tools are not registered unless the server is started with an explicit allowlist:

```bash
samsung-re-find-mcp --allow-effects ring,tracking
```

Their tool calls still require confirmation. This protects against an assistant ringing a device or changing tracking state because of an accidental or untrusted instruction. It does not imply that other Samsung operations do not exist.

See [docs/mcp.md](docs/mcp.md) for tool schemas and host configuration.

## Local data and security

- The account master state and Find-derived sessions are separate files. Rotating the master authorization invalidates derived credentials from the previous generation.
- Secret-bearing requests reject redirects and validate their destination before sending credentials.
- State files reject unsafe symlinks and use private permissions on platforms with POSIX modes.
- Secret state is not encrypted at rest; anyone who can bypass the account's filesystem permissions may be able to reuse it.
- Device IDs are hidden from ordinary CLI and MCP output unless explicitly requested.
- The package contains no telemetry service or intermediary proxy.

Do not share callback URIs, state files, tokens or raw authenticated responses in issues.

## Current limitations

- Samsung Find uses private, undocumented APIs and can change independently of this project.
- A successful location request does not guarantee a fresh fix. The device may be offline, power constrained or unable to obtain a position; inspect the returned timestamp, age, accuracy and operation state.
- Some location payloads, notably for some SmartTag flows, are end-to-end encrypted. Their key path is not implemented yet.
- Capability flags are heuristics derived from broad device categories observed in Samsung's frontend, not an official compatibility matrix. Samsung may still refuse an advertised operation.
- Real-device validation is currently narrower than the categories that can be listed; additional synthetic fixtures and authorized device testing are welcome.
- The automatic callback handler is currently implemented only for Linux desktops.

These are a mix of private-API uncertainty and work not yet implemented. They should not be read as a complete description of Samsung's backend capabilities.

## Contributing

Pull requests are welcome, especially for:

- additional device families and synthetic fixtures;
- encrypted location decoding with a separately reviewed key path;
- macOS and Windows callback handlers;
- newly understood Samsung operations with typed interfaces and explicit safety controls;
- protocol documentation backed by reproducible evidence.

New behavior must keep tests offline, use synthetic data, avoid generic authenticated request dispatchers, and document any privacy or physical effect. High-risk operations such as lock or wipe need a separate design and security review rather than being added to the ordinary command surface.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Documentation

- [Authentication](docs/authentication.md)
- [CLI reference](docs/cli.md)
- [Python SDK](docs/sdk.md)
- [MCP server](docs/mcp.md)
- [Technical findings and implementation status](docs/technical-findings.md)
- [Shared master-state format](docs/shared-master-state-v1.md)
- [Migration from 0.1](docs/migration-0.2.md)
- [Agent integration](docs/agent-integration.md)
- [Release process](docs/release.md)

## License

MIT. See [LICENSE](LICENSE).

## Sources

[1] https://github.com/KieronQuinn/uTag
[2] https://github.com/VityaSchel/samsung-pinger
[3] https://github.com/coldfire88/HA-SmartThings-Find
[4] https://www.samsung.com/uk/apps/smartthings-find
[5] https://github.com/SmartThingsCommunity/smartthings-core-sdk

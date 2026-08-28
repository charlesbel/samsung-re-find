# samsung-find-agent

Persistent Samsung SmartThings Find access for Python programs and AI agents.

`samsung-find-agent` is an unofficial Python client, JSON CLI, and set of agent skills for interacting with devices in a Samsung Account. Its main difference from cookie-based projects is a layered authentication design that retains the Samsung application master token, rotates scoped refresh tokens, reissues them when necessary, and rebuilds the SmartThings Find web session automatically.

The repository is intended for AI-agent workflows, but the CLI can also be used directly by people, cron jobs, home-automation systems, and Python applications.

> This project is not affiliated with, endorsed by, or supported by Samsung or SmartThings. It relies on reverse-engineered, unofficial APIs that can change or be revoked without notice.

## Goals

- Provide one interactive Samsung Account login followed by persistent operation.
- Recover automatically from ordinary access-token, refresh-token, and web-cookie expiration.
- Return structured JSON suitable for AI agents.
- List and resolve devices by friendly name, model, substring, or internal ID.
- Distinguish a newly acquired location from a stale last-known location.
- Support bounded polling without confusing old operations with the current request.
- Expose useful non-destructive actions with explicit confirmation for intrusive effects.
- Keep authentication state private, atomic, and safe under concurrent agent calls.
- Document which behavior was live-tested and which remains inferred or untested.

## Safety boundary

The CLI exposes:

- authentication health;
- device listing and capability inspection;
- passive and active location;
- connection and battery checks;
- audible ring start/stop;
- continuous tracking start/stop for compatible device categories.

Audible ringing and continuous tracking require `--yes`. Locking, wiping, payment locking, and lost-mode operations are intentionally not implemented. A strict internal allowlist rejects every operation outside the five non-destructive operations exposed by the client. The helper has no generic caller-supplied payload surface: only typed ring fields can be added, and only to `RING`. Exact native string types are required before any allowlist comparison or web request. An agent must not bypass that boundary by constructing raw requests.

## How persistent authentication works

Earlier SmartThings Find projects commonly require users to copy `JSESSIONID`, `WMONID`, or device IDs from browser developer tools.[3][4][6] Those techniques can access the legacy web backend, but they do not provide a durable recovery chain when cookies expire.

uTag documents Samsung's application authentication flow: an encrypted Samsung Account sign-in yields a master `userauth_token`; that token can authorize both Samsung Find and SmartThings scopes, issue rotating access/refresh token pairs, and create new pairs after the ordinary refresh-token window ends.[1] The documented direct Find API remains incomplete for several location workflows.[2]

This project combines that application flow with an additional web-session bridge discovered during live testing:

```text
Interactive Samsung Account login
        |
        v
Persistent userauth_token
        |
        +--> Find access + rotating refresh token
        |
        +--> SmartThings access + rotating refresh token
        |
        +--> SmartThings Find getState.do bootstrap
                         |
                         v
             server-issued login state + bootstrap cookie
                         |
                         v
              regenerated authenticated JSESSIONID
                         |
                         v
                  device list and web operations
```

Normal recovery order:

1. Reuse a non-expired scoped access token.
2. Rotate the single-use refresh token under an exclusive file lock.
3. If refresh is no longer possible, issue a new scoped pair from the master token.
4. Validate the cached web cookie; if invalid, bootstrap a server-issued login state and cookie through `getState.do`, then create a new web session from the master token using the same cookie jar.
5. Retry a failed authenticated request once after `401` or `403`.

This avoids periodic manual login, but it cannot survive explicit logout, master-token revocation, account-security changes, or incompatible Samsung protocol changes. See [Persistent authentication design](docs/authentication.md) for the complete flow.

## Implemented and tested

| Feature | Implemented | Automated tests | Live-tested |
| --- | ---: | ---: | ---: |
| Initial Samsung Account login | Yes | Partial | Yes |
| Master-token persistence | Yes | Yes | Yes |
| Scoped token rotation and reissue | Yes | Yes | Yes |
| Web-session regeneration | Yes | Partial | Yes |
| Device listing | Yes | Yes | Yes |
| Passive last-known location | Yes | Yes | Yes |
| Direct active `LOCATION` | Yes | Yes | Yes |
| Connection and battery check | Yes | Yes | Yes |
| Ring start/stop | Yes | Yes | Not by this project |
| Continuous tracking start/stop | Yes | Yes | Not by this project |
| Encrypted SmartTag location | No | No | No |
| Lock, wipe, lost mode | Deliberately excluded | N/A | No |

Live tests used a real Samsung Account and a recent Galaxy phone, but all account data, names, identifiers, timestamps tied to a person, and coordinates were removed from this repository. See [Technical findings and implementation status](docs/technical-findings.md) for details.

## Requirements

- Linux
- Python 3.11 or newer
- A Samsung Account with SmartThings Find enabled
- A desktop browser for the initial login
- `xdg-mime` for automatic handling of the private `ms-app://` callback

The runtime dependencies are `httpx` and `cryptography`.

## Installation

Clone and install in a virtual environment:

```bash
git clone https://github.com/charlesbel/samsung-find-agent.git
cd samsung-find-agent
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
```

For development:

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python -m build
```

The installed console command is `samsung-find`. Examples below use that command; use `.venv/bin/samsung-find` if the virtual environment is not activated.

## Initial authentication

Register the private callback handler:

```bash
samsung-find install-handler
```

Generate the Samsung Account login URL using your locale:

```bash
samsung-find auth-start --country us --locale en-US
```

Open the returned URL in a trusted desktop browser and complete Samsung Account authentication. The password and second factor remain on Samsung's page and are not stored by this project.

After the browser invokes the `ms-app://` callback:

```bash
samsung-find auth-complete
samsung-find status
samsung-find verify
```

Expected health fields:

```json
{
  "persistent_master_token_present": true,
  "web_session_valid": true
}
```

The complete login URL and callback URI are transient secrets. Do not paste them into an issue, agent conversation, shell history, or log. The fallback for systems that cannot register the callback scheme is documented in [docs/authentication.md](docs/authentication.md).

## Configuration

Default private state location:

```text
~/.config/samsung-find/state.json
```

Global options must appear before the subcommand:

```bash
samsung-find \
  --country US \
  --language en \
  --timezone America/New_York \
  devices
```

Equivalent environment variables:

```text
SAMSUNG_FIND_COUNTRY
SAMSUNG_FIND_LANGUAGE
SAMSUNG_FIND_TIMEZONE
```

The timezone must be an IANA timezone name. The public default is `UTC`.

Custom private paths are available through `--state`, `--pending`, and `--redirect-file`.

## CLI usage

### Authentication health

```bash
samsung-find status
samsung-find verify
```

`status` reports only booleans and never prints the login address or token values.

### Devices

```bash
samsung-find devices
samsung-find capabilities "Primary Galaxy Phone"
```

Internal device IDs are omitted by default. A technical workflow can opt in:

```bash
samsung-find devices --include-ids
```

### Connection and battery

```bash
samsung-find check "Primary Galaxy Phone" --poll-seconds 60
```

The result contains the terminal operation state and battery percentage when Samsung returns it.

### Passive location

```bash
samsung-find locate "Primary Galaxy Phone" --passive
```

Passive mode does not request a new fix. Always inspect `last_update` and `age_seconds` before describing the location as current.

### Active location

```bash
samsung-find locate "Primary Galaxy Phone" --poll-seconds 180
```

The client:

1. reads a baseline location;
2. submits the dedicated `LOCATION` operation;
3. polls the current request to a terminal state;
4. reads the newest location again;
5. sets `fresh_location_obtained` only when the new timestamp is newer than the baseline.

A successful request does not automatically mean that the returned coordinates are fresh. Agents must inspect `fresh_location_obtained` and `age_seconds`.

### Ring

Only after an explicit request that accepts an audible side effect:

```bash
samsung-find ring "Primary Galaxy Phone" --yes
samsung-find ring "Primary Galaxy Phone" --status stop --yes
```

Do not use ringing as a generic connectivity test.

### Continuous tracking

Only after an explicit request that accepts a persistent state change:

```bash
samsung-find track "Primary Galaxy Phone" start --yes
samsung-find track "Primary Galaxy Phone" stop --yes
```

The capability model exposes tracking only for phone and tablet categories.

## AI-agent skills

The `skills/` directory contains two portable Markdown skills:

- `samsung-find-agent`: safe operational use, device resolution, freshness interpretation, and action policy;
- `samsung-find-auth`: initial login and repair of persistent authentication.

Install them from a repository checkout; the Python wheel installs the CLI package but does not copy framework-specific skill directories. For Hermes Agent:

```bash
mkdir -p ~/.hermes/skills/smart-home
cp -R skills/samsung-find-agent ~/.hermes/skills/smart-home/
cp -R skills/samsung-find-auth ~/.hermes/skills/smart-home/
```

Restart or reload the agent's skill index if required by the framework. Other agent systems can ingest the Markdown directly or translate it to their own policy format.

The operational skill instructs an agent to:

- use exact safe commands rather than raw HTTP requests;
- list devices when selection is ambiguous;
- check capabilities before action;
- distinguish fresh from last-known locations;
- avoid exposing exact coordinates or internal identifiers unnecessarily;
- require explicit intent for ring and tracking;
- refuse destructive operations.

See [AI-agent integration guide](docs/agent-integration.md).

## Python API

The CLI is the stable agent-facing surface, but the package can also be imported:

```python
from samsung_find.api import SamsungFindClient
from samsung_find.auth import SamsungAuth
from samsung_find.constants import DEFAULT_PENDING_PATH, DEFAULT_STATE_PATH


auth = SamsungAuth(DEFAULT_STATE_PATH, DEFAULT_PENDING_PATH)
client = SamsungFindClient(
    auth,
    country="US",
    language="en",
    timezone="America/New_York",
)

try:
    devices = client.devices()
    location = client.locate("Primary Galaxy Phone", poll_seconds=180)
finally:
    client.close()
    auth.close()
```

Treat `devices()` as an internal API: it includes raw protocol fields used by operation methods. Do not log or forward the raw structure to an unrelated model.

## Technical findings

### Active location uses `LOCATION`, not connection polling

The legacy web backend supports an operation lifecycle around `addOperation.do` and `getOperationResult.do`.[3] During live testing, polling `CHECK_CONNECTION_WITH_LOCATION` for three minutes did not create a new fix. The current frontend's dedicated `LOCATION` operation completed in approximately three to four seconds on the tested phone. The client therefore uses `LOCATION` and retains a 180-second upper bound for slower or disconnected devices.

### Current-request filtering is mandatory

The backend can retain previous operation entries. The poller filters by operation type and the current `reqId`; it never falls back to an older completed request when the current one has no result yet.

### `in_progress` is not terminal

Status values associated with progress continue polling. Only a normalized `success` or `failed` result terminates early.

### Some locations are encrypted

The location reader accepts plain `LOCATION`, `LASTLOC`, and `OFFLINE_LOC` entries. Encrypted `encLocation` entries are skipped until the Samsung Find E2E key flow is implemented. uTag documents the currently known direct Find key endpoints and notes that the API surface is incomplete.[2]

## State security

- State and callback files are written with mode `0600`.
- Parent directories use mode `0700`.
- Token mutation is serialized with `fcntl.flock`.
- State replacement is atomic and uses `fsync` plus `os.replace`.
- The redirect callback is consumed and deleted.
- Error messages omit response bodies.
- `.gitignore` excludes state, callbacks, archives, environments, caches, and common secret files.

Read [SECURITY.md](SECURITY.md) before adding fixtures or diagnostic logs.

## Current limitations

- Samsung does not publish or support this API contract.
- The initial callback helper is Linux-specific.
- Ring and continuous tracking are implemented and unit-tested but were not triggered during this project's live validation.
- Device categories are coarse and a backend may reject a capability advertised for a particular model.
- SmartTag E2E-encrypted locations are not implemented.
- There is no daemon, MCP server, or formal JSON Schema yet.
- Active location can consume battery or wake a device.
- A revoked master token still requires a new interactive login.

## Roadmap

- Add an optional MCP server and formal JSON Schemas.
- Support encrypted SmartTag locations after a separate security review.
- Add callback helpers for macOS and Windows.
- Expand anonymized fixtures across device classes.
- Add privacy-preserving coarse-location output.
- Track protocol changes and expose compatibility diagnostics without leaking account data.

## Prior art and sources

- uTag authentication documentation established the application master-token and rotating scoped-token model.[1]
- uTag's Find API notes document the known direct Find headers and E2E key endpoints.[2]
- VityaSchel's reverse-engineering gist identified the legacy web operation surface, including ring, connection, and location operations.[3]
- Samsung Pinger demonstrated a practical ring client but required manually copied cookies and a device ID.[4]
- The OAuth Home Assistant fork explored PKCE and SmartThings installed-app access for multiple device categories.[5]
- Jeena's maintained Home Assistant integration provided additional reference behavior for the legacy web session and device operations.[6]

Contributions and protocol corrections are welcome. Never attach real authentication material, raw account responses, or exact personal location data to an issue.

## License

MIT. See [LICENSE](LICENSE).

## Sources

[1] https://github.com/KieronQuinn/uTag/wiki/Authentication
[2] https://github.com/KieronQuinn/uTag/wiki/Find-API-Calls
[3] https://gist.github.com/VityaSchel/fe8945c0189bbaabed420003bdf3216d
[4] https://github.com/VityaSchel/samsung-pinger
[5] https://github.com/coldfire88/HA-SmartThings-Find
[6] https://git.jeena.net/jeena/HA-SmartThings-Find

Published by Hermes Agent under the instructions of Charles.

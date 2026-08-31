# Technical findings and implementation status

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

This project combines published reverse-engineering work with additional live protocol testing. It is not affiliated with Samsung or SmartThings.

## Prior work

uTag provides the most complete public description of Samsung's application authentication flow, including the master `userauth_token`, PKCE authorization, rotating refresh tokens, and documented parts of `api.samsungfind.com`.[1][2]

VityaSchel documented the legacy web operations endpoint and demonstrated `RING`, `CHECK_CONNECTION`, and `LOCATION`, but the original workflow depended on manually copied cookies.[3][4] Home Assistant integrations provided additional device parsing and active/passive location references; the maintained Jeena version still documents manual `JSESSIONID` authentication, while an OAuth fork explores SmartThings installed-app access.[5][6]

## Additional findings in this project

### Master-token-to-web-session bridge

A master `userauth_token` can authorize the SmartThings Find web client and create a fresh authenticated `JSESSIONID`. The current frontend first requires `getState.do` to issue both an opaque login state and a bootstrap cookie; `login.do` must receive that exact state through the same cookie jar. A random caller-generated state now produces a cookie that fails `chkLogin.do`. Preserving the frontend bootstrap sequence allows the legacy phone/device web API to recover from ordinary cookie expiration without storing a Samsung password or repeating two-factor authentication.

### Direct active location operation

`CHECK_CONNECTION_WITH_LOCATION` was not a reliable active-location trigger in live testing. A three-minute poll returned no new fix. The current Samsung frontend exposes a dedicated `LOCATION` operation with its own lifecycle:

```text
POST /dm/addOperation.do
POST /dm/getOperationResult.do
POST /device/setLastSelect.do
```

On a recent Galaxy phone, the direct operation completed in approximately three to four seconds and the subsequent location read returned a new fix. The CLI keeps a 180-second default bound because device connectivity can vary.

### Polling rules

- `in_progress` is not terminal.
- Only terminal `success` or `failed` results stop polling early.
- The backend operation payload contains an internal `reqId`; the poller retains it for current-request filtering, while the public v1 CLI model exposes only the normalized operation result.
- The internal operation helper enforces a closed allowlist containing only connection check, location, ring, and tracking start/stop.
- The helper has no generic caller-supplied payload parameter. Only typed ring status/message fields can be added, and only for `RING`.
- Operation and ring fields must be exact native strings, preventing deceptive subclasses from bypassing comparisons.
- Destructive operation names and invalid typed fields are rejected before a web session is opened.
- Results are filtered by both operation type and the current `reqId`.
- Old completed operations are never substituted when the current request has no result yet.
- Freshness compares the timestamp before and after the active operation; the public `is_fresh` field is not inferred merely from request acceptance.

### Location parsing

The web response may contain `LOCATION`, `LASTLOC`, or `OFFLINE_LOC` entries. The client selects the newest usable timestamp. Plain coordinates are parsed; end-to-end-encrypted `encLocation` payloads are skipped because the key derivation and decryption chain are not implemented.

## Operation status

| Capability | Implemented | Automated tests | Live tested by this project | Notes |
| --- | ---: | ---: | ---: | --- |
| Initial Samsung Account login | Yes | Partial | Yes | Interactive browser step required once |
| Master token persistence | Yes | Yes | Yes | Root for scoped token and web-session recovery |
| Access-token refresh rotation | Yes | Yes | Yes | New refresh token replaces the old one |
| Reissue after dead refresh token | Yes | Yes | Yes | Uses the master token |
| Web-session regeneration | Yes | Yes | Yes | `getState.do` bootstrap; validated through `chkLogin.do` and `_csrf` |
| Device listing | Yes | Yes | Yes | Internal IDs hidden by default in CLI output |
| Passive location read | Yes | Yes | Yes | May be stale; inspect `age_seconds` |
| Direct active `LOCATION` | Yes | Yes | Yes | Fresh fix observed on a recent Galaxy phone |
| Connection check and battery | Yes | Yes | Yes | Battery depends on device/backend response |
| Ring start/stop | Yes | Yes | No | Requires explicit `--yes`; backend support varies |
| Continuous tracking start/stop | Yes | Yes | No | Phone/tablet only; requires explicit `--yes` |
| SmartTag encrypted location | No | No | No | Requires E2E key support |
| Lost mode | No | No | No | Sensitive; not exposed |
| Remote lock | No | No | No | Sensitive; deliberately not exposed |
| Remote wipe | No | No | No | Destructive; deliberately not exposed |

No personal device name, identifier, coordinate, account address, or raw live response is included in the repository or its test fixtures.

## Device capability model

The current capability mapping is deliberately conservative:

- passive and active location plus connection checks are exposed for listed devices;
- ringing is advertised for phone, tablet, watch, buds, tag, and VR categories observed in the frontend;
- continuous tracking is advertised only for phones and tablets;
- destructive operations are represented as `discovered_not_exposed` and have no execution method.

This is a frontend-derived capability model, not an official compatibility contract. Samsung may reject an operation for a particular model or account.

## Known limitations

- The service and endpoints are unofficial and may change.
- Device availability, battery, settings, and nearby Galaxy devices affect results.
- Active location can wake a device and consume battery.
- Some locations are E2E encrypted and currently unavailable.
- Capability detection is based on coarse device categories.
- The initial callback flow is easiest on a Linux desktop with `xdg-mime`.
- Windows and macOS callback helpers are not implemented.
- There is no long-running network daemon. Version 0.2.0 provides a local stdio MCP server and formal v1 JSON Schemas.

## Roadmap

1. Add encrypted SmartTag location support with a separately audited key path.
2. Add non-Linux callback helpers.
3. Expand synthetic fixtures for watches, earbuds, tablets, and SmartTags.
4. Add optional privacy-preserving output modes for coarse location.
5. Add integration tests against recorded, fully redacted HTTP fixtures.

## Sources

[1] https://github.com/KieronQuinn/uTag/wiki/Authentication
[2] https://github.com/KieronQuinn/uTag/wiki/Find-API-Calls
[3] https://gist.github.com/VityaSchel/fe8945c0189bbaabed420003bdf3216d
[4] https://github.com/VityaSchel/samsung-pinger
[5] https://github.com/coldfire88/HA-SmartThings-Find
[6] https://git.jeena.net/jeena/HA-SmartThings-Find

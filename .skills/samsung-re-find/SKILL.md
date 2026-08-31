---
name: samsung-re-find
description: Locate and inspect Samsung Find devices safely.
version: 0.2.2
author: Charles Bel, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [samsung, smartthings-find, device-location, mcp]
---

# Samsung Find

Operate the installed `samsung-re-find` JSON CLI or its stdio MCP server. This is an unofficial reverse-engineered integration, not affiliated with Samsung or SmartThings; it deliberately exposes no lock, wipe, payment-lock, or arbitrary-request capability.

## When to Use

- List Samsung phones, tablets, watches, earbuds, or tags registered to the authenticated account.
- Inspect capabilities, connectivity, battery, or the last reported location.
- Request a fresh location when the user explicitly wants a current fix.
- Ring a device or change continuous tracking only after explicit user authorization.
- Diagnose or migrate Samsung Account authentication used by Find and companion tools.

Do not use it for devices the user does not own or administer, covert tracking, destructive actions, or raw private-API requests.

## Prerequisites

1. Install the package with `terminal(command="python -m pip install 'samsung-re-find[mcp]'")`, preferably in a virtual environment or tool installer.
2. Use the canonical executables `samsung-re-find` and `samsung-re-find-mcp`. The `samsung-find` aliases are transitional compatibility only.
3. Authentication is discovered through platform-standard user directories. The neutral master state is named `samsung-account/master.json`; Find-derived state is separate and must never contain a copied master token.
4. Never read, print, upload, commit, or place raw state, tokens, cookies, callback URLs, internal IDs, or authorization headers in agent context.
5. For first login or legacy migration, follow the companion `.skills/samsung-account-auth/SKILL.md` procedure from the cloned repository.

## How to Run

Invoke CLI commands through `terminal`, parse only stdout as the versioned JSON envelope, and treat stderr as diagnostics:

```text
terminal(command="samsung-re-find status")
terminal(command="samsung-re-find verify")
terminal(command="samsung-re-find devices")
terminal(command="samsung-re-find capabilities '<unique device query>'")
terminal(command="samsung-re-find locate '<unique device query>' --passive")
terminal(command="samsung-re-find locate '<unique device query>' --poll-seconds 180")
terminal(command="samsung-re-find check '<unique device query>' --poll-seconds 40")
```

Executed commands use a JSON envelope with `ok`, `schema_version`, and either `data` or `error`; informational `--help` output is plain text. Exit codes are: `0` success, `1` device/operation failure, `2` usage error, `3` authentication required, `4` network/protocol failure, and `5` storage/security failure.

For MCP, configure the local stdio command `samsung-re-find-mcp`. It opens no network listener.

## Quick Reference

| Intent | CLI | MCP tool | Effect |
|---|---|---|---|
| Authentication status | `status` | `samsung_find_status` | Local/read-only |
| List devices | `devices` | `samsung_find_list_devices` | Read-only; IDs hidden by default |
| Capabilities | `capabilities QUERY` | `samsung_find_get_capabilities` | Read-only |
| Last known location | `locate QUERY --passive` | `samsung_find_get_last_location` | Read-only |
| Fresh location | `locate QUERY` | `samsung_find_request_location` | Active device poll |
| Connectivity/battery | `check QUERY` | `samsung_find_check_connection` | Active device poll |
| Ring start/stop | `ring QUERY --status start|stop --yes` | `samsung_find_ring` | Audible side effect |
| Tracking start/stop | `track QUERY start|stop --yes` | `samsung_find_set_tracking` | Persistent state change |

MCP exposes only the first six tools by default. Start it with `--allow-effects ring`, `--allow-effects tracking`, or `--allow-effects ring,tracking` only when the host configuration intentionally permits those effects. Tool calls still require explicit confirmation arguments.

## Procedure

1. **Check local readiness.** Run `terminal(command="samsung-re-find status")`. Continue when the success envelope reports usable master/derived state; otherwise use the authentication skill. Completion criterion: a structured result is obtained without exposing state contents.
2. **Verify only when network validation is needed.** Run `terminal(command="samsung-re-find verify")`. This may contact Samsung and renew derived session material. Completion criterion: the result distinguishes valid connectivity from authentication or network failure.
3. **Resolve the device.** Run `terminal(command="samsung-re-find devices")`; do not add `--include-ids` unless an internal ID is strictly required for a technical task. Select a unique name or model. If ambiguous, ask the user. Completion criterion: exactly one device is selected without disclosing its internal ID.
4. **Check capabilities.** Before any active or side-effect operation, run `terminal(command="samsung-re-find capabilities '<query>'")`. Missing capability fields are fail-closed and do not imply support. Completion criterion: the requested capability is explicitly true.
5. **Choose passive or active location honestly.** Use `--passive` for the last known fix. Use active `locate` only for a requested fresh fix. Inspect freshness, timestamp, age, accuracy, operation status, and map URL together. Completion criterion: report either “fresh position” or “last known position” without conflating request acceptance with device response.
6. **Report minimally.** Give the device name/model, freshness, localized timestamp, age, accuracy when available, and a map link. Suppress exact coordinates, internal IDs, request IDs, and raw payloads unless the authorized user explicitly needs them.
7. **Gate physical effects.** Ring or tracking requires an explicit request in the current conversation, a positive capability, and the CLI `--yes` flag. Start MCP with the matching `--allow-effects` option only when needed. Completion criterion: the requested effect and target are unambiguous before dispatch.
8. **Verify the outcome.** Wait for a terminal operation result where supported. Do not call `in_progress` success, and do not claim the device rang, tracked, or refreshed merely because Samsung accepted the request.

## Authentication and Migration

- `samsung-re-find status` is local; `verify` tests live connectivity.
- `samsung-re-find migrate-master` non-destructively converts supported legacy state into the neutral master-state v1 and separate derived state. Back up first; do not use `--force` unless the user has approved replacing an existing target.
- First login uses `install-handler`, `auth-start`, and `auth-complete` on Linux desktops with `xdg-mime`. On macOS or Windows, provision the neutral master state from a supported environment until native callback helpers exist. Credentials and MFA are entered only into Samsung’s trusted login surface, never CLI arguments or chat.
- Migration must leave the legacy source untouched and produce owner-only files that can be immediately reloaded.

## Pitfalls

- The service is private and undocumented; Samsung may change it without notice.
- A successful active request does not prove a fresh fix was returned.
- Offline devices, disabled location, power saving, network loss, or E2EE data can leave only an old or unusable position.
- Do not guess that a device supports ringing or tracking from its type.
- Do not bypass the narrow SDK/CLI/MCP surface with generic HTTP calls.
- Do not run concurrent manual credential renewals; rotating material may be single-use.
- `--include-ids`, raw coordinates, and callback data increase privacy exposure and are not normal user-facing output.

## Verification

A workflow is complete only when:

1. `status` or `verify` returned a structured, understood result;
2. the device query resolved uniquely;
3. the requested operation reached a terminal result or was clearly reported as incomplete;
4. location freshness and uncertainty were stated accurately;
5. no secret, internal identifier, callback URL, or raw authenticated payload appeared in logs or the response;
6. side effects occurred only after explicit authorization.

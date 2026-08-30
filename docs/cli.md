# Samsung Find CLI Reference

`samsung-re-find` provides a versioned JSON CLI for automation. The legacy `samsung-find` executable is a transitional alias.

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Private APIs may change without notice.

## Installation

```bash
python -m pip install samsung-re-find
samsung-re-find --help
```

## JSON Contract

Stdout contains a v1 success or error envelope:

```json
{"ok": true, "schema_version": "1.0", "data": {}, "meta": {}}
```

```json
{"ok": false, "schema_version": "1.0", "error": {"code": "auth_required", "message": "..."}}
```

`--legacy-json` retains the pre-0.2 raw dictionary form temporarily. New integrations must use the versioned envelope and packaged schemas.

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General device or operation failure |
| `2` | Usage / argument-validation error |
| `3` | Authentication required or revoked |
| `4` | Network / remote-protocol error |
| `5` | Local storage, permission, or security error |


## Global Options

- `--master-state PATH`: neutral master-state v1 override.
- `--state PATH`: Find-derived state override.
- `--legacy-state PATH`: legacy migration/fallback state override.
- `--pending PATH`: pending authentication-state override.
- `--redirect-file PATH`: private captured callback override.
- `--country CODE`: default `US` or `SAMSUNG_FIND_COUNTRY`.
- `--language CODE`: default `en` or `SAMSUNG_FIND_LANGUAGE`.
- `--timezone IANA_ZONE`: default `UTC` or `SAMSUNG_FIND_TIMEZONE`.
- `--legacy-json`: compatibility output without the v1 envelope.

## Authentication

```bash
samsung-re-find install-handler
samsung-re-find auth-start [--country CODE] [--locale LOCALE]
samsung-re-find auth-complete
samsung-re-find status
samsung-re-find verify
```

- `install-handler` registers the private desktop callback catcher where supported.
- `auth-start` creates pending PKCE state and returns the Samsung login URL.
- `auth-complete` consumes the private captured redirect and deletes the callback artifact.
- `status` is a local readiness check.
- `verify` performs live connectivity/session verification and may renew derived state.

Passwords and second factors are entered only on Samsung’s sign-in page. Callback URIs, state files, tokens, and cookies are secrets and must never enter chat, shell history, logs, or issues.

## Legacy Migration

```bash
samsung-re-find migrate-master [--from-state PATH] [--force]
```

Migration creates neutral master-state v1 and separate Find-derived state without modifying the legacy source. Back up before migration. `--force` can replace an existing target and must be used only after deliberate review.

## Devices and Capabilities

```bash
samsung-re-find devices [--include-ids]
samsung-re-find capabilities QUERY
```

Internal IDs are hidden by default. Resolve by a unique user-visible name or model; if a query is ambiguous, refine it rather than guessing. Missing capability data is fail-closed.

## Location

```bash
# Last known fix; no fresh-device request
samsung-re-find locate QUERY --passive

# Active location request and polling
samsung-re-find locate QUERY [--poll-seconds SECONDS]
```

A server-accepted request is not proof of a fresh fix. Evaluate timestamp, `is_fresh`, age, accuracy, operation state, and map URL together. Protect exact coordinates and internal identifiers.

## Connectivity and Battery

```bash
samsung-re-find check QUERY [--poll-seconds SECONDS]
```

The result distinguishes acceptance, terminal success/failure, and battery information when reported. Do not call an `in_progress` operation successful.

## Explicit Side Effects

```bash
samsung-re-find ring QUERY [--status start|stop] [--message TEXT] \
  [--poll-seconds SECONDS] --yes

samsung-re-find track QUERY start|stop [--poll-seconds SECONDS] --yes
```

`ring` produces an audible physical effect; `track` changes persistent continuous-tracking state. Both require `--yes`, a uniquely resolved device, a positive capability, and explicit user authorization. The project exposes no lock, wipe, payment-lock, or arbitrary request command.

## MCP

Install the optional dependency and use the local stdio executable:

```bash
python -m pip install 'samsung-re-find[mcp]'
samsung-re-find-mcp
samsung-re-find-mcp --allow-effects ring,tracking
```

Read/safe tools are available by default. Ringing and tracking tools are absent unless enabled at server startup and still require confirmation in each call. See [MCP Reference](mcp.md).

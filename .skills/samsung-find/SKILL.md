---
name: samsung-find
description: "Locate and manage Samsung devices safely via CLI or MCP."
version: 0.2.0
author: Charles Bel, Hermes Agent
license: MIT
platforms: [linux, darwin, windows]
metadata:
  hermes:
    tags: [samsung, smartthings-find, device-location, smart-home, mcp]
---

# Samsung Find Agent Integration

Use this skill when an AI agent needs to discover, locate, check status, or safely ring/track Samsung devices and SmartTags.

## When to Use

- Discovering registered Samsung devices (phones, tablets, SmartTags, Galaxy Buds, Galaxy Watches).
- Checking device battery level and connectivity reachability.
- Looking up last reported passive GPS fix or requesting active real-time GPS location.
- Ringing lost devices or setting lost-mode continuous tracking upon explicit user confirmation.

## Prerequisites

- `samsung-find` (or `samsung-find-mcp`) installed in the environment.
- Valid authentication present in shared master state (`samsung-account/master.json`) or legacy state.
- Never read, write, or display raw state files or private token strings in agent context.

## How to Run

### Via CLI

```bash
# List devices
samsung-find devices

# Check reachability and battery
samsung-find check "<device-name>"

# Query passive location (cached)
samsung-find locate "<device-name>" --passive

# Request fresh location fix (active GPS polling)
samsung-find locate "<device-name>" --poll-seconds 180
```

### Via MCP (Model Context Protocol)

Launch `samsung-find-mcp` (or with `--allow-effects ring,tracking` for audible alarms and continuous tracking).

Call narrow MCP tools:
- `samsung_find_list_devices`
- `samsung_find_get_capabilities`
- `samsung_find_get_last_location`
- `samsung_find_request_location`
- `samsung_find_check_connection`

## Quick Reference

| Action | CLI Command | MCP Tool | Safe Default? |
|---|---|---|---|
| List devices | `samsung-find devices` | `samsung_find_list_devices` | Yes (IDs hidden) |
| Device features | `samsung-find capabilities "<query>"` | `samsung_find_get_capabilities` | Yes |
| Last known fix | `samsung-find locate "<query>" --passive` | `samsung_find_get_last_location` | Yes |
| Fresh GPS poll | `samsung-find locate "<query>"` | `samsung_find_request_location` | Yes |
| Reachability/Battery | `samsung-find check "<query>"` | `samsung_find_check_connection` | Yes |
| Audible alarm | `samsung-find ring "<query>" --yes` | `samsung_find_ring` | Requires confirmation |
| Lost tracking | `samsung-find track "<query>" start --yes` | `samsung_find_set_tracking` | Requires confirmation |

## Procedure

1. **Verify Health:** Verify authentication using `samsung-find verify` or `samsung_find_status`.
2. **Find Device:** Call `devices` to find exact device name. Never guess internal IDs.
3. **Check Capabilities:** If attempting an operation, verify device support via `capabilities`.
4. **Locate:** For battery-efficient read, use passive locate. If user specifically requests real-time location, use active locate.
5. **Audible Ringing / Tracking:** Require explicit user confirmation before ringing or toggling tracking.

## Pitfalls

- **Do Not Guess IDs:** Device names should match those returned by `devices`.
- **Coordinate Privacy:** Avoid printing full raw coordinates unless explicitly asked; prefer city/locality/map link.
- **Side Effects:** Never ring devices or toggle tracking without explicit consent (`--yes`).
- **No Destructive Operations:** Samsung Find does not expose lock, wipe, or payment features. Never attempt to construct raw requests.

## Verification

Run `samsung-find verify` or `samsung_find_status` to ensure healthy persistent connection.

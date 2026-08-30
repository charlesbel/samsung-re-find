# Samsung Find CLI Reference

`samsung-find` provides a contractually stable JSON CLI for script automation and machine integrations.

## Standard Output Contract

By default, all CLI command outputs on `stdout` are wrapped in a versioned JSON envelope (`schema_version: "1.0"`):

### Success Envelope

```json
{
  "ok": true,
  "schema_version": "1.0",
  "data": { ... },
  "meta": { ... }
}
```

### Error Envelope

```json
{
  "ok": false,
  "schema_version": "1.0",
  "error": {
    "code": "auth_required",
    "message": "Authentication required: run 'samsung-find auth-start'"
  }
}
```

If you need the raw un-enveloped JSON dictionary format from v0.1, supply the `--legacy-json` flag.

## Standard Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Usage / CLI argument validation error |
| `3` | Authentication required / credentials revoked |
| `4` | Network / remote protocol error |
| `5` | Local storage / permission / security error |
| `6` | Partial result |
| `1` | General operation or device failure |

## Global Options

- `--master-state PATH` - Explicit path to shared Samsung master state v1
- `--state PATH` - Service-specific state path (default: `~/.config/samsung-find/state.json`)
- `--country CODE` - Country code (default: `US` or `$SAMSUNG_FIND_COUNTRY`)
- `--language CODE` - Language code (default: `en` or `$SAMSUNG_FIND_LANGUAGE`)
- `--timezone TZ` - IANA timezone (default: `UTC` or `$SAMSUNG_FIND_TIMEZONE`)
- `--legacy-json` - Output raw JSON without v1 envelope

## Core Commands

### Authentication
```bash
samsung-find auth-start [--country us] [--locale en-US]
samsung-find auth-complete
samsung-find migrate-master [--from-state PATH] [--force]
samsung-find status
samsung-find verify
```

### Devices & Location
```bash
# List devices
samsung-find devices [--include-ids]

# Show device capabilities
samsung-find capabilities "Galaxy S24"

# Get last known location
samsung-find locate "Galaxy S24" --passive

# Request fresh location fix (active GPS poll)
samsung-find locate "Galaxy S24" [--poll-seconds 180]

# Check reachability and battery
samsung-find check "SmartTag2"
```

### Active Operations (Explicit Confirmation Required)
```bash
# Ring device (requires --yes confirmation)
samsung-find ring "Galaxy S24" --status start --yes

# Continuous tracking (requires --yes confirmation)
samsung-find track "SmartTag2" start --yes
```

# Shared Samsung Account Master State Contract (v1)

This specification defines the neutral, shared authentication state schema (`master-state-v1`) used across Samsung ecosystem client tools (such as `samsung-re-find` and `samsung-re-health`).

## Architecture & Responsibilities

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
```

- **Primary Writer:** `samsung-re-find` interactive authentication flow (`auth-start` / `auth-complete`).
- **Readers:** `samsung-re-find` and `samsung-re-health`.
- **Health Write Policy:** Strict read-only. `samsung-re-health` NEVER writes or modifies the master state file.
- **Derived Token Storage:** Service-specific derived tokens (e.g. Find `offline.access`, SmartThings `iot.client`, web session cookies, Health sync checkpoints) are stored strictly in their respective service state files (`samsung-find/state.json`, `samsung-health/state.json`) and NEVER in `master.json`.

## Resolution Priority

Both repositories resolve the master state location using the identical priority order:

1. Explicit credential provider injected by the Python SDK.
2. CLI/MCP `--master-state` argument.
3. Environment variable `SAMSUNG_ACCOUNT_MASTER_STATE`.
4. Default `platformdirs` location:
   - Linux: `${XDG_CONFIG_HOME:-~/.config}/samsung-account/master.json`
   - macOS: `~/Library/Application Support/samsung-account/master.json`
   - Windows: `%APPDATA%\samsung-account\master.json`
5. Legacy fallback: `~/.config/samsung-find/state.json` (read-only migration fallback).

## Schema Definition

The formal JSON Schema is located at `schemas/master-state-v1.schema.json`.

Key fields:
- `schema`: Constant `"io.github.charlesbel.samsung-account.master"`
- `schema_version`: Constant integer `1`
- `generation`: Opaque unique string identifier (e.g. UUID), regenerated whenever credentials rotate.
- `created_at`: Unix timestamp (float/int).
- `updated_at`: Unix timestamp (float/int).
- `account`: Contains `login_id` (string) and optional `user_id`.
- `installation`: Contains `physical_address` (string).
- `identity`: Contains `auth_server_url` (HTTPS Samsung host) and `userauth_token` (master authentication token).

## Security & Storage Properties

- **File Permissions:** Master file mode `0600` (`-rw-------`), parent directory mode `0700` (`drwx------`).
- **Atomic Commits:** Writes are staged to a temporary file in the same directory, followed by `fsync` and atomic rename (`os.replace`).
- **Symlink Protection:** Readers and writers explicitly reject symlinks and non-owned files.
- **Redaction:** In-memory models implement strict redaction in `__repr__` and `__str__`. Tokens and sensitive fields are never printed in logs, errors, or CLI outputs.

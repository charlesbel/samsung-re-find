# Shared Samsung Account Master State Contract (v1)

This specification defines the neutral, shared authentication state schema (`master-state-v1`) used across Samsung ecosystem client tools (such as `samsung-re-find` and `samsung-re-health`).

## Architecture & Responsibilities

```text
Samsung Account interactive login
 (samsung-re-find or samsung-re-health)
                    │
                    ▼
     Shared Neutral Master State v1
     (samsung-account/master.json)
           │                  │
           ▼                  ▼
  Samsung Find State   Samsung Health State
  (derived tokens)     (derived tokens & mirror)
```

- **Explicit writers:** either `samsung-re-find` or `samsung-re-health` may create or replace the master through its interactive `auth-start` / `auth-complete` flow.
- **Ordinary readers:** service initialization, refresh and synchronization read the master but do not rewrite it.
- **Generation boundary:** replacing the master creates a new generation; each service rejects or reinitializes derived credentials from an older generation.
- **Derived token storage:** Find tokens and web cookies remain in `samsung-find/state.json`; Health tokens and registration state remain in `samsung-health-cloud/state.json`; Health records and checkpoints remain in the Health SQLite mirror. None of these derived values belongs in `master.json`.

## Resolution Priority

The shared contract defines this resolution priority; implementations should preserve it or document a versioned incompatibility:

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
- `generation`: Opaque unique string identifier (e.g. UUID), regenerated when an explicit account bootstrap replaces the master authorization. Ordinary service-token refresh does not rotate it.
- `created_at`: Unix timestamp (float/int).
- `updated_at`: Unix timestamp (float/int).
- `account`: Contains `login_id` (string) and optional `user_id`.
- `installation`: Contains `physical_address` (string).
- `identity`: Contains `auth_server_url` (HTTPS Samsung host) and `userauth_token` (master authentication token).

## Security & Storage Properties

- **File Permissions:** On POSIX platforms, master file mode `0600` (`-rw-------`) and parent directory mode `0700` (`drwx------`); other platforms use the strongest equivalent checks implemented by the client.
- **Atomic Commits:** Writes are staged to a temporary file in the same directory, followed by `fsync` and atomic rename (`os.replace`).
- **Symlink Protection:** Readers and writers explicitly reject symlinks and non-owned files.
- **Redaction:** Project-owned `__repr__`, `__str__`, CLI status and normal error serializers redact known token fields. Raw state files, debuggers, process memory and caller-defined SDK logging remain outside that guarantee.

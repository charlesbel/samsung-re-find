# Pre-Migration Baseline (v0.1.0)

This document captures the audit baseline for `samsung-find-agent` at release 0.1.0 before implementing the 0.2.0 ecosystem changes.

## Baseline Metadata

- **Package Name:** `samsung-find-agent`
- **Version:** `0.1.0`
- **Import Name:** `samsung_find`
- **CLI Name:** `samsung-find`
- **Git Commit:** `aed165e` (`fix(auth): preserve Samsung web login bootstrap state`)
- **Python Support:** `>=3.11` (CI tested on 3.11, 3.12, 3.13)
- **Dependencies:** `cryptography>=42`, `httpx>=0.27`
- **Test Suite:** 28 passing unit tests in `pytest`
- **Linter Status:** `ruff check .` clean

## Existing CLI Commands in v0.1.0

1. `install-handler` - Register desktop redirect URI handler for `ms-app://`
2. `auth-start` - Begin Samsung Account interactive OAuth flow
3. `auth-complete` - Exchange redirect callback for master and scoped credentials
4. `status` - Report local authentication state
5. `verify` - Check the live SmartThings/Find session
6. `devices` - List devices registered with Samsung Find
7. `capabilities` - List exposed features for a specific device
8. `check` - Test device connectivity and report battery information when available
9. `ring` - Start or stop device ringing
10. `track` - Start or stop continuous tracking
11. `locate` - Read the last reported location or request an active update

## State Storage in v0.1.0

- State path: `~/.config/samsung-find/state.json` (mode `0600`)
- Mixed content: master token (`userauth_token`), scoped tokens (`offline.access`, `iot.client`), device physical ID, web bridge session (`JSESSIONID`, `_csrf`).
- File locking: `fcntl.flock` (Linux/macOS only).

## Public Surfaces & Identified Gaps

- Public import `src/samsung_find/__init__.py` did not export typed facades (`SamsungFindClient`).
- CLI outputs were plain raw JSON dictionaries without versioned envelope wrappers or machine schemas.
- No MCP server implementation.
- Generic dispatcher in `api.py` allowed arbitrary URI/payload dispatch.
- Authentication host and redirect targets lacked strict allowlist validation before bearer attachment.
- Automatic retry on `401/403` applied indiscriminately to non-idempotent actions.

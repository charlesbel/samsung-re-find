---
name: samsung-account-auth
description: "Authenticate and manage shared Samsung Account master state."
version: 0.2.0
author: Charles Bel, Hermes Agent
license: MIT
platforms: [linux, darwin, windows]
metadata:
  hermes:
    tags: [samsung, authentication, oauth, master-state, smart-home]
---

# Samsung Account Shared Authentication

Use this skill to bootstrap, migrate, or repair the shared Samsung Account master authentication state (`master-state-v1`) used by Samsung Find and Samsung Health Cloud.

## When to Use

- First-time setup on a new system.
- Migrating legacy v0.1 `~/.config/samsung-find/state.json` to neutral `master-state-v1`.
- Repairing revoked or expired credentials.
- Checking master authentication status across ecosystem tools.

## Prerequisites

- Access to a web browser on desktop or local machine to complete human Samsung login.
- `samsung-find` CLI installed.
- Never output or paste passwords, master tokens, or private state files into chat or logs.

## How to Run

### Initial Interactive Setup

```bash
# 1. Register desktop redirect URI handler
samsung-find install-handler

# 2. Generate secure login URL
samsung-find auth-start --country us --locale en-US

# 3. Open URL in browser, complete login, then:
samsung-find auth-complete

# 4. Verify status
samsung-find status
samsung-find verify
```

### Migration from Legacy v0.1

```bash
# Migrate without re-entering credentials
samsung-find migrate-master
```

## Quick Reference

| Task | Command | Purpose |
|---|---|---|
| Register handler | `samsung-find install-handler` | Desktop `ms-app://` handler |
| Start login | `samsung-find auth-start` | Initiates PKCE OAuth flow |
| Complete login | `samsung-find auth-complete` | Exchanges callback for master state |
| Migrate legacy | `samsung-find migrate-master` | Converts legacy state to neutral v1 |
| Check status | `samsung-find status` | Shows local token readiness |
| Verify session | `samsung-find verify` | Tests live SmartThings/Find API connectivity |

## Procedure

1. **Check Status First:** Run `samsung-find status`. If authenticated, re-login is not needed.
2. **If Legacy State Exists:** Run `samsung-find migrate-master` to create `master-state-v1` non-destructively.
3. **Interactive Login:** If unauthenticated, run `auth-start`, guide the user to sign in via their browser, and run `auth-complete`.
4. **Verification:** Run `samsung-find verify` to test full connectivity.

## Pitfalls

- **No Chat Credentials:** Never ask users to paste passwords, 2FA codes, or tokens in conversation.
- **Do Not Delete Legacy:** Migration leaves legacy state intact for safety and rollback.
- **Single Master State:** `samsung-find` and `samsung-health-cloud` both consume `samsung-account/master.json`. Logging in once powers both tools.

## Verification

Run `samsung-find verify`. A valid response reports `persistent_master_token_present: true` and `web_session_valid: true`.

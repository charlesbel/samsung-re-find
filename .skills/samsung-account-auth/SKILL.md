---
name: samsung-account-auth
description: Manage shared Samsung Account authentication safely.
version: 0.2.0
author: Charles Bel, Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [samsung, authentication, oauth, master-state, smart-home]
---

# Samsung Account Shared Authentication

> **Disclaimer:** Unofficial reverse-engineered authentication tools. Not affiliated with, endorsed by, or supported by Samsung Electronics.

Use this skill to bootstrap, migrate, or repair the shared Samsung Account master authentication state (`master-state-v1`) used by Samsung Find (`samsung-re-find`) and Samsung Health Cloud (`samsung-re-health`).

## When to Use

- First-time setup on a new system.
- Migrating legacy v0.1 `~/.config/samsung-find/state.json` to neutral `master-state-v1`.
- Repairing revoked or expired credentials.
- Checking master authentication status across ecosystem tools.

## Prerequisites

- Access to a web browser on desktop or local machine to complete human Samsung login.
- `samsung-re-find` CLI installed (legacy alias `samsung-find` also supported).
- Never output or paste passwords, master tokens, or private state files into chat or logs.

## How to Run

### Initial Interactive Setup

```bash
# 1. Register desktop redirect URI handler
samsung-re-find install-handler

# 2. Generate secure login URL
samsung-re-find auth-start --country us --locale en-US

# 3. Open URL in browser, complete login, then:
samsung-re-find auth-complete

# 4. Verify status
samsung-re-find status
samsung-re-find verify
```

### Migration from Legacy v0.1

```bash
# Migrate without re-entering credentials
samsung-re-find migrate-master
```

## Quick Reference

| Task | Canonical Command | Legacy Alias Command | Purpose |
|---|---|---|---|
| Register handler | `samsung-re-find install-handler` | `samsung-find install-handler` | Desktop `ms-app://` handler |
| Start login | `samsung-re-find auth-start` | `samsung-find auth-start` | Initiates PKCE OAuth flow |
| Complete login | `samsung-re-find auth-complete` | `samsung-find auth-complete` | Exchanges callback for master state |
| Migrate legacy | `samsung-re-find migrate-master` | `samsung-find migrate-master` | Converts legacy state to neutral v1 |
| Check status | `samsung-re-find status` | `samsung-find status` | Shows local token readiness |
| Verify session | `samsung-re-find verify` | `samsung-find verify` | Tests live SmartThings/Find API connectivity |

## Procedure

1. **Check Status First:** Run `samsung-re-find status`. If authenticated, re-login is not needed.
2. **If Legacy State Exists:** Run `samsung-re-find migrate-master` to create `master-state-v1` non-destructively.
3. **Interactive Login:** If unauthenticated, run `auth-start`, guide the user to sign in via their browser, and run `auth-complete`.
4. **Verification:** Run `samsung-re-find verify` to test full connectivity.

## Pitfalls

- **No Chat Credentials:** Never ask users to paste passwords, 2FA codes, or tokens in conversation.
- **Do Not Delete Legacy:** Migration leaves legacy state intact for safety and rollback.
- **Single Master State:** `samsung-re-find` and `samsung-re-health` both consume `samsung-account/master.json`. Logging in once powers both tools.

## Verification

Run `samsung-re-find verify`. A valid response reports `persistent_master_token_present: true` and `web_session_valid: true`.

---
name: samsung-find-auth
description: "Set up or repair persistent Samsung Find authentication."
version: 0.1.0
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [samsung, authentication, oauth, smartthings-find]
---

# Samsung Find persistent authentication

Use this skill only for initial setup, revoked credentials, or repair of the persistent Samsung Find session.

## Security rules

- Authentication requires a human-controlled Samsung Account browser session.
- Never ask the user to paste a password, one-time code, master token, OAuth callback, cookie, or state file into chat.
- Never display or inspect `~/.config/samsung-find/state.json`.
- The login URL and complete `ms-app://` callback are sensitive transient values. Do not log or publish them.
- Do not copy authentication state between machines.

## Linux desktop setup

Install the private callback handler once:

```bash
samsung-find install-handler
```

Start authentication with the user's locale:

```bash
samsung-find auth-start --country us --locale en-US
```

Open the returned URL in a trusted browser and let the user complete Samsung Account authentication. After the browser invokes the private callback handler, complete the exchange:

```bash
samsung-find auth-complete
samsung-find status
samsung-find verify
```

A healthy final state has a persistent master token and a valid regenerated web session.

## Manual callback fallback

If the OS cannot open the `ms-app://` callback, the user may capture the complete URI from browser developer tools and store it directly in `~/.config/samsung-find/redirect.uri` with mode `0600`. Then run `samsung-find auth-complete` immediately. Do not paste the URI into a conversation or shell history.

## Normal expiration

Do not repeat interactive login for ordinary access-token, refresh-token, or web-cookie expiration. The client rotates scoped refresh tokens and reissues them from the master token; it also regenerates the web session from the same master token. Current web-session recovery first obtains an opaque server state and bootstrap cookie from `getState.do`, then reuses both through `login.do`; never substitute a caller-generated random state.

## Interactive login is required again when

- the Samsung Account was explicitly logged out;
- Samsung revoked the master token;
- account-security settings invalidated the session;
- the local state was deleted or corrupted;
- Samsung changed the unofficial protocol.

If `verify` fails but `status` reports an authenticated master state, retry once. If it still fails, explain that the unofficial backend may have changed before starting a new login.

# Persistent authentication design

This document describes the authentication architecture implemented by `samsung-find-agent`. The APIs are unofficial and can change without notice.

## Why a browser cookie is not enough

Earlier SmartThings Find integrations commonly ask users to copy `JSESSIONID` and `WMONID` from a browser. That can enable the legacy web API, but it leaves the integration unable to recover when the session expires.[3][4][6]

Samsung's application authentication flow provides a stronger root of trust: a `userauth_token` associated with the Samsung Account. uTag documents that the same master token can authorize both Samsung Find and SmartThings scopes and can issue new scoped tokens after the ordinary refresh-token window ends.[1]

This client therefore uses a four-layer chain:

1. Samsung Account interactive sign-in creates a master `userauth_token`.
2. The master token issues scoped access and rotating refresh tokens.
3. Refresh tokens rotate during normal operation.
4. If a scoped refresh token is no longer usable, the master token issues a new scoped pair; if the legacy web cookie expires, the same master token creates a new web session.

This is persistent authentication, not permanent authorization. Samsung can revoke the master token, change the protocol, or require a new interactive sign-in.

## Initial sign-in

The initial flow starts at:

```text
GET https://account.samsung.com/accounts/ANDROIDSDK/getEntryPoint
```

The response provides a sign-in URL, an RSA public key, and `chkDoNum`. The client builds an application SVC payload containing PKCE state, a persistent random physical device identifier, locale information, and the application redirect URI. It encrypts the payload with the sequence documented by uTag: PBKDF2-HMAC-SHA256 for a generated AES key, RSA PKCS#1 v1.5 for wrapping that key, and AES-CBC for the SVC JSON.[1]

The callback-derived authentication server is accepted only over HTTPS on Samsung-controlled `samsungosp.com` or `account.samsung.com` hosts. Pending authentication state expires after 15 minutes and expired files are removed before callback processing.

After the browser login, Samsung redirects to an `ms-app://` URI. The callback fields are encrypted. The client decrypts the response, exchanges its authorization code, and stores:

- the master `userauth_token`;
- the Samsung user identifier and auth server URL;
- the persistent random physical device identifier;
- the login identifier needed for later authorizations;
- scoped Find and SmartThings token pairs.

The password and second factor are handled by Samsung's page and are never stored by this project.

## Scoped tokens

The client currently uses:

| Purpose | Scope |
| --- | --- |
| Samsung Find API | `offline.access` |
| SmartThings installed-app execution | `iot.client` |

Each scoped authorization uses PKCE. Refresh tokens rotate and are single-use: a successful refresh response replaces both the access token and the refresh token.[1] The state update therefore runs under an exclusive file lock and is committed atomically.

A `401` or `403` causes one forced refresh and one retry. If refresh fails, the client authorizes a new scoped pair with the master token.

## Legacy SmartThings Find web bridge

Phones and several remote operations remain available through `smartthingsfind.samsung.com`. The project found that the master token can authorize the web Find client, after which the returned short-lived code can be exchanged through `login.do` for a `JSESSIONID`.

The current frontend requires a server-side login bootstrap before that exchange. The client first calls `getState.do?payload=hound`, retains the bootstrap `JSESSIONID` in the same HTTP cookie jar, and passes the returned opaque `state` unchanged to `login.do`. A caller-generated random state can still yield a replacement cookie, but `chkLogin.do` rejects it with `fail` and `init.do` treats it as logged out. The bootstrap state is transient and is never persisted.

The web bridge is intentionally authorized without PKCE. In live testing, including a PKCE challenge produced a cookie that existed but failed `chkLogin.do`; omitting PKCE produced an authenticated session with a valid `_csrf` response header.

The client validates every cached web cookie before use. An invalid cookie is discarded and rebuilt from the master token, the server-issued login state, and the bootstrap cookie without asking for the account password again.

## Local state and concurrency

Default files:

```text
~/.config/samsung-find/state.json
~/.config/samsung-find/state.json.lock
~/.config/samsung-find/pending.json
~/.config/samsung-find/redirect.uri
```

Security properties:

- state, pending data, callbacks, and lock files use mode `0600`;
- parent directories use mode `0700`;
- writes use a temporary file, `fsync`, and `os.replace`;
- refresh and reissue operations are serialized with `fcntl.flock`;
- the callback file is consumed and deleted;
- normal errors never include Samsung response bodies.

Do not copy `state.json` between machines or commit it to source control.

## Bootstrap sequence

```bash
samsung-find install-handler
samsung-find auth-start --country us --locale en-US
```

Open the returned login URL in a desktop browser. Complete Samsung Account authentication. The installed private URI handler stores the callback in the private redirect file. Then run:

```bash
samsung-find auth-complete
samsung-find status
samsung-find verify
```

If the desktop cannot register `ms-app://`, capture the complete redirect URI from browser developer tools and write it directly to the configured callback file with mode `0600`, then run `auth-complete`. Never paste that URI into an issue, chat transcript, or shell history.

## Failure modes

A new interactive sign-in can still be required after:

- explicit Samsung Account logout;
- account-security changes or server-side revocation;
- a protocol or client-policy change;
- deletion or corruption of the local master state;
- Samsung disabling the relevant service for the account or device.

## Sources

[1] https://github.com/KieronQuinn/uTag/wiki/Authentication
[3] https://gist.github.com/VityaSchel/fe8945c0189bbaabed420003bdf3216d
[4] https://github.com/VityaSchel/samsung-pinger
[6] https://git.jeena.net/jeena/HA-SmartThings-Find

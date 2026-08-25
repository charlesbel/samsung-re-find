# Security policy

## Supported versions

The project is experimental and currently supports only the latest release on the `main` branch.

## Reporting a vulnerability

Do not open a public issue containing Samsung Account credentials, OAuth codes, access tokens, refresh tokens, `userauth_token` values, cookies, device identifiers, or exact location data. Contact the repository owner privately through GitHub instead.

## Secret-handling guarantees

The client stores authentication state under `~/.config/samsung-find/` by default. State files are written atomically with mode `0600`; the parent directory and lock files are private. Normal errors intentionally omit response bodies because Samsung responses can contain credentials.

The repository contains Samsung application client identifiers observed in official clients and prior reverse-engineering work. These identifiers are not user credentials. No account-specific secret is required in source code.

## Agent safety boundary

The CLI exposes non-destructive operations only. A strict internal allowlist rejects all other operation names. The operation helper accepts no generic caller payload; only typed ring fields may be added to `RING`, and exact native string types are required before comparisons. All checks run before any web request is made. Audible ringing and continuous tracking require an explicit `--yes` flag. Locking, wiping, payment locking, and lost-mode operations are intentionally not implemented.

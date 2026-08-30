# Security Policy

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

## Supported Versions

| Version | Supported |
|---|---|
| 0.2.x | Yes (Current release candidate `samsung-re-find`) |
| 0.1.x | Deprecated (Migrate with `samsung-re-find migrate-master`) |

## Reporting a Vulnerability

Please do not disclose security vulnerabilities in public GitHub issues. If you discover a security vulnerability or sensitive token leakage risk, please contact the repository maintainers privately via GitHub Security Advisories or private messaging.

## Secret Handling & Privacy Guarantees

1. **State Storage:** Shared master credentials are stored in `samsung-account/master.json` with file permissions `0600` (`-rw-------`) inside a private `0700` parent directory. Symlinks and non-owned paths are strictly rejected.
2. **Redaction:** In-memory dataclasses (`MasterState`, `Device`, `LocationResult`) implement string redaction on `__repr__` and `__str__`. Tokens and credentials are never emitted in logs, exception traces, or error messages.
3. **Transport Destination Allowlist:** Outgoing HTTP requests with bearer authorization tokens strictly validate target scheme (`https`), trusted Samsung/SmartThings hostnames, and standard ports (`443`) before attaching headers. Inter-host pagination redirects are explicitly blocked.
4. **No Destructive Operations:** The codebase does not implement or allow remote wiping, locking, SIM lock, or payment lock features.
5. **No Live Credentials in Repository:** Test fixtures use purely synthetic, mocked structures. Never commit real tokens or credentials.

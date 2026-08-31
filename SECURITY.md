# Security Policy

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

## Supported Versions

| Version | Supported |
|---|---|
| 0.2.x | Yes (current Beta release) |
| 0.1.x | Deprecated (Migrate with `samsung-re-find migrate-master`) |

## Reporting a Vulnerability

Please do not disclose security vulnerabilities in public GitHub issues. Use GitHub Private Vulnerability Reporting through the repository's **Security → Report a vulnerability** flow. If that flow is unavailable, open a non-sensitive issue asking the maintainer to provide a private reporting channel; do not include reproduction secrets or location data.

## Secret Handling & Privacy Guarantees

1. **State Storage:** Shared master credentials are stored in `samsung-account/master.json`. POSIX files/directories use modes `0600`/`0700`; readers reject unsafe symlinks and unexpected ownership where the platform exposes those checks. State is not encrypted at rest.
2. **Redaction:** Project-owned dataclass representations, CLI status output and normal project exceptions redact known tokens and credentials. Raw state, process memory, debuggers, third-party tracing and caller-defined SDK logging are outside this guarantee.
3. **Transport Destination Allowlist:** Outgoing HTTP requests with bearer authorization tokens strictly validate target scheme (`https`), trusted Samsung/SmartThings hostnames, and standard ports (`443`) before attaching headers. Inter-host pagination redirects are explicitly blocked.
4. **No Destructive Operations:** The codebase does not implement or allow remote wiping, locking, SIM lock, or payment lock features.
5. **No Live Credentials in Repository:** Test fixtures use purely synthetic, mocked structures. Never commit real tokens or credentials.

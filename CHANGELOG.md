# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-08-31

### Changed
- Reworked the README to explain the project's headless automation purpose, its relationship to the official Samsung experience and public SmartThings API, and its differences from uTag, Samsung Pinger, and Home Assistant integrations.
- Made bundled-skill installation instructions harness-neutral by requiring the agent runtime's configured skills directory instead of a framework-specific path.
- Clarified passive reads, active device contact, audible effects, persistent tracking, retry behavior, location freshness, and the distinction between backend payloads and public models.
- Corrected the shared master-state contract: either Samsung RE project may create or replace the neutral master during an explicit interactive bootstrap, while ordinary service operations consume it without implicit replacement.

### Fixed
- Corrected historical CLI commands and exit-code documentation in the 0.1 baseline and agent guide.
- Scoped privacy, network, and security claims to the interfaces and controls that actually implement them.
- Added documentation contracts for product positioning and portable agent-skill installation.

## [0.2.0] - 2026-08-30

### Added
- **Typed Python SDK Facade:** Added `from samsung_find import SamsungFindClient, FindConfig` with typed models (`Device`, `DeviceCapabilities`, `LocationResult`, `OperationResult`).
- **Shared Master State Contract (v1):** Introduced neutral `master-state-v1` schema (`schemas/master-state-v1.schema.json`) stored at `samsung-account/master.json` for seamless shared authentication with `samsung-re-health`.
- **Non-Destructive State Migration:** Added `samsung-re-find migrate-master` (and alias `samsung-find migrate-master`) to upgrade v0.1 state files to `master-state-v1` without re-login.
- **Model Context Protocol (MCP) Server:** Added `samsung-re-find-mcp` (and alias `samsung-find-mcp`) stdio server exposing typed tools for AI agents, with physical side effects gated behind `--allow-effects`.
- **Contractual Versioned JSON Envelopes:** CLI machine outputs now conform to `schemas/cli/v1/` with standardized response envelopes (`ok`, `schema_version: "1.0"`, `data`, `error`).
- **Standardized Exit Codes:** Standardized CLI return codes (`0` success, `2` argument validation, `3` auth error, `4` network error, `5` storage/permission error).
- **Portable Skills:** Moved and standardized skills under `.skills/samsung-re-find/` and `.skills/samsung-account-auth/`.
- **Package Typing:** Added `py.typed` PEP 561 marker.

### Changed
- **Renamed Distribution to `samsung-re-find`:** Package graduated and renamed to `samsung-re-find` on PyPI and GitHub (`charlesbel/samsung-re-find`). Standard tagline: *"Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server"*.
- **Canonical Entry Points:** Established canonical CLI `samsung-re-find` and MCP `samsung-re-find-mcp`, retaining legacy aliases `samsung-find` and `samsung-find-mcp` with documented deprecation/compatibility.
- **Stable Import:** Python import preserved as `samsung_find`.
- **Hardened Transport:** Enforced HTTPS and Samsung/SmartThings domain allowlist before attaching Bearer tokens; blocked hostile inter-host pagination.
- **Removed Generic Dispatcher:** Removed generic execution overrides and protected field tampering (`requester`, `requesterToken`, `method`, `uri`).
- **Disallowed Automatic Retries on Actions:** Disabled blind auto-retry on 401/403 for non-idempotent mutation actions.

### Fixed
- Fixed permission hardening and symlink vulnerabilities in state storage.
- Fixed cross-platform locking support.

## [0.1.0] - 2026-08-28

### Added
- Initial public release of `samsung-find-agent`.
- Persistent Samsung Account OAuth authentication with master token and token rotation.
- Web bridge session bootstrap via `getState.do` and `login.do`.
- CLI commands for devices, capabilities, location, ring, track, and check.

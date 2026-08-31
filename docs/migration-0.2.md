# Migration Guide: Samsung Find 0.1 to 0.2

This document details the migration path from `samsung-find-agent` v0.1.0 to `samsung-re-find` v0.2.0.

## Overview of Changes

1. **Package Identity & Universal Naming:**
   - Distribution renamed: `samsung-find-agent` -> `samsung-re-find` (PyPI package `samsung-re-find`).
   - Python import remains: `samsung_find`.
   - Canonical CLI command: `samsung-re-find` (legacy compatibility alias `samsung-find` retained).
   - Canonical MCP command: `samsung-re-find-mcp` (legacy compatibility alias `samsung-find-mcp` retained).

2. **State Boundary Separation & Master Contract (v1):**
   - In v0.1.0, master credentials and service-specific session cookies were stored together in legacy `~/.config/samsung-find/state.json`.
   - In v0.2.0, the neutral Samsung master identity is stored in `~/.config/samsung-account/master.json` (`master-state-v1` contract), enabling shared authentication with companion projects like `samsung-re-health` without re-login.
   - Canonical Find derived tokens and web cookies are stored cleanly in `~/.local/state/samsung-find/state.json` (`platformdirs.user_state_dir("samsung-find")/state.json`), completely free of master identity credentials.

3. **Non-Destructive Local Migration:**
   - Run the migration command:
     ```bash
     samsung-re-find migrate-master
     ```
     *(or legacy alias: `samsung-find migrate-master`)*
   - This reads your existing legacy `state.json`, constructs the versioned `master-state-v1` file and clean derived state, and saves them atomically with mode `0600`.
   - Your existing legacy `state.json` file is left byte-for-byte intact.
   - The migration command itself is local and does not request an interactive login. A later login can still be required if the migrated Samsung authorization has expired or been revoked.

4. **SDK Modernization:**
   - Direct typed facade available via `from samsung_find import SamsungFindClient, FindConfig`.
   - Full model dataclasses in `samsung_find.models`.

5. **MCP Server:**
   - Stdio MCP server available via `samsung-re-find-mcp` (with `pip install 'samsung-re-find[mcp]'`).
   - Ring and tracking tools are disabled by default and gated behind explicit `--allow-effects`. Active location and connection checks remain available by default and can contact or wake a device.

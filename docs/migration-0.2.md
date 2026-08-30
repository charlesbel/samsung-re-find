# Migration Guide: Samsung Find 0.1 to 0.2

This document details the migration path from `samsung-find-agent` v0.1.0 to `samsung-find` v0.2.0.

## Overview of Changes

1. **Package Identity:**
   - Distribution renamed: `samsung-find-agent` -> `samsung-find`.
   - Python import remains: `samsung_find`.
   - CLI command remains: `samsung-find`.

2. **Shared Master Authentication Contract (v1):**
   - In v0.1.0, master credentials and service-specific session cookies were stored together in `~/.config/samsung-find/state.json`.
   - In v0.2.0, the neutral Samsung master token is stored in `~/.config/samsung-account/master.json` (`master-state-v1` contract), enabling shared authentication with companion projects like `samsung-health-cloud` without re-login.
   - Derived tokens and web cookies remain isolated in `~/.config/samsung-find/state.json`.

3. **Non-Destructive Local Migration:**
   - Run the migration command:
     ```bash
     samsung-find migrate-master
     ```
   - This reads your existing `state.json`, constructs the versioned `master-state-v1` file, and saves it atomically with mode `0600`.
   - Your existing `state.json` file is left completely intact.
   - No interactive re-login or credentials entry is required.

4. **SDK Modernization:**
   - Direct typed facade available via `from samsung_find import SamsungFindClient, FindConfig`.
   - Full model dataclasses in `samsung_find.models`.

5. **MCP Server:**
   - Stdio MCP server available via `samsung-find-mcp` (with `pip install 'samsung-find[mcp]'`).
   - Read-only tools enabled by default; side-effect tools (`ring`, `track`) gated behind explicit `--allow-effects`.

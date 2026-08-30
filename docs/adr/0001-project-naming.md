# ADR 0001: Ecosystem Project Naming and Boundaries

## Status
Accepted

## Context
The Samsung reverse-engineering tools started as `samsung-find-agent` and a research client for Samsung Health (`samsung-health-cloud`). To graduate these projects into coherent, safe, public ecosystems for multiple consumers (Python SDK, JSON CLI, and MCP servers for AI agents), universal canonical names, distribution identities, disclaimer standards, and package boundaries must be established.

## Decision

### Universal Convention for `samsung-re-{domain}` Tools

All reverse-engineered Samsung service tools in this ecosystem follow the universal `samsung-re-{domain}` convention:

1. **Distribution & Repository:** `samsung-re-{domain}` (e.g. `charlesbel/samsung-re-find`, `charlesbel/samsung-re-health`).
2. **Canonical CLI:** `samsung-re-{domain}` (e.g. `samsung-re-find`, `samsung-re-health`).
3. **Canonical MCP:** `samsung-re-{domain}-mcp` (e.g. `samsung-re-find-mcp`, `samsung-re-health-mcp`).
4. **Standard Tagline:** `"Unofficial reverse-engineered Samsung {Domain} SDK, JSON CLI & MCP server"`.
5. **Prominent Disclaimer:** Unofficial / non-affiliation disclaimers must be prominently displayed across all READMEs, documentation, CLI `--help`, MCP servers, and skills.
6. **Shared Master State v1:** All tools consume the neutral `master-state-v1` contract (`io.github.charlesbel.samsung-account.master`) stored at `samsung-account/master.json`.
7. **Compatibility Aliases:** Legacy aliases (such as `samsung-find`, `samsung-find-mcp`, `samsung-health`, `samsung-health-cloud`) are retained for at least one minor release cycle with clear deprecation warnings.

### Canonical Naming Matrix

| Surface | Samsung Find | Samsung Health (Companion) |
|---|---|---|
| GitHub Repository | `charlesbel/samsung-re-find` | `charlesbel/samsung-re-health` |
| Local Directory | `projects/samsung-re-find` | `projects/samsung-re-health` |
| Python Distribution | `samsung-re-find` | `samsung-re-health` |
| Python Import | `samsung_find` | `samsung_health_cloud` |
| CLI Executable | `samsung-re-find` | `samsung-re-health` |
| CLI Transitional Alias | `samsung-find` (deprecated, 1 cycle) | `samsung-health`, `samsung-health-cloud` (deprecated, 1 cycle) |
| MCP Executable | `samsung-re-find-mcp` | `samsung-re-health-mcp` |
| MCP Server Name | `samsung-re-find` | `samsung-re-health` |
| MCP Tool Prefix | `samsung_find_*` | `samsung_health_*` |
| Public Skill Path | `.skills/samsung-re-find/SKILL.md` | `.skills/samsung-re-health/SKILL.md` |

### Key Rationale
1. **Explicit Reverse-Engineering Indicator (`re-`):** Clearly signals unofficial, reverse-engineered nature directly in the package name and CLI, avoiding trademark ambiguity or mistaken official affiliation.
2. **Standardized Ecosystem Pattern:** Every new Samsung reverse-engineered service automatically adopts `samsung-re-{domain}` without ad-hoc naming decisions.
3. **Preserve stable Python imports:** `samsung_find` and `samsung_health_cloud` are already clear, unambiguous, and widely tested.
4. **No immediate 3rd Auth repo:** To avoid unnecessary multi-repo coordination and release overhead with only two services, the shared master authentication state is defined as a neutral versioned contract (`master-state-v1`), with Find acting as the primary interactive writer and Health as a strict read-only consumer.

### Alternatives Considered and Rejected
- **Keeping `samsung-find-agent`:** Rejected because it implies limitation to agent workflows and does not reflect SDK/CLI use cases.
- **Bare `samsung-find` / `samsung-health`:** Rejected in favor of `samsung-re-{domain}` to make unofficial, reverse-engineered status unambiguous on PyPI and GitHub.
- **Separate `samsung-account-auth` package:** Deferred until a 3rd Samsung consumer emerges or contract drift occurs.

### Compatibility Windows
- Transitional CLI aliases (`samsung-find`, `samsung-find-mcp`, `samsung-health`, `samsung-health-cloud`) retained for at least one minor release cycle (0.2.x -> 0.3.x / 1.0.x).
- Legacy JSON envelope options (`--legacy-json`) provided during Find 0.2.x transition.
- Legacy state file path fallback (`~/.config/samsung-find/state.json`) supported with clean warning before deprecation.

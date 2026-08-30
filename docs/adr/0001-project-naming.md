# ADR 0001: Ecosystem Project Naming and Boundaries

## Status
Accepted

## Context
The Samsung reverse-engineering tools started as `samsung-find-agent` and a research client for Samsung Health. To graduate these projects into coherent, safe, public ecosystems for multiple consumers (Python SDK, JSON CLI, and MCP servers for AI agents), canonical names, distribution identities, and package boundaries must be established.

## Decision

### Canonical Naming Matrix

| Surface | Samsung Find | Samsung Health Cloud (Companion) |
|---|---|---|
| GitHub Repository | `charlesbel/samsung-find` | `charlesbel/samsung-health-cloud` |
| Local Directory | `projects/samsung-find` | `projects/samsung-health-cloud` |
| Python Distribution | `samsung-find` | `samsung-health-cloud` |
| Python Import | `samsung_find` | `samsung_health_cloud` |
| CLI Executable | `samsung-find` | `samsung-health` |
| CLI Transitional Alias | *None needed* | `samsung-health-cloud` (deprecated, 1 cycle) |
| MCP Executable | `samsung-find-mcp` | `samsung-health-mcp` |
| MCP Server Name | `samsung-find` | `samsung-health` |
| MCP Tool Prefix | `samsung_find_*` | `samsung_health_*` |
| Public Skill Path | `.skills/samsung-find/SKILL.md` | `.skills/samsung-health-cloud/SKILL.md` |

### Key Rationale
1. **Drop `-agent` suffix from Find:** The project is a general-purpose Python SDK and robust CLI, not solely an AI agent plugin.
2. **Keep `-cloud` suffix for Health:** Distinguishes the cloud reverse-engineering client from Samsung's Android SDK, Health Connect, or static file export parsers.
3. **Preserve stable Python imports:** `samsung_find` and `samsung_health_cloud` are already clear, unambiguous, and widely tested.
4. **No immediate 3rd Auth repo:** To avoid unnecessary multi-repo coordination and release overhead with only two services, the shared master authentication state is defined as a neutral versioned contract (`master-state-v1`), with Find acting as the primary interactive writer and Health as a strict read-only consumer.

### Alternatives Considered and Rejected
- **Keeping `samsung-find-agent`:** Rejected because it implies limitation to agent workflows and does not reflect SDK/CLI use cases.
- **Symmetric `samsung-find-cloud` or `samsung-health`:** Rejected because `samsung-find` already conveys cloud service cleanly, while `samsung-health` without `-cloud` is ambiguous relative to local Health Connect / export tools.
- **Separate `samsung-account-auth` package:** Deferred until a 3rd Samsung consumer emerges or contract drift occurs.

### Compatibility Windows
- Transitional CLI alias for Health retained for at least one minor release cycle (0.7.x -> 1.0.x).
- Legacy JSON envelope options (`--legacy-json`) provided during Find 0.2.x transition.
- Legacy state file path fallback (`~/.config/samsung-find/state.json`) supported with clean warning before deprecation.

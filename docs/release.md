# Release Process and Verification Gates

This document describes the release process for `samsung-re-find`.

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

## Release Boundary

- Distribution: `samsung-re-find`
- Python import: `samsung_find`
- Canonical executables: `samsung-re-find`, `samsung-re-find-mcp`
- Trigger: a pushed tag exactly matching `v{project.version}`
- Publisher: GitHub Actions OIDC through PyPI Trusted Publishing
- GitHub environment: `pypi`

No password or long-lived PyPI API token is stored in the repository or workflow.

## Required Local Gates

Run after the final source or documentation edit:

```bash
uv run pytest -q
uv run python -O -m pytest -q
uv run ruff check .
uv run ruff format --check .
git diff --check
uv build
uvx twine check --strict dist/*
uvx pip-audit --strict
```

Also run `actionlint`, Gitleaks with redaction against the working tree and complete Git history, inspect archive contents, and install the built wheel with its `mcp` extra into an empty Python 3.11 environment. `scripts/smoke_built_wheel.py` must negotiate MCP stdio sequentially and verify both canonical and compatibility entry points.

## Automated Release Flow

`.github/workflows/release.yml` runs only for pushed `v*` tags:

1. **`verify-and-build`** checks tag/version equality, installs release dependencies, runs Ruff, both test modes, `pip-audit`, full-history Gitleaks, builds wheel/sdist, runs strict Twine checks, inspects archives, and smoke-tests the installed wheel and MCP server.
2. **`publish-pypi`** runs only after verification. It downloads the exact verified artifacts and publishes them to PyPI using Trusted Publishing in the `pypi` environment.
3. **`github-release`** runs only after PyPI succeeds. It creates the final GitHub Release and attaches the same wheel and sdist.

This ordering prevents a GitHub Release from claiming success when PyPI publication failed.

## Trusted Publisher Configuration

For a first publication, the PyPI account owner must configure a pending publisher with:

- PyPI project: `samsung-re-find`
- GitHub owner: `charlesbel`
- Repository: `samsung-re-find`
- Workflow: `release.yml`
- Environment: `pypi`

The GitHub repository must also contain an environment named `pypi`. Optional environment reviewers are configured in GitHub settings, not in the workflow file.

## Publishing

After the release commit is on `main`, all CI checks are green, and the pending publisher is configured:

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

Do not upload the same artifacts manually while the workflow is running. PyPI distributions are immutable; if publication partially succeeds, inspect PyPI and the workflow before retrying. Never delete and recreate a tag that has already produced public artifacts.

## Post-Release Verification

Verify independently:

1. the PyPI JSON endpoint reports version `0.2.0` and both artifacts;
2. a fresh environment can install `samsung-re-find[mcp]==0.2.0` from PyPI;
3. canonical CLI/MCP help and stdio negotiation work;
4. GitHub shows a non-draft `v0.2.0` release with matching assets;
5. repository links and README badges resolve to the renamed public repository.

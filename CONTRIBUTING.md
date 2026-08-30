# Contributing to Samsung Find

> **Disclaimer:** Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server. Not affiliated with, endorsed by, or supported by Samsung Electronics or SmartThings.

Thank you for contributing to `samsung-re-find`!

## Local Development Workflow

```bash
# Create local virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install editable with dev and mcp dependencies
pip install -e '.[dev,mcp]'

# Run linters and formatters
ruff check .
ruff format --check .

# Run test suite
pytest

# Build package
python -m build
twine check dist/*
```

## Security & Fixture Rules

1. **Synthetic Data Only:** Never commit real tokens, `userauth_token` values, session cookies, OAuth callbacks, physical MAC addresses, personal email addresses, or real GPS coordinates.
2. **Deterministic & Offline Tests:** All unit and contract tests must run completely offline without relying on real Samsung network services.
3. **Additional Operations:** Pull requests for newly understood operations are welcome when they use typed interfaces, explicit confirmation or opt-in controls appropriate to their effects, and focused offline tests. High-risk operations such as lock or wipe require a separate design and security review; never add a generic authenticated request dispatcher.
4. **Code Style:** All Python code must pass `ruff check .` and `ruff format --check .`.

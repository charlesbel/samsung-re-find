# Contributing

Contributions are welcome, especially protocol updates, device-type fixtures, documentation corrections, and tests that do not require a live Samsung account.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest
.venv/bin/python -m build
```

## Rules for fixtures and logs

- Never commit real tokens, cookies, OAuth redirects, account IDs, device IDs, device names, email addresses, coordinates, street addresses, or raw Samsung responses from a personal account.
- Reduce protocol fixtures to the smallest synthetic structure needed by a test.
- Keep destructive remote operations out of the generic execution surface.
- Mark live-tested behavior separately from inferred or untested behavior.

## Pull requests

Describe which device class and endpoint were tested, whether a live account was used, and what was anonymized. Include automated tests for new parsing, polling, authentication, or operation logic.

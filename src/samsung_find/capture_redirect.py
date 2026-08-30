"""Securely capture Samsung OAuth redirect URIs."""

from __future__ import annotations

import sys
import urllib.parse

from .constants import REDIRECT_URI
from .credentials import resolve_redirect_path
from .exceptions import SecurityError, StorageError
from .storage import atomic_write_text


def is_expected_redirect_uri(value: str) -> bool:
    """Match the configured OAuth callback's scheme, authority, and path exactly."""
    if not isinstance(value, str) or not value.startswith("ms-app://"):
        return False
    try:
        actual = urllib.parse.urlsplit(value)
        expected = urllib.parse.urlsplit(REDIRECT_URI)
    except (TypeError, ValueError):
        return False
    return (actual.scheme, actual.netloc, actual.path) == (expected.scheme, expected.netloc, expected.path)


def main(argv: list[str] | None = None) -> int:
    """Capture redirect URI and atomically write to secure location."""
    args = sys.argv if argv is None else argv
    if len(args) != 2 or not is_expected_redirect_uri(args[1]):
        return 2

    try:
        target = resolve_redirect_path()
        atomic_write_text(target, args[1], mode=0o600)
    except (SecurityError, StorageError, OSError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

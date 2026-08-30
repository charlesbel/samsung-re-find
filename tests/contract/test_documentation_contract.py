from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
PUBLIC_DOCS = (ROOT / "README.md").read_text(encoding="utf-8") + (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")


def test_public_documentation_covers_every_cli_command_and_sensitive_option() -> None:
    for command in (
        "install-handler",
        "auth-start",
        "auth-complete",
        "migrate-master",
        "status",
        "verify",
        "devices",
        "capabilities",
        "check",
        "ring",
        "track",
        "locate",
    ):
        assert command in PUBLIC_DOCS
    for option in (
        "--from-state",
        "--force",
        "--include-ids",
        "--passive",
        "--poll-seconds",
        "--message",
        "--status",
        "--yes",
    ):
        assert option in PUBLIC_DOCS


def test_readme_uses_current_identity_and_avoids_release_overclaims() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pip install samsung-re-find" in readme
    assert "import samsung_find" in readme
    assert "samsung-re-find-mcp" in readme
    assert ".skills/" in readme
    assert "production-ready" not in readme
    assert "official OAuth" not in readme
    assert "Battery: {status.battery}%" not in readme

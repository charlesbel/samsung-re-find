from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
FIND_SKILL = ROOT / ".skills" / "samsung-re-find" / "SKILL.md"
AUTH_SKILL = ROOT / ".skills" / "samsung-account-auth" / "SKILL.md"


def _frontmatter(content: str) -> dict[str, str]:
    assert content.startswith("---\n")
    raw = content.split("---\n", 2)[1]
    values: dict[str, str] = {}
    for line in raw.splitlines():
        if line and not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            values[key] = value.strip().strip('"')
    return values


def test_public_skills_are_portable_and_well_formed() -> None:
    for path, expected_name, expected_platforms in (
        (FIND_SKILL, "samsung-re-find", "[linux, macos, windows]"),
        (AUTH_SKILL, "samsung-account-auth", "[linux]"),
    ):
        content = path.read_text(encoding="utf-8")
        metadata = _frontmatter(content)
        assert metadata["name"] == expected_name
        assert metadata["description"].endswith(".")
        assert len(metadata["description"]) <= 60
        assert metadata["author"].startswith("Charles Bel")
        assert metadata["platforms"] == expected_platforms
        assert "/home/" not in content
        assert "Never" in content or "never" in content
        assert "## Pitfalls" in content
        assert "## Verification" in content


def test_find_skill_documents_real_public_surfaces() -> None:
    content = FIND_SKILL.read_text(encoding="utf-8")
    for command in (
        "status",
        "verify",
        "devices",
        "capabilities",
        "locate",
        "check",
        "ring",
        "track",
    ):
        assert f"`{command}" in content or f" {command}" in content
    for tool in (
        "samsung_find_status",
        "samsung_find_list_devices",
        "samsung_find_get_capabilities",
        "samsung_find_get_last_location",
        "samsung_find_request_location",
        "samsung_find_check_connection",
        "samsung_find_ring",
        "samsung_find_set_tracking",
    ):
        assert tool in content
    assert "--allow-effects" in content
    assert "--include-ids" in content
    assert "fresh position" in content
    assert "last known position" in content


def test_documented_help_surfaces_work_in_empty_home(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env["XDG_DATA_HOME"] = str(tmp_path / "data")

    probes = (
        [sys.executable, "-m", "samsung_find.cli", "--help"],
        [sys.executable, "-m", "samsung_find.cli", "locate", "--help"],
        [sys.executable, "-m", "samsung_find.cli", "ring", "--help"],
        [sys.executable, "-m", "samsung_find.mcp_server", "--help"],
    )
    for probe in probes:
        completed = subprocess.run(probe, env=env, text=True, capture_output=True, timeout=15, check=False)
        assert completed.returncode == 0, completed.stderr
        assert "Traceback" not in completed.stderr

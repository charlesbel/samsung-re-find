import stat
import sys

import pytest

from samsung_find.capture_redirect import main
from samsung_find.constants import REDIRECT_URI
from samsung_find.storage import secure_read_raw_text


def test_capture_redirect_requires_valid_arguments():
    # Bad argument count
    assert main(["capture_redirect"]) == 2
    assert main(["capture_redirect", "arg1", "arg2"]) == 2

    # Bad scheme
    assert main(["capture_redirect", "https://example.com"]) == 2
    assert main(["capture_redirect", "http://smartthingsfind.samsung.com"]) == 2


def test_capture_redirect_requires_exact_configured_callback_target(tmp_path, monkeypatch):
    target = tmp_path / "redirect.uri"
    monkeypatch.setenv("SAMSUNG_FIND_REDIRECT_PATH", str(target))

    for hostile in (
        "ms-app://callback?code=synthetic",
        f"{REDIRECT_URI}.evil?code=synthetic",
        f"{REDIRECT_URI}/other?code=synthetic",
        f"MS-APP://{REDIRECT_URI.removeprefix('ms-app://')}?code=synthetic",
    ):
        assert main(["capture_redirect", hostile]) == 2
        assert not target.exists()

    expected = f"{REDIRECT_URI}?code=synthetic&state=synthetic"
    assert main(["capture_redirect", expected]) == 0
    assert secure_read_raw_text(target) == expected


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes do not model Windows ACLs")
def test_capture_redirect_writes_uri_atomically_with_secure_permissions(tmp_path, monkeypatch):
    target = tmp_path / "redirect_dir" / "redirect.uri"
    monkeypatch.setenv("SAMSUNG_FIND_REDIRECT_PATH", str(target))

    uri = f"{REDIRECT_URI}?code=test-auth-code"
    exit_code = main(["capture_redirect", uri])
    assert exit_code == 0

    assert target.exists()
    assert secure_read_raw_text(target) == uri

    # Verify target mode is 0600
    file_mode = stat.S_IMODE(target.stat().st_mode)
    assert file_mode == 0o600

    # Verify parent directory mode is 0700
    dir_mode = stat.S_IMODE(target.parent.stat().st_mode)
    assert dir_mode == 0o700


def test_capture_redirect_rejects_symlink_parent_directory(tmp_path, monkeypatch):
    real_dir = tmp_path / "real_redirect"
    real_dir.mkdir(mode=0o700)
    symlink_dir = tmp_path / "symlink_redirect"
    symlink_dir.symlink_to(real_dir, target_is_directory=True)

    target = symlink_dir / "redirect.uri"
    monkeypatch.setenv("SAMSUNG_FIND_REDIRECT_PATH", str(target))

    uri = f"{REDIRECT_URI}?code=test-auth-code"
    exit_code = main(["capture_redirect", uri])
    assert exit_code != 0
    assert not (real_dir / "redirect.uri").exists()


def test_capture_redirect_rejects_symlink_target_file(tmp_path, monkeypatch):
    target_dir = tmp_path / "redirect_dir"
    target_dir.mkdir(mode=0o700)
    real_file = tmp_path / "real_file.txt"
    real_file.write_text("initial", encoding="utf-8")
    real_file.chmod(0o600)

    symlink_target = target_dir / "redirect.uri"
    symlink_target.symlink_to(real_file)

    monkeypatch.setenv("SAMSUNG_FIND_REDIRECT_PATH", str(symlink_target))

    uri = f"{REDIRECT_URI}?code=test-auth-code"
    exit_code = main(["capture_redirect", uri])
    assert exit_code != 0
    assert real_file.read_text(encoding="utf-8") == "initial"

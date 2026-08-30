import os
import stat

from samsung_find.storage import atomic_write_json, locked, read_json, secure_read_text


def test_locked_context(tmp_path):
    target = tmp_path / "data.json"
    with locked(target):
        atomic_write_json(target, {"hello": "world"})
    assert read_json(target) == {"hello": "world"}


def test_atomic_write_permissions(tmp_path):
    target = tmp_path / "subdir" / "state.json"
    atomic_write_json(target, {"key": "value"})
    assert target.exists()
    if hasattr(os, "chmod"):
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_secure_read_text_deletes_file(tmp_path):
    target = tmp_path / "secret.txt"
    target.write_text("my-secret-content", encoding="utf-8")
    val = secure_read_text(target)
    assert val == "my-secret-content"
    assert not target.exists()

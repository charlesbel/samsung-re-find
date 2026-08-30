import os

from samsung_find.storage import atomic_write_json, read_json, secure_read_text


def test_atomic_state_is_private(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"private_fixture": "value"})
    assert read_json(path) == {"private_fixture": "value"}
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_secure_redirect_is_consumed(tmp_path):
    path = tmp_path / "redirect.uri"
    path.write_text("ms-app://callback?code=synthetic-code", encoding="utf-8")
    path.chmod(0o600)
    assert secure_read_text(path).startswith("ms-app://")
    assert not path.exists()

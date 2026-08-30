import json

import pytest

from samsung_find.credentials import MasterStateStore
from samsung_find.exceptions import AuthError


def test_migrate_legacy_state_preserves_source_and_creates_master(tmp_path):
    legacy_file = tmp_path / "legacy" / "state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_content = json.dumps({
        "schema": 1,
        "device_id": "legacy_device_id_999",
        "auth_server_url": "https://auth.samsungosp.com",
        "login_id": "legacy_user@example.com",
        "user_id": "legacy_user_id_888",
        "userauth_token": "legacy_userauth_token_777",
        "find": {"access_token": "find_at", "refresh_token": "find_rt"},
        "iot": {"access_token": "iot_at", "refresh_token": "iot_rt"},
    }, indent=2)
    legacy_file.write_text(legacy_content, encoding="utf-8")
    legacy_file.chmod(0o600)

    target_master_file = tmp_path / "master" / "master.json"

    store = MasterStateStore(master_path=target_master_file, legacy_path=legacy_file)
    result = store.migrate_legacy()

    assert result["migrated"] is True
    assert result["source_kind"] == "legacy_samsung_find"
    assert result["target_kind"] == "master_state_v1"
    assert result["schema_version"] == 1

    # Source file MUST be byte-for-byte identical (not deleted, not modified)
    assert legacy_file.read_text(encoding="utf-8") == legacy_content

    # Target master file exists and is valid v1
    assert target_master_file.exists()
    loaded = store.load(allow_legacy_fallback=False)
    assert loaded is not None
    assert loaded.account.login_id == "legacy_user@example.com"
    assert loaded.account.user_id == "legacy_user_id_888"
    assert loaded.installation.physical_address == "legacy_device_id_999"
    assert loaded.identity.userauth_token == "legacy_userauth_token_777"
    assert loaded.identity.auth_server_url == "https://auth.samsungosp.com"


def test_migrate_already_migrated_is_idempotent(tmp_path):
    legacy_file = tmp_path / "legacy" / "state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text(json.dumps({
        "schema": 1,
        "device_id": "legacy_device_id_999",
        "auth_server_url": "https://auth.samsungosp.com",
        "login_id": "legacy_user@example.com",
        "user_id": "legacy_user_id_888",
        "userauth_token": "legacy_userauth_token_777",
    }), encoding="utf-8")
    legacy_file.chmod(0o600)

    target_master_file = tmp_path / "master" / "master.json"
    store = MasterStateStore(master_path=target_master_file, legacy_path=legacy_file)

    first = store.migrate_legacy()
    assert first["migrated"] is True

    second = store.migrate_legacy()
    assert second["migrated"] is False
    assert second["target_kind"] == "master_state_v1"


def test_migrate_fails_safely_if_legacy_missing_or_corrupt(tmp_path):
    legacy_file = tmp_path / "non_existent.json"
    target_master_file = tmp_path / "master.json"

    store = MasterStateStore(master_path=target_master_file, legacy_path=legacy_file)
    with pytest.raises(AuthError):
        store.migrate_legacy()

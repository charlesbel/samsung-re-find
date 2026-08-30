import json

import pytest

from samsung_find.credentials import MasterStateStore
from samsung_find.exceptions import AuthError


def test_migrate_legacy_state_preserves_source_and_creates_master(tmp_path):
    legacy_file = tmp_path / "legacy" / "state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.parent.chmod(0o700)
    legacy_content = json.dumps(
        {
            "schema": 1,
            "device_id": "synthetic-test-device-id-999",
            "auth_server_url": "https://auth.samsungosp.com",
            "login_id": "synthetic-test-user@example.invalid",
            "user_id": "synthetic-test-user-id-888",
            "userauth_token": "synthetic-test-userauth-token-777",
            "find": {"access_token": "find_at", "refresh_token": "find_rt"},
            "iot": {"access_token": "iot_at", "refresh_token": "iot_rt"},
        },
        indent=2,
    )
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
    assert loaded.account.login_id == "synthetic-test-user@example.invalid"
    assert loaded.account.user_id == "synthetic-test-user-id-888"
    assert loaded.installation.physical_address == "synthetic-test-device-id-999"
    assert loaded.identity.userauth_token == "synthetic-test-userauth-token-777"
    assert loaded.identity.auth_server_url == "https://auth.samsungosp.com"


def test_migrate_already_migrated_is_idempotent(tmp_path):
    legacy_file = tmp_path / "legacy" / "state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.parent.chmod(0o700)
    legacy_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "device_id": "synthetic-test-device-id-999",
                "auth_server_url": "https://auth.samsungosp.com",
                "login_id": "synthetic-test-user@example.invalid",
                "user_id": "synthetic-test-user-id-888",
                "userauth_token": "synthetic-test-userauth-token-777",
            }
        ),
        encoding="utf-8",
    )
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


@pytest.mark.parametrize(
    "incomplete_data",
    [
        {
            "device_id": "d1",
            "auth_server_url": "https://auth.samsungosp.com",
            "userauth_token": "t1",
        },  # missing login_id
        {
            "login_id": "u1",
            "auth_server_url": "https://auth.samsungosp.com",
            "userauth_token": "t1",
        },  # missing device_id
        {"login_id": "u1", "device_id": "d1", "userauth_token": "t1"},  # missing auth_server_url
        {
            "login_id": "u1",
            "device_id": "d1",
            "auth_server_url": "https://auth.samsungosp.com",
        },  # missing userauth_token
    ],
)
def test_migrate_rejects_incomplete_legacy_data(tmp_path, incomplete_data):
    legacy_file = tmp_path / "incomplete_legacy.json"
    legacy_file.write_text(json.dumps(incomplete_data), encoding="utf-8")
    legacy_file.chmod(0o600)

    target_master = tmp_path / "master.json"
    store = MasterStateStore(master_path=target_master, legacy_path=legacy_file)

    with pytest.raises(AuthError):
        store.migrate_legacy()


@pytest.mark.parametrize(
    "adversarial_created_at",
    [
        9999999999.0,  # far future timestamp
        -500.0,  # negative timestamp
        "invalid_timestamp",  # corrupted string
        True,  # boolean
        None,  # None
    ],
)
def test_migrate_adversarial_created_at_normalized_and_reloads(tmp_path, adversarial_created_at):
    import math

    legacy_file = tmp_path / "legacy" / "state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.parent.chmod(0o700)
    legacy_data = {
        "schema": 1,
        "device_id": "synthetic-test-device-id-999",
        "auth_server_url": "https://auth.samsungosp.com",
        "login_id": "synthetic-test-user@example.invalid",
        "user_id": "synthetic-test-user-id-888",
        "userauth_token": "synthetic-test-userauth-token-777",
        "created_at": adversarial_created_at,
    }
    legacy_file.write_text(json.dumps(legacy_data), encoding="utf-8")
    legacy_file.chmod(0o600)

    target_master_file = tmp_path / "master" / "master.json"
    canonical_derived = tmp_path / "derived" / "state.json"
    store = MasterStateStore(
        master_path=target_master_file,
        canonical_state_path=canonical_derived,
        legacy_path=legacy_file,
    )
    result = store.migrate_legacy()
    assert result["migrated"] is True

    # Emitted master satisfies created_at <= updated_at and immediately reloads without error
    loaded = store.load(allow_legacy_fallback=False)
    assert loaded is not None
    assert math.isfinite(loaded.created_at)
    assert math.isfinite(loaded.updated_at)
    assert 0 <= loaded.created_at <= loaded.updated_at
    assert loaded.account.login_id == "synthetic-test-user@example.invalid"

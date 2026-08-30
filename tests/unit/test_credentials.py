import json
import os
import stat
import uuid

import pytest

from samsung_find.credentials import (
    MasterAccount,
    MasterIdentity,
    MasterInstallation,
    MasterState,
    MasterStateStore,
    resolve_master_state_path,
)
from samsung_find.exceptions import AuthError, SecurityError


def test_master_state_repr_redaction():
    state = MasterState(
        schema="io.github.charlesbel.samsung-account.master",
        schema_version=1,
        generation=str(uuid.uuid4()),
        created_at=1700000000.0,
        updated_at=1700000000.0,
        account=MasterAccount(
            login_id="synthetic-test-user@example.invalid",
            user_id="synthetic-test-user-12345",
        ),
        installation=MasterInstallation(physical_address="synthetic-test-address-01"),
        identity=MasterIdentity(
            auth_server_url="https://synthetic-test.samsungosp.com",
            userauth_token="synthetic-test-userauth-token-not-real",
        ),
    )
    repr_str = repr(state)
    str_str = str(state)
    for text in (repr_str, str_str):
        assert "synthetic-test-userauth-token-not-real" not in text
        assert "synthetic-test-user@example.invalid" not in text
        assert "synthetic-test-user-12345" not in text
        assert "synthetic-test-address-01" not in text
        assert "[REDACTED]" in text or "***" in text


def test_master_state_store_save_and_load(tmp_path):
    master_file = tmp_path / "samsung-account" / "master.json"
    store = MasterStateStore(master_file)

    saved = store.save(
        login_id="synthetic-test-user@example.invalid",
        user_id="synthetic-test-uid",
        physical_address="synthetic-test-device-id",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="synthetic-test-token-not-real-001",
    )

    assert saved.schema == "io.github.charlesbel.samsung-account.master"
    assert saved.schema_version == 1
    assert saved.account.login_id == "synthetic-test-user@example.invalid"
    assert saved.identity.userauth_token == "synthetic-test-token-not-real-001"
    assert master_file.exists()

    if hasattr(os, "chmod") and os.name != "nt":
        mode = stat.S_IMODE(master_file.stat().st_mode)
        assert mode == 0o600
        parent_mode = stat.S_IMODE(master_file.parent.stat().st_mode)
        assert parent_mode == 0o700

    loaded = store.load()
    assert loaded == saved


def test_master_state_generation_rotation(tmp_path):
    master_file = tmp_path / "master.json"
    store = MasterStateStore(master_file)

    first = store.save(
        login_id="synthetic-test-user@example.invalid",
        user_id="synthetic-test-uid",
        physical_address="synthetic-test-device-id",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="synthetic-test-token-1",
    )

    second = store.save(
        login_id="synthetic-test-user@example.invalid",
        user_id="synthetic-test-uid",
        physical_address="synthetic-test-device-id",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="synthetic-test-token-2",
    )

    assert first.generation != second.generation
    assert second.identity.userauth_token == "synthetic-test-token-2"


def test_master_state_store_rejects_symlink(tmp_path):
    target_file = tmp_path / "real_master.json"
    target_file.write_text("{}", encoding="utf-8")
    symlink_file = tmp_path / "symlink_master.json"
    symlink_file.symlink_to(target_file)

    with pytest.raises((SecurityError, AuthError, ValueError)):
        store = MasterStateStore(symlink_file)
        store.load()


def test_master_state_store_rejects_symlink_parent_directory(tmp_path):
    """Reproduction of symlink parent traversal attack."""
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir(parents=True, mode=0o700)
    real_file = real_dir / "master.json"
    real_file.write_text("{}", encoding="utf-8")
    real_file.chmod(0o600)

    symlink_dir = tmp_path / "symlink_dir"
    symlink_dir.symlink_to(real_dir, target_is_directory=True)

    symlink_path = symlink_dir / "master.json"
    with pytest.raises(SecurityError, match="is a symlink"):
        store = MasterStateStore(symlink_path)
        store.load()


def test_master_state_from_dict_strict_schema():
    valid = {
        "schema": "io.github.charlesbel.samsung-account.master",
        "schema_version": 1,
        "generation": "gen-1",
        "created_at": 100.0,
        "updated_at": 200.0,
        "account": {"login_id": "user@example.invalid", "user_id": "uid-1"},
        "installation": {"physical_address": "dev-1"},
        "identity": {"auth_server_url": "https://auth.samsungosp.com", "userauth_token": "tok-1"},
    }
    state = MasterState.from_dict(valid)
    assert state.schema == "io.github.charlesbel.samsung-account.master"
    assert state.schema_version == 1

    # Unknown top-level key
    with pytest.raises(AuthError, match="Master state contains unauthorized or unknown fields"):
        MasterState.from_dict({**valid, "extra_key": "val"})

    # Boolean as schema_version (type(True) is bool)
    with pytest.raises(AuthError, match="Unsupported master schema version"):
        MasterState.from_dict({**valid, "schema_version": True})

    # Boolean as created_at
    with pytest.raises(AuthError, match="invalid created_at timestamp"):
        MasterState.from_dict({**valid, "created_at": True})

    # JSON Schema timestamps are finite and non-negative
    for invalid_timestamp in (-1, float("nan"), float("inf")):
        with pytest.raises(AuthError, match="invalid created_at timestamp"):
            MasterState.from_dict({**valid, "created_at": invalid_timestamp})

    # Missing updated_at
    invalid_no_ts = dict(valid)
    del invalid_no_ts["updated_at"]
    with pytest.raises(AuthError, match="invalid updated_at timestamp"):
        MasterState.from_dict(invalid_no_ts)

    # Empty generation string
    with pytest.raises(AuthError, match="invalid generation identifier"):
        MasterState.from_dict({**valid, "generation": "   "})

    # Account extra key
    with pytest.raises(AuthError, match="account object contains unauthorized fields"):
        MasterState.from_dict({**valid, "account": {"login_id": "u", "bad": "key"}})

    # Identity invalid auth url
    with pytest.raises(AuthError, match="untrusted identity.auth_server_url"):
        MasterState.from_dict({**valid, "identity": {"auth_server_url": "https://evil.example", "userauth_token": "t"}})

    # updated_at earlier than created_at
    with pytest.raises(AuthError, match="updated_at cannot be earlier than created_at"):
        MasterState.from_dict({**valid, "created_at": 200.0, "updated_at": 100.0})


def test_migration_rejects_same_source_and_target(tmp_path):
    same_file = tmp_path / "same.json"
    same_file.write_text("{}", encoding="utf-8")
    store = MasterStateStore(master_path=same_file, legacy_path=same_file)
    with pytest.raises(AuthError, match="cannot be the same file"):
        store.migrate_legacy()


def test_master_state_store_rejects_untrusted_auth_host(tmp_path):
    master_file = tmp_path / "master.json"
    store = MasterStateStore(master_file)

    with pytest.raises(SecurityError):
        store.save(
            login_id="synthetic-test-user@example.invalid",
            user_id="synthetic-test-uid",
            physical_address="synthetic-test-device-id",
            auth_server_url="https://attacker-controlled.com",
            userauth_token="synthetic-test-token",
        )


def test_master_state_path_resolution(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom" / "master.json"

    # 1. Explicit override
    resolved = resolve_master_state_path(explicit_path=str(custom_path))
    assert resolved == custom_path

    # 2. Environment variable
    monkeypatch.setenv("SAMSUNG_ACCOUNT_MASTER_STATE", str(custom_path))
    resolved = resolve_master_state_path()
    assert resolved == custom_path

    # 3. Default path (platformdirs/XDG)
    monkeypatch.delenv("SAMSUNG_ACCOUNT_MASTER_STATE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    resolved = resolve_master_state_path()
    assert resolved == (tmp_path / "config" / "samsung-account" / "master.json")


def test_legacy_fallback_loading(tmp_path):
    legacy_file = tmp_path / "legacy_state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "device_id": "synthetic-test-device-id-123",
                "auth_server_url": "https://auth.samsungosp.com",
                "login_id": "synthetic-test-user@example.invalid",
                "user_id": "synthetic-test-uid-456",
                "userauth_token": "synthetic-test-master-token-789",
                "find": {"access_token": "at", "refresh_token": "rt"},
                "iot": {"access_token": "iat", "refresh_token": "irt"},
            }
        ),
        encoding="utf-8",
    )
    legacy_file.chmod(0o600)

    store = MasterStateStore(
        master_path=tmp_path / "non_existent_master.json",
        legacy_path=legacy_file,
    )
    loaded = store.load(allow_legacy_fallback=True)
    assert loaded is not None
    assert loaded.account.login_id == "synthetic-test-user@example.invalid"
    assert loaded.identity.userauth_token == "synthetic-test-master-token-789"
    assert loaded.installation.physical_address == "synthetic-test-device-id-123"

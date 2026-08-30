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
        account=MasterAccount(login_id="user@example.com", user_id="user_12345"),
        installation=MasterInstallation(physical_address="AA:BB:CC:DD:EE:FF"),
        identity=MasterIdentity(
            auth_server_url="https://auth.samsungosp.com",
            userauth_token="SUPER_SECRET_USERAUTH_TOKEN_VALUE",
        ),
    )
    repr_str = repr(state)
    str_str = str(state)
    for text in (repr_str, str_str):
        assert "SUPER_SECRET_USERAUTH_TOKEN_VALUE" not in text
        assert "user@example.com" not in text
        assert "user_12345" not in text
        assert "AA:BB:CC:DD:EE:FF" not in text
        assert "[REDACTED]" in text or "***" in text


def test_master_state_store_save_and_load(tmp_path):
    master_file = tmp_path / "samsung-account" / "master.json"
    store = MasterStateStore(master_file)

    saved = store.save(
        login_id="alice@example.com",
        user_id="alice_uid",
        physical_address="11:22:33:44:55:66",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="secret_token_123",
    )

    assert saved.schema == "io.github.charlesbel.samsung-account.master"
    assert saved.schema_version == 1
    assert saved.account.login_id == "alice@example.com"
    assert saved.identity.userauth_token == "secret_token_123"
    assert master_file.exists()

    # Permissions on POSIX
    if hasattr(os, "chmod"):
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
        login_id="alice@example.com",
        user_id="alice_uid",
        physical_address="11:22:33:44:55:66",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="secret_token_1",
    )

    second = store.save(
        login_id="alice@example.com",
        user_id="alice_uid",
        physical_address="11:22:33:44:55:66",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="secret_token_2",
    )

    assert first.generation != second.generation
    assert second.identity.userauth_token == "secret_token_2"


def test_master_state_store_rejects_symlink(tmp_path):
    target_file = tmp_path / "real_master.json"
    target_file.write_text("{}", encoding="utf-8")
    symlink_file = tmp_path / "symlink_master.json"
    symlink_file.symlink_to(target_file)

    store = MasterStateStore(symlink_file)
    with pytest.raises((SecurityError, AuthError, ValueError)):
        store.load()


def test_master_state_store_rejects_untrusted_auth_host(tmp_path):
    master_file = tmp_path / "master.json"
    store = MasterStateStore(master_file)

    with pytest.raises(SecurityError):
        store.save(
            login_id="alice@example.com",
            user_id="alice_uid",
            physical_address="11:22:33:44:55:66",
            auth_server_url="https://attacker-controlled.com",
            userauth_token="secret_token",
        )


def test_master_state_path_resolution(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom" / "master.json"

    # 1. Explicit override
    resolved = resolve_master_state_path(explicit_path=str(custom_path))
    assert resolved == custom_path.resolve()

    # 2. Environment variable
    monkeypatch.setenv("SAMSUNG_ACCOUNT_MASTER_STATE", str(custom_path))
    resolved = resolve_master_state_path()
    assert resolved == custom_path.resolve()

    # 3. Default path (platformdirs/XDG)
    monkeypatch.delenv("SAMSUNG_ACCOUNT_MASTER_STATE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    resolved = resolve_master_state_path()
    assert resolved == (tmp_path / "config" / "samsung-account" / "master.json").resolve()


def test_legacy_fallback_loading(tmp_path):
    legacy_file = tmp_path / "legacy_state.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "device_id": "legacy_device_id_123",
                "auth_server_url": "https://auth.samsungosp.com",
                "login_id": "legacy_user@example.com",
                "user_id": "legacy_uid_456",
                "userauth_token": "legacy_master_token_789",
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
    assert loaded.account.login_id == "legacy_user@example.com"
    assert loaded.identity.userauth_token == "legacy_master_token_789"
    assert loaded.installation.physical_address == "legacy_device_id_123"

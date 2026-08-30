import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from samsung_find.auth import FIND, SamsungAuth
from samsung_find.config import FindConfig
from samsung_find.credentials import (
    MasterStateStore,
    resolve_find_state_path,
    resolve_legacy_find_state_path,
    resolve_master_state_path,
    validate_derived_state,
)
from samsung_find.exceptions import AuthError, SecurityError


def test_path_resolvers_platformdirs_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("SAMSUNG_ACCOUNT_MASTER_STATE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_STATE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_LEGACY_STATE", raising=False)

    monkeypatch.setattr(sys, "platform", "linux")

    master_path = resolve_master_state_path()
    derived_path = resolve_find_state_path()
    legacy_path = resolve_legacy_find_state_path()

    assert master_path == (tmp_path / ".config" / "samsung-account" / "master.json").resolve()
    assert derived_path == (tmp_path / ".local" / "state" / "samsung-find" / "state.json").resolve()
    assert legacy_path == (tmp_path / ".config" / "samsung-find" / "state.json").resolve()


def test_path_resolvers_mocked_darwin_and_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("SAMSUNG_ACCOUNT_MASTER_STATE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_STATE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_LEGACY_STATE", raising=False)

    # Darwin
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    derived_mac = resolve_find_state_path()
    assert "Library" in str(derived_mac) or "samsung-find" in str(derived_mac)

    # Windows
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    derived_win = resolve_find_state_path()
    assert "AppData" in str(derived_win)
    assert "state.json" in str(derived_win)


def test_find_config_exposes_canonical_and_legacy_paths(tmp_path):
    master_file = tmp_path / "master.json"
    derived_file = tmp_path / "state.json"
    legacy_file = tmp_path / "legacy.json"

    cfg = FindConfig(
        master_state_path=master_file,
        state_path=derived_file,
        legacy_state_path=legacy_file,
    )

    assert cfg.master_state_path == master_file.resolve()
    assert cfg.state_path == derived_file.resolve()
    assert cfg.legacy_state_path == legacy_file.resolve()


def test_derived_state_rejects_forbidden_master_keys():
    forbidden_keys = [
        "userauth_token",
        "login_id",
        "user_id",
        "physical_address",
        "device_id",
        "auth_server_url",
        "account",
        "identity",
        "installation",
    ]
    for key in forbidden_keys:
        bad_data = {
            "schema": 1,
            "find": {"access_token": "at"},
            key: "sensitive_value",
        }
        with pytest.raises(SecurityError) as exc_info:
            validate_derived_state(bad_data)
        assert "Forbidden master key" in str(exc_info.value) or "forbidden" in str(exc_info.value).lower()


def test_migration_creates_master_and_clean_derived_without_mutating_legacy(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir(parents=True, mode=0o700)
    legacy_file = legacy_dir / "state.json"
    legacy_content = json.dumps(
        {
            "schema": 1,
            "device_id": "synthetic-device-id-123",
            "auth_server_url": "https://auth.samsungosp.com",
            "login_id": "synthetic-user@example.invalid",
            "user_id": "synthetic-user-id-456",
            "userauth_token": "synthetic-userauth-token-789",
            "find": {"access_token": "find_at", "refresh_token": "find_rt", "expires_at": 1800000000},
            "iot": {"access_token": "iot_at", "refresh_token": "iot_rt", "expires_at": 1800000000},
            "web": {"jsessionid": "synth_session_id"},
        },
        indent=2,
    )
    legacy_file.write_text(legacy_content, encoding="utf-8")
    legacy_file.chmod(0o600)

    master_file = tmp_path / "config" / "master.json"
    derived_file = tmp_path / "state" / "state.json"

    store = MasterStateStore(
        master_path=master_file,
        canonical_state_path=derived_file,
        legacy_path=legacy_file,
    )
    result = store.migrate_legacy()

    assert result["migrated"] is True
    assert result["source_kind"] == "legacy_samsung_find"
    assert result["target_kind"] == "master_state_v1"

    # 1. Source legacy file must be byte-for-byte identical
    assert legacy_file.read_text(encoding="utf-8") == legacy_content

    # 2. Master file must contain identity
    assert master_file.exists()
    master = store.load(allow_legacy_fallback=False)
    assert master is not None
    assert master.account.login_id == "synthetic-user@example.invalid"
    assert master.installation.physical_address == "synthetic-device-id-123"
    assert master.identity.userauth_token == "synthetic-userauth-token-789"

    # 3. Canonical derived file must contain only derived tokens and ZERO master fields
    assert derived_file.exists()
    derived_data = json.loads(derived_file.read_text(encoding="utf-8"))
    validate_derived_state(derived_data)
    assert derived_data.get("find", {}).get("access_token") == "find_at"
    assert derived_data.get("iot", {}).get("access_token") == "iot_at"
    assert derived_data.get("web", {}).get("jsessionid") == "synth_session_id"
    for forbidden in ["userauth_token", "login_id", "user_id", "physical_address", "device_id", "auth_server_url"]:
        assert forbidden not in derived_data


def test_migration_idempotent_and_conflict_handling(tmp_path):
    legacy_file = tmp_path / "legacy.json"
    legacy_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "device_id": "dev-1",
                "auth_server_url": "https://auth.samsungosp.com",
                "login_id": "user1@example.invalid",
                "userauth_token": "token-1",
                "find": {"access_token": "f1"},
            }
        ),
        encoding="utf-8",
    )
    legacy_file.chmod(0o600)

    master_file = tmp_path / "master.json"
    derived_file = tmp_path / "state.json"

    store = MasterStateStore(
        master_path=master_file,
        canonical_state_path=derived_file,
        legacy_path=legacy_file,
    )

    # First migration
    first = store.migrate_legacy()
    assert first["migrated"] is True

    # Second migration: idempotent
    second = store.migrate_legacy()
    assert second["migrated"] is False

    # Conflict simulation: mutate master file
    master_file.write_text(
        json.dumps(
            {
                "schema": "io.github.charlesbel.samsung-account.master",
                "schema_version": 1,
                "generation": "gen-x",
                "created_at": 1.0,
                "updated_at": 1.0,
                "account": {"login_id": "other_user@example.invalid"},
                "installation": {"physical_address": "dev-x"},
                "identity": {"auth_server_url": "https://auth.samsungosp.com", "userauth_token": "other_token"},
            }
        ),
        encoding="utf-8",
    )
    master_file.chmod(0o600)

    # Without force: raises AuthError on conflict
    with pytest.raises(AuthError) as exc_info:
        store.migrate_legacy(force=False)
    assert "conflict" in str(exc_info.value).lower() or "force" in str(exc_info.value).lower()

    # With force: succeeds
    forced = store.migrate_legacy(force=True)
    assert forced["migrated"] is True


def test_migration_second_write_failure_rolls_back_first_write(tmp_path, monkeypatch):
    legacy_file = tmp_path / "legacy.json"
    legacy_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "device_id": "dev-1",
                "auth_server_url": "https://auth.samsungosp.com",
                "login_id": "user1@example.invalid",
                "userauth_token": "token-1",
            }
        ),
        encoding="utf-8",
    )
    legacy_file.chmod(0o600)

    master_file = tmp_path / "master.json"
    derived_file = tmp_path / "state.json"

    store = MasterStateStore(
        master_path=master_file,
        canonical_state_path=derived_file,
        legacy_path=legacy_file,
    )

    # Inject failure on writing derived state
    def fail_write_derived(path, data):
        raise OSError("Injected disk failure on derived state")

    monkeypatch.setattr(store, "_atomic_write_derived", fail_write_derived)

    with pytest.raises(OSError):
        store.migrate_legacy()

    # Master file must NOT exist (rolled back to avoid partial state)
    assert not master_file.exists(), "Master file should be rolled back if derived write fails"
    assert not derived_file.exists()


def test_auth_complete_never_persists_master_keys_to_derived_state(tmp_path):
    master_file = tmp_path / "master.json"
    derived_file = tmp_path / "state.json"
    pending_file = tmp_path / "pending.json"
    legacy_file = tmp_path / "legacy.json"

    auth = SamsungAuth(
        state_path=derived_file,
        pending_path=pending_file,
        master_path=master_file,
        legacy_state_path=legacy_file,
    )

    # Mock HTTP client responses for auth.complete()
    auth.http = MagicMock()
    auth.http.post.return_value.status_code = 200
    auth.http.post.return_value.json.return_value = {
        "userauth_token": "synth_userauth_token_999",
        "userId": "synth_user_id_888",
    }
    auth._issue_token = lambda kind, **kwargs: {
        "access_token": f"{kind.name}_at",
        "refresh_token": f"{kind.name}_rt",
        "expires_at": time.time() + 3600,
    }

    pending_data = {
        "state": "test_state",
        "device_id": "test_device_id",
        "code_verifier": "test_verifier",
        "created_at": time.time(),
    }
    pending_file.write_text(json.dumps(pending_data), encoding="utf-8")
    pending_file.chmod(0o600)

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    def _encrypt(val: str, k: str) -> str:
        key_bytes = k.encode()[:16].ljust(16, b"\0")
        padder = padding.PKCS7(128).padder()
        padded = padder.update(val.encode()) + padder.finalize()
        encryptor = Cipher(algorithms.AES(key_bytes), modes.ECB()).encryptor()
        return (encryptor.update(padded) + encryptor.finalize()).hex()

    key = "response_key_123"
    enc_state = _encrypt(key, "test_state")
    enc_server = _encrypt("https://auth.samsungosp.com", key)
    enc_code = _encrypt("test_code", key)
    enc_ret = _encrypt("synth_user@example.invalid", key)
    redirect_uri = f"ms-app://s-1-xxx?state={enc_state}&auth_server_url={enc_server}&code={enc_code}&retValue={enc_ret}"

    status = auth.complete(redirect_uri)
    assert status["authenticated"] is True

    # Verify MasterState saved to master_file
    assert master_file.exists()
    master = auth.master_store.load()
    assert master.account.login_id == "synth_user@example.invalid"
    assert master.identity.userauth_token == "synth_userauth_token_999"

    # Verify derived_file contains ONLY derived data and NO master fields
    assert derived_file.exists()
    derived = json.loads(derived_file.read_text(encoding="utf-8"))
    validate_derived_state(derived)
    for forbidden in ["userauth_token", "login_id", "user_id", "physical_address", "device_id", "auth_server_url"]:
        assert forbidden not in derived


def test_read_only_legacy_fallback_does_not_mutate_legacy_file(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir(parents=True, mode=0o700)
    legacy_file = legacy_dir / "state.json"
    legacy_content = json.dumps(
        {
            "schema": 1,
            "device_id": "synth_device",
            "auth_server_url": "https://auth.samsungosp.com",
            "login_id": "user@example.invalid",
            "userauth_token": "synth_token",
            "find": {"access_token": "valid_find_at", "expires_at": time.time() + 3600},
            "iot": {"access_token": "valid_iot_at", "expires_at": time.time() + 3600},
        },
        indent=2,
    )
    legacy_file.write_text(legacy_content, encoding="utf-8")
    legacy_file.chmod(0o600)

    master_file = tmp_path / "master.json"
    derived_file = tmp_path / "state.json"

    auth = SamsungAuth(
        state_path=derived_file,
        master_path=master_file,
        legacy_state_path=legacy_file,
    )

    # Status inspects legacy read-only
    status = auth.public_status()
    assert status["authenticated"] is True
    assert status["find_token_present"] is True

    # access_token uses valid token from legacy without writing legacy
    tok = auth.access_token(FIND)
    assert tok == "valid_find_at"

    # Legacy file must NOT have been changed
    assert legacy_file.read_text(encoding="utf-8") == legacy_content

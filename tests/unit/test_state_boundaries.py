import json
import stat
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from samsung_find.api import SamsungFindClient
from samsung_find.auth import SamsungAuth
from samsung_find.config import FindConfig
from samsung_find.credentials import (
    MasterStateStore,
    project_legacy_derived,
    resolve_find_state_path,
    resolve_legacy_find_state_path,
    resolve_master_state_path,
    validate_derived_state,
)
from samsung_find.exceptions import AuthError, SecurityError
from samsung_find.storage import secure_read_raw_text


def test_path_resolvers_platformdirs_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
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


def test_derived_state_rejects_forbidden_master_keys_recursively():
    forbidden_keys = [
        "userauth_token",
        "userAuthToken",
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
        # Top-level forbidden
        bad_top = {
            "schema": 1,
            "find": {"access_token": "at"},
            key: "sensitive_value",
        }
        with pytest.raises(SecurityError) as exc_info:
            validate_derived_state(bad_top)
        assert "forbidden" in str(exc_info.value).lower() or "unauthorized" in str(exc_info.value).lower()

        # Nested forbidden
        bad_nested = {
            "schema": 1,
            "find": {"access_token": "at", key: "nested_sensitive"},
        }
        with pytest.raises(SecurityError) as exc_info:
            validate_derived_state(bad_nested)
        assert "forbidden" in str(exc_info.value).lower() or "unauthorized" in str(exc_info.value).lower()


def test_derived_state_rejects_unknown_top_level_keys():
    bad_data = {
        "schema": 1,
        "unexpected_random_key": "some_value",
        "find": {"access_token": "at"},
    }
    with pytest.raises(SecurityError) as exc_info:
        validate_derived_state(bad_data)
    assert "unexpected_random_key" in str(exc_info.value)


def test_project_legacy_derived_sanitizes_cleanly():
    mixed_legacy = {
        "schema": 1,
        "device_id": "secret-device-id",
        "auth_server_url": "https://auth.samsungosp.com",
        "login_id": "user@example.invalid",
        "user_id": "secret-user-id",
        "userauth_token": "secret-master-token",
        "random_legacy_field": "disallowed",
        "find": {"access_token": "find_token_1", "refresh_token": "find_rt_1", "expires_at": 1800000000},
        "web": {"jsessionid": "session_123", "updated_at": 1700000000.0},
    }
    clean = project_legacy_derived(mixed_legacy, master_generation="gen-123")
    validate_derived_state(clean)
    assert clean["master_generation"] == "gen-123"
    assert clean["find"]["access_token"] == "find_token_1"
    assert clean["web"]["jsessionid"] == "session_123"
    assert "device_id" not in clean
    assert "userauth_token" not in clean
    assert "login_id" not in clean
    assert "user_id" not in clean
    assert "auth_server_url" not in clean
    assert "random_legacy_field" not in clean


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
    assert secure_read_raw_text(legacy_file, consume=False) == legacy_content

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


def test_migration_repair_matching_master_missing_derived_preserves_master_bytes(tmp_path):
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
    saved_master = store.save(
        login_id="user1@example.invalid",
        physical_address="dev-1",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="token-1",
    )
    original_master_bytes = master_file.read_bytes()
    original_master_mtime = master_file.stat().st_mtime_ns

    assert master_file.exists()
    assert not derived_file.exists()

    # Migration writes derived using existing master generation, and preserves master bytes
    res = store.migrate_legacy()
    assert res["migrated"] is True
    assert derived_file.exists()
    assert master_file.read_bytes() == original_master_bytes
    assert master_file.stat().st_mtime_ns == original_master_mtime

    derived_data = json.loads(derived_file.read_text(encoding="utf-8"))
    assert derived_data["master_generation"] == saved_master.generation
    assert derived_data["find"]["access_token"] == "f1"


def test_migration_generation_coherence_repairs_derived_without_rewriting_master(tmp_path):
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
    saved_master = store.save(
        login_id="user1@example.invalid",
        physical_address="dev-1",
        auth_server_url="https://auth.samsungosp.com",
        userauth_token="token-1",
    )
    original_master_bytes = master_file.read_bytes()

    # Pre-write derived state matching payload but with DIFFERENT generation
    derived_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "master_generation": "different-incoherent-gen",
                "find": {"access_token": "f1"},
            }
        ),
        encoding="utf-8",
    )
    derived_file.chmod(0o600)

    res = store.migrate_legacy()
    assert res["migrated"] is True

    # Master bytes must NOT have been rewritten
    assert master_file.read_bytes() == original_master_bytes

    # Derived state must have been repaired to match master generation
    derived_data = json.loads(derived_file.read_text(encoding="utf-8"))
    assert derived_data["master_generation"] == saved_master.generation
    assert derived_data["find"]["access_token"] == "f1"


def test_migration_preserves_derived_bytes_when_master_missing_with_valid_gen(tmp_path):
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
    derived_content = (
        json.dumps(
            {
                "schema": 1,
                "master_generation": "valid-derived-gen-12345",
                "find": {"access_token": "f1"},
            },
            indent=2,
        )
        + "\n"
    )
    derived_file.write_text(derived_content, encoding="utf-8")
    derived_file.chmod(0o600)
    original_derived_mtime = derived_file.stat().st_mtime_ns

    assert not master_file.exists()

    res = store.migrate_legacy()
    assert res["migrated"] is True
    assert master_file.exists()

    # Derived bytes and mtime must be preserved unchanged
    assert derived_file.read_text(encoding="utf-8") == derived_content
    assert derived_file.stat().st_mtime_ns == original_derived_mtime

    master_state = store.load(allow_legacy_fallback=False)
    assert master_state.generation == "valid-derived-gen-12345"


def test_migration_repairs_both_when_master_missing_and_derived_has_no_generation(tmp_path):
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
    derived_file.write_text(
        json.dumps({"schema": 1, "find": {"access_token": "f1"}}),
        encoding="utf-8",
    )
    derived_file.chmod(0o600)

    res = store.migrate_legacy()
    assert res["migrated"] is True
    assert master_file.exists()

    master_state = store.load(allow_legacy_fallback=False)
    derived_data = json.loads(derived_file.read_text(encoding="utf-8"))
    assert master_state.generation == derived_data["master_generation"]


def test_migration_both_matching_and_coherent_is_idempotent_noop_preserving_bytes_and_mtimes(tmp_path):
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

    first = store.migrate_legacy()
    assert first["migrated"] is True

    master_bytes = master_file.read_bytes()
    master_mtime = master_file.stat().st_mtime_ns
    derived_bytes = derived_file.read_bytes()
    derived_mtime = derived_file.stat().st_mtime_ns

    # Second migration with both existing and coherent => no-op
    second = store.migrate_legacy()
    assert second["migrated"] is False

    assert master_file.read_bytes() == master_bytes
    assert master_file.stat().st_mtime_ns == master_mtime
    assert derived_file.read_bytes() == derived_bytes
    assert derived_file.stat().st_mtime_ns == derived_mtime


def test_migration_force_overwrite_and_injected_second_write_failure_rollback(tmp_path, monkeypatch):
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

    original_master_content = (
        json.dumps(
            {
                "schema": "io.github.charlesbel.samsung-account.master",
                "schema_version": 1,
                "generation": "orig-gen",
                "created_at": 100.0,
                "updated_at": 100.0,
                "account": {"login_id": "orig_user@example.invalid"},
                "installation": {"physical_address": "orig-dev"},
                "identity": {"auth_server_url": "https://auth.samsungosp.com", "userauth_token": "orig-token"},
            },
            indent=2,
        )
        + "\n"
    )
    master_file.write_text(original_master_content, encoding="utf-8")
    master_file.chmod(0o600)

    original_derived_content = json.dumps({"schema": 1, "find": {"access_token": "orig_at"}}, indent=2) + "\n"
    derived_file.write_text(original_derived_content, encoding="utf-8")
    derived_file.chmod(0o600)

    store = MasterStateStore(
        master_path=master_file,
        canonical_state_path=derived_file,
        legacy_path=legacy_file,
    )

    # Injected failure on writing derived state
    def fail_write_derived(path, data):
        raise OSError("Injected disk error during derived write")

    monkeypatch.setattr(store, "_atomic_write_derived", fail_write_derived)

    with pytest.raises(OSError):
        store.migrate_legacy(force=True)

    # Verify that BOTH master and derived files were restored to exact preexisting contents
    assert master_file.read_text(encoding="utf-8") == original_master_content
    assert stat.S_IMODE(master_file.stat().st_mode) == 0o600
    assert derived_file.read_text(encoding="utf-8") == original_derived_content
    assert stat.S_IMODE(derived_file.stat().st_mode) == 0o600


def test_auth_state_legacy_fallback_never_exposes_master_fields(tmp_path):
    legacy_file = tmp_path / "legacy.json"
    legacy_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "device_id": "secret-dev",
                "auth_server_url": "https://auth.samsungosp.com",
                "login_id": "secret-user@example.invalid",
                "user_id": "secret-uid",
                "userauth_token": "secret-master-token",
                "find": {"access_token": "f1_token"},
            }
        ),
        encoding="utf-8",
    )
    legacy_file.chmod(0o600)

    derived_file = tmp_path / "non_existent_state.json"
    master_file = tmp_path / "master.json"

    auth = SamsungAuth(
        state_path=derived_file,
        master_path=master_file,
        legacy_state_path=legacy_file,
    )

    fallback_state = auth.state()
    validate_derived_state(fallback_state)
    for forbidden in ["userauth_token", "login_id", "user_id", "physical_address", "device_id", "auth_server_url"]:
        assert forbidden not in fallback_state
    assert fallback_state["find"]["access_token"] == "f1_token"


def test_verify_find_token_fails_closed_without_http_if_user_id_or_auth_server_missing(tmp_path):
    derived_file = tmp_path / "state.json"
    derived_file.write_text(
        json.dumps({"schema": 1, "find": {"access_token": "valid_token", "expires_at": time.time() + 3600}}),
        encoding="utf-8",
    )
    derived_file.chmod(0o600)
    master_file = tmp_path / "master.json"
    legacy_file = tmp_path / "nonexistent_legacy.json"

    auth = SamsungAuth(
        state_path=derived_file,
        master_path=master_file,
        legacy_state_path=legacy_file,
    )
    client = SamsungFindClient(auth)
    client.http = MagicMock()

    # 1. Master file does not exist -> master summary has None for auth_server_url and user_id
    with pytest.raises(AuthError) as exc_info:
        client.verify_find_token()

    assert "missing auth_server_url or user_id" in str(exc_info.value)
    client.http.get.assert_not_called()

    # 2. Master exists but user_id is None
    master_file.write_text(
        json.dumps(
            {
                "schema": "io.github.charlesbel.samsung-account.master",
                "schema_version": 1,
                "generation": "gen-1",
                "created_at": 100.0,
                "updated_at": 100.0,
                "account": {"login_id": "user@example.invalid"},
                "installation": {"physical_address": "dev-1"},
                "identity": {"auth_server_url": "https://auth.samsungosp.com", "userauth_token": "token-1"},
            }
        ),
        encoding="utf-8",
    )
    master_file.chmod(0o600)
    with pytest.raises(AuthError) as exc_info2:
        client.verify_find_token()
    assert "missing auth_server_url or user_id" in str(exc_info2.value)
    client.http.get.assert_not_called()


def test_migrate_then_verify_find_token_works_from_canonical_only(tmp_path):
    legacy_file = tmp_path / "legacy.json"
    legacy_file.write_text(
        json.dumps(
            {
                "schema": 1,
                "device_id": "synth-device-uuid",
                "auth_server_url": "https://auth.samsungosp.com",
                "login_id": "user@example.invalid",
                "user_id": "synth-user-guid-999",
                "userauth_token": "master-userauth-token",
                "find": {"access_token": "valid_find_token", "expires_at": time.time() + 3600},
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
    store.migrate_legacy()

    auth = SamsungAuth(
        state_path=derived_file,
        master_path=master_file,
        legacy_state_path=legacy_file,
    )
    client = SamsungFindClient(auth)

    # Mock HTTP client for verify endpoint
    client.http = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_success = True
    client.http.get.return_value = mock_resp

    assert client.verify_find_token() is True

    # Verify that verify_find_token called endpoint with correct headers without needing master fields in state()
    call_args = client.http.get.call_args
    assert "https://api.samsungfind.com/users/synth-user-guid-999/key" in call_args[0]
    headers = call_args[1]["headers"]
    assert headers["X-Sec-Sa-Userid"] == "synth-user-guid-999"
    assert headers["X-Sec-Sa-Authtoken"] == "valid_find_token"
    assert headers["X-Sec-Sa-Authserverurl"] == "auth.samsungosp.com"

    # Verify derived state still contains NO master fields
    derived_data = json.loads(derived_file.read_text(encoding="utf-8"))
    validate_derived_state(derived_data)
    for forbidden in ["userauth_token", "login_id", "user_id", "physical_address", "device_id", "auth_server_url"]:
        assert forbidden not in derived_data

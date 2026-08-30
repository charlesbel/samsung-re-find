"""Shared Samsung Account Master Credentials Contract (v1)."""

from __future__ import annotations

import contextlib
import json
import math
import os
import stat
import sys
import time
import urllib.parse
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import AuthError, SecurityError, StorageError
from .storage import (
    atomic_write_json,
    atomic_write_text,
    expand,
    locked,
    read_json,
    secure_read_raw_text,
)

MASTER_SCHEMA_ID = "io.github.charlesbel.samsung-account.master"
MASTER_SCHEMA_VERSION = 1

ALLOWED_MASTER_TOP_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "generation",
        "created_at",
        "updated_at",
        "account",
        "installation",
        "identity",
    }
)

ALLOWED_DERIVED_TOP_KEYS = frozenset(
    {
        "schema",
        "master_generation",
        "created_at",
        "updated_at",
        "find",
        "iot",
        "web",
    }
)

ALLOWED_FIND_IOT_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "expires_at",
        "obtained_at",
        "token_type",
        "scope",
        "expires_in",
    }
)

ALLOWED_WEB_KEYS = frozenset(
    {
        "jsessionid",
        "updated_at",
        "obtained_at",
    }
)

FORBIDDEN_MASTER_KEY_NAMES = frozenset(
    {
        "userauth_token",
        "userauthtoken",
        "login_id",
        "loginid",
        "user_id",
        "userid",
        "physical_address",
        "physicaladdress",
        "device_id",
        "deviceid",
        "auth_server_url",
        "authserverurl",
        "account",
        "identity",
        "installation",
    }
)


def _check_no_forbidden_keys_recursive(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise SecurityError("Non-string key in derived state")
            k_clean = k.lower().replace("_", "").replace("-", "")
            if k_clean in {name.lower().replace("_", "").replace("-", "") for name in FORBIDDEN_MASTER_KEY_NAMES}:
                raise SecurityError(f"Forbidden master key found in derived state: {k!r}")
            _check_no_forbidden_keys_recursive(v)
    elif isinstance(obj, list):
        for item in obj:
            _check_no_forbidden_keys_recursive(item)


def validate_derived_state(data: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate derived state against allowlisted schema and reject any master keys."""
    if not isinstance(data, dict):
        raise SecurityError("Derived state must be a JSON dictionary")

    _check_no_forbidden_keys_recursive(data)

    for k in data:
        if k not in ALLOWED_DERIVED_TOP_KEYS:
            raise SecurityError(f"Unknown or unauthorized top-level key in derived state: {k!r}")

    schema = data.get("schema")
    if schema is not None and (type(schema) is not int or isinstance(schema, bool)):
        raise SecurityError("Derived state 'schema' must be an integer")

    generation = data.get("master_generation")
    if generation is not None and not isinstance(generation, str):
        raise SecurityError("Derived state 'master_generation' must be a string")

    for ts_key in ("created_at", "updated_at"):
        ts = data.get(ts_key)
        if ts is not None and (type(ts) not in (int, float) or isinstance(ts, bool)):
            raise SecurityError(f"Derived state '{ts_key}' must be numeric")

    for kind in ("find", "iot"):
        token_obj = data.get(kind)
        if token_obj is not None:
            if not isinstance(token_obj, dict):
                raise SecurityError(f"Derived state '{kind}' must be a dictionary")
            for k, v in token_obj.items():
                if k not in ALLOWED_FIND_IOT_KEYS:
                    raise SecurityError(f"Unauthorized key in '{kind}' token object: {k!r}")
                if k in ("access_token", "refresh_token", "token_type", "scope") and not isinstance(v, str):
                    raise SecurityError(f"Invalid type for '{kind}.{k}'")
                if k in ("expires_at", "obtained_at", "expires_in") and (
                    type(v) not in (int, float) or isinstance(v, bool)
                ):
                    raise SecurityError(f"Invalid numeric timestamp for '{kind}.{k}'")

    web_obj = data.get("web")
    if web_obj is not None:
        if not isinstance(web_obj, dict):
            raise SecurityError("Derived state 'web' must be a dictionary")
        for k, v in web_obj.items():
            if k not in ALLOWED_WEB_KEYS:
                raise SecurityError(f"Unauthorized key in 'web' object: {k!r}")
            if k == "jsessionid" and not isinstance(v, str):
                raise SecurityError("Invalid type for 'web.jsessionid'")
            if k in ("updated_at", "obtained_at") and (type(v) not in (int, float) or isinstance(v, bool)):
                raise SecurityError(f"Invalid numeric timestamp for 'web.{k}'")

    return data


def _normalize_legacy_timestamp(raw_ts: Any, default_now: float, *, max_ts: float | None = None) -> float:
    """Safely parse and normalize legacy timestamp, rejecting non-finite/negative/future values."""
    if raw_ts is None or isinstance(raw_ts, bool):
        return default_now
    try:
        val = float(raw_ts)
    except (ValueError, TypeError):
        return default_now
    if not math.isfinite(val) or val < 0:
        return default_now
    if max_ts is not None and val > max_ts:
        return max_ts
    return val


def project_legacy_derived(legacy_data: dict[str, Any], master_generation: str | None = None) -> dict[str, Any]:
    """Extract and validate a clean derived state projection from legacy mixed state."""
    if not isinstance(legacy_data, dict):
        return {}

    now = time.time()
    created_at = _normalize_legacy_timestamp(legacy_data.get("created_at"), now, max_ts=now)
    updated_at = _normalize_legacy_timestamp(legacy_data.get("updated_at"), now, max_ts=now)
    if updated_at < created_at:
        updated_at = created_at

    clean: dict[str, Any] = {
        "schema": 1,
        "master_generation": master_generation or str(uuid.uuid4()),
        "created_at": created_at,
        "updated_at": updated_at,
    }

    if isinstance(legacy_data.get("find"), dict):
        clean["find"] = {k: v for k, v in legacy_data["find"].items() if k in ALLOWED_FIND_IOT_KEYS}

    if isinstance(legacy_data.get("iot"), dict):
        clean["iot"] = {k: v for k, v in legacy_data["iot"].items() if k in ALLOWED_FIND_IOT_KEYS}

    if isinstance(legacy_data.get("web"), dict):
        clean["web"] = {k: v for k, v in legacy_data["web"].items() if k in ALLOWED_WEB_KEYS}

    return validate_derived_state(clean)


@dataclass(frozen=True)
class MasterAccount:
    login_id: str
    user_id: str | None = None

    def __repr__(self) -> str:
        return f"MasterAccount(login_id='[REDACTED]', user_id={('[REDACTED]' if self.user_id else None)!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class MasterInstallation:
    physical_address: str

    def __repr__(self) -> str:
        return "MasterInstallation(physical_address='[REDACTED]')"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class MasterIdentity:
    auth_server_url: str
    userauth_token: str

    def __repr__(self) -> str:
        return f"MasterIdentity(auth_server_url={self.auth_server_url!r}, userauth_token='***')"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class MasterState:
    schema: str
    schema_version: int
    generation: str
    created_at: float
    updated_at: float
    account: MasterAccount
    installation: MasterInstallation
    identity: MasterIdentity

    def __repr__(self) -> str:
        return (
            f"MasterState(schema={self.schema!r}, schema_version={self.schema_version!r}, "
            f"generation={self.generation!r}, account={self.account!r}, "
            f"installation={self.installation!r}, identity={self.identity!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "generation": self.generation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "account": {
                "login_id": self.account.login_id,
                "user_id": self.account.user_id,
            },
            "installation": {
                "physical_address": self.installation.physical_address,
            },
            "identity": {
                "auth_server_url": self.identity.auth_server_url,
                "userauth_token": self.identity.userauth_token,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MasterState:
        if not isinstance(data, dict):
            raise StorageError("Master state is not a valid JSON object")

        if not set(data).issubset(ALLOWED_MASTER_TOP_KEYS):
            raise AuthError("Master state contains unauthorized or unknown fields")

        schema = data.get("schema")
        if schema != MASTER_SCHEMA_ID:
            raise AuthError("Unsupported master schema identifier")

        version = data.get("schema_version")
        if type(version) is not int or isinstance(version, bool) or version != MASTER_SCHEMA_VERSION:
            raise AuthError("Unsupported master schema version")

        generation = data.get("generation")
        if not isinstance(generation, str) or not generation.strip():
            raise AuthError("Master state missing or invalid generation identifier")

        created_raw = data.get("created_at")
        if (
            type(created_raw) not in (int, float)
            or isinstance(created_raw, bool)
            or not math.isfinite(float(created_raw))
            or float(created_raw) < 0
        ):
            raise AuthError("Master state missing or invalid created_at timestamp")

        updated_raw = data.get("updated_at")
        if (
            type(updated_raw) not in (int, float)
            or isinstance(updated_raw, bool)
            or not math.isfinite(float(updated_raw))
            or float(updated_raw) < 0
        ):
            raise AuthError("Master state missing or invalid updated_at timestamp")

        if float(updated_raw) < float(created_raw):
            raise AuthError("Master state updated_at cannot be earlier than created_at")

        account_raw = data.get("account")
        if not isinstance(account_raw, dict):
            raise AuthError("Master state missing or invalid account object")
        for k in account_raw:
            if k not in ("login_id", "user_id"):
                raise AuthError("Master state account object contains unauthorized fields")
        login_id = account_raw.get("login_id")
        if not isinstance(login_id, str) or not login_id.strip():
            raise AuthError("Master state missing or invalid account.login_id")
        user_id = account_raw.get("user_id")
        if user_id is not None and (not isinstance(user_id, str) or not user_id.strip()):
            raise AuthError("Master state account.user_id must be a non-empty string")
        account = MasterAccount(login_id=login_id.strip(), user_id=user_id.strip() if user_id else None)

        installation_raw = data.get("installation")
        if not isinstance(installation_raw, dict):
            raise AuthError("Master state missing or invalid installation object")
        if set(installation_raw) != {"physical_address"}:
            raise AuthError("Master state installation object contains unauthorized or missing fields")
        phys_addr = installation_raw.get("physical_address")
        if not isinstance(phys_addr, str) or not phys_addr.strip():
            raise AuthError("Master state missing or invalid installation.physical_address")
        installation = MasterInstallation(physical_address=phys_addr.strip())

        identity_raw = data.get("identity")
        if not isinstance(identity_raw, dict):
            raise AuthError("Master state missing or invalid identity object")
        if set(identity_raw) != {"auth_server_url", "userauth_token"}:
            raise AuthError("Master state identity object contains unauthorized or missing fields")
        auth_url_raw = identity_raw.get("auth_server_url")
        if not isinstance(auth_url_raw, str) or not auth_url_raw.strip():
            raise AuthError("Master state missing or invalid identity.auth_server_url")
        token_raw = identity_raw.get("userauth_token")
        if not isinstance(token_raw, str) or not token_raw.strip():
            raise AuthError("Master state missing or invalid identity.userauth_token")

        try:
            auth_server = validate_auth_server_url(auth_url_raw.strip())
        except SecurityError as exc:
            raise AuthError("Master state contains untrusted identity.auth_server_url") from exc

        identity = MasterIdentity(
            auth_server_url=auth_server,
            userauth_token=token_raw.strip(),
        )

        return cls(
            schema=schema,
            schema_version=version,
            generation=generation.strip(),
            created_at=float(created_raw),
            updated_at=float(updated_raw),
            account=account,
            installation=installation,
            identity=identity,
        )


def validate_auth_server_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    hostname = (parsed.hostname or "").lower()
    trusted_host = (
        hostname == "account.samsung.com" or hostname == "samsungosp.com" or hostname.endswith(".samsungosp.com")
    )
    try:
        port = parsed.port
    except ValueError as exc:
        raise SecurityError("Invalid authentication server URL port") from exc

    if (
        parsed.scheme != "https"
        or not trusted_host
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise SecurityError(f"Untrusted authentication server host: {hostname or 'unknown'}")
    return f"https://{hostname}"


def resolve_master_state_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve the master state file location using standard OS conventions."""
    if explicit_path:
        return expand(explicit_path)

    env_path = os.environ.get("SAMSUNG_ACCOUNT_MASTER_STATE")
    if env_path:
        return expand(env_path)

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return expand(base / "samsung-account" / "master.json")
    elif sys.platform == "darwin":
        return expand(Path.home() / "Library" / "Application Support" / "samsung-account" / "master.json")
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return expand(base / "samsung-account" / "master.json")


def resolve_find_state_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve canonical Find derived state location using standard OS conventions."""
    if explicit_path:
        return expand(explicit_path)

    env_path = os.environ.get("SAMSUNG_FIND_STATE")
    if env_path:
        return expand(env_path)

    if sys.platform == "win32":
        app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Local"
        return expand(base / "samsung-find" / "state.json")
    elif sys.platform == "darwin":
        return expand(Path.home() / "Library" / "Application Support" / "samsung-find" / "state.json")
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME")
        base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        return expand(base / "samsung-find" / "state.json")


def resolve_legacy_find_state_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve the legacy Find state file path (${XDG_CONFIG_HOME:-~/.config}/samsung-find/state.json)."""
    if explicit_path:
        return expand(explicit_path)

    env_path = os.environ.get("SAMSUNG_FIND_LEGACY_STATE")
    if env_path:
        return expand(env_path)

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return expand(base / "samsung-find" / "state.json")
    elif sys.platform == "darwin":
        return expand(Path.home() / "Library" / "Application Support" / "samsung-find" / "state.json")
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return expand(base / "samsung-find" / "state.json")


def resolve_pending_path(
    explicit_path: str | Path | None = None,
    master_path: str | Path | None = None,
) -> Path:
    """Resolve the shared pending Samsung Account authentication path."""
    if explicit_path:
        return expand(explicit_path)

    env_path = (
        os.environ.get("SAMSUNG_ACCOUNT_PENDING_PATH")
        or os.environ.get("SAMSUNG_ACCOUNT_PENDING")
        or os.environ.get("SAMSUNG_FIND_PENDING")
    )
    if env_path:
        return expand(env_path)
    if master_path is not None:
        return expand(Path(master_path).parent / "pending.json")

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return expand(base / "samsung-account" / "pending.json")
    elif sys.platform == "darwin":
        return expand(Path.home() / "Library" / "Application Support" / "samsung-account" / "pending.json")
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return expand(base / "samsung-account" / "pending.json")


def resolve_redirect_path(
    explicit_path: str | Path | None = None,
    master_path: str | Path | None = None,
) -> Path:
    """Resolve the shared Samsung Account OAuth redirect path."""
    if explicit_path:
        return expand(explicit_path)

    env_path = os.environ.get("SAMSUNG_ACCOUNT_REDIRECT_PATH") or os.environ.get("SAMSUNG_FIND_REDIRECT_PATH")
    if env_path:
        return expand(env_path)
    if master_path is not None:
        return expand(Path(master_path).parent / "redirect.uri")

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return expand(base / "samsung-account" / "redirect.uri")
    elif sys.platform == "darwin":
        return expand(Path.home() / "Library" / "Application Support" / "samsung-account" / "redirect.uri")
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return expand(base / "samsung-account" / "redirect.uri")


class MasterStateStore:
    """Store for managing shared Samsung master credentials and migration."""

    def __init__(
        self,
        master_path: str | Path | None = None,
        canonical_state_path: str | Path | None = None,
        legacy_path: str | Path | None = None,
    ):
        self.master_path = resolve_master_state_path(master_path)
        if canonical_state_path is not None:
            self.canonical_state_path = resolve_find_state_path(canonical_state_path)
        elif master_path is not None:
            self.canonical_state_path = expand(self.master_path.parent / "state.json")
        else:
            self.canonical_state_path = resolve_find_state_path(None)
        self.legacy_path = resolve_legacy_find_state_path(legacy_path)

    def exists(self) -> bool:
        return self.master_path.exists()

    def _load_master_locked(self) -> MasterState | None:
        if not self.master_path.exists():
            return None
        data = read_json(self.master_path)
        return MasterState.from_dict(data)

    def _save_master_locked(
        self,
        login_id: str,
        physical_address: str,
        auth_server_url: str,
        userauth_token: str,
        user_id: str | None = None,
        generation: str | None = None,
    ) -> MasterState:
        auth_server = validate_auth_server_url(auth_server_url)
        gen = generation or str(uuid.uuid4())
        now = time.time()
        created_at = now
        existing = self._load_master_locked()
        if existing:
            created_at = existing.created_at

        state = MasterState(
            schema=MASTER_SCHEMA_ID,
            schema_version=MASTER_SCHEMA_VERSION,
            generation=gen,
            created_at=created_at,
            updated_at=now,
            account=MasterAccount(login_id=login_id, user_id=user_id),
            installation=MasterInstallation(physical_address=physical_address),
            identity=MasterIdentity(
                auth_server_url=auth_server,
                userauth_token=userauth_token,
            ),
        )
        atomic_write_json(self.master_path, state.to_dict())
        return state

    def _load_legacy_locked(self) -> MasterState | None:
        if not self.legacy_path.exists():
            return None
        data = read_json(self.legacy_path)
        userauth = data.get("userauth_token")
        login_id = data.get("login_id")
        device_id = data.get("device_id")
        auth_server_raw = data.get("auth_server_url")
        if not userauth or not login_id or not device_id or not auth_server_raw:
            return None

        auth_server = validate_auth_server_url(str(auth_server_raw))
        now = time.time()
        ts = _normalize_legacy_timestamp(data.get("created_at"), now, max_ts=now)
        return MasterState(
            schema=MASTER_SCHEMA_ID,
            schema_version=MASTER_SCHEMA_VERSION,
            generation=str(uuid.uuid4()),
            created_at=ts,
            updated_at=ts,
            account=MasterAccount(
                login_id=str(login_id),
                user_id=str(data.get("user_id")) if data.get("user_id") else None,
            ),
            installation=MasterInstallation(
                physical_address=str(device_id),
            ),
            identity=MasterIdentity(
                auth_server_url=auth_server,
                userauth_token=str(userauth),
            ),
        )

    def _atomic_write_derived(self, path: Path, data: dict[str, Any]) -> None:
        validate_derived_state(data)
        atomic_write_json(path, data)

    def load(self, *, allow_legacy_fallback: bool = True) -> MasterState | None:
        if self.master_path.exists():
            with locked(self.master_path):
                return self._load_master_locked()

        if allow_legacy_fallback and self.legacy_path.exists():
            warnings.warn(
                "Using legacy authentication state from samsung-find. Run 'samsung-re-find migrate-master' to migrate.",
                UserWarning,
                stacklevel=2,
            )
            with locked(self.legacy_path):
                return self._load_legacy_locked()

        return None

    def save(
        self,
        login_id: str,
        physical_address: str,
        auth_server_url: str,
        userauth_token: str,
        user_id: str | None = None,
        generation: str | None = None,
    ) -> MasterState:
        with locked(self.master_path):
            return self._save_master_locked(
                login_id=login_id,
                physical_address=physical_address,
                auth_server_url=auth_server_url,
                userauth_token=userauth_token,
                user_id=user_id,
                generation=generation,
            )

    def migrate_legacy(self, *, force: bool = False) -> dict[str, Any]:
        """Migrate legacy samsung-find state to shared master-state-v1 and clean derived state."""
        # Reject source == target migration before locking
        if self.legacy_path == self.master_path or self.legacy_path == self.canonical_state_path:
            raise AuthError("Migration source and target paths cannot be the same file")

        paths = sorted([self.master_path, self.canonical_state_path, self.legacy_path], key=lambda p: str(p))

        with locked(paths[0]), locked(paths[1]), locked(paths[2]):
            if not self.legacy_path.exists():
                raise AuthError(f"Legacy state file does not exist: {self.legacy_path.name}")

            legacy_content = secure_read_raw_text(self.legacy_path, consume=False)
            try:
                legacy_data = json.loads(legacy_content)
            except Exception as exc:
                raise AuthError(f"Failed to read legacy state: {exc}") from exc

            userauth = legacy_data.get("userauth_token")
            login_id = legacy_data.get("login_id")
            device_id = legacy_data.get("device_id")
            auth_server_raw = legacy_data.get("auth_server_url")

            if not userauth or not isinstance(userauth, str) or not userauth.strip():
                raise AuthError("Legacy state is missing required userauth_token")
            if not login_id or not isinstance(login_id, str) or not login_id.strip():
                raise AuthError("Legacy state is missing required login_id")
            if not device_id or not isinstance(device_id, str) or not device_id.strip():
                raise AuthError("Legacy state is missing required device_id")
            if not auth_server_raw or not isinstance(auth_server_raw, str):
                raise AuthError("Legacy state is missing required auth_server_url")

            candidate_auth_server = validate_auth_server_url(auth_server_raw)
            candidate_user_id = str(legacy_data.get("user_id")) if legacy_data.get("user_id") else None
            candidate_login_id = login_id.strip()
            candidate_device_id = device_id.strip()
            candidate_userauth = userauth.strip()
            now = time.time()
            candidate_created_at = _normalize_legacy_timestamp(legacy_data.get("created_at"), now, max_ts=now)

            legacy_find = (
                {k: v for k, v in legacy_data["find"].items() if k in ALLOWED_FIND_IOT_KEYS}
                if isinstance(legacy_data.get("find"), dict)
                else None
            )
            legacy_iot = (
                {k: v for k, v in legacy_data["iot"].items() if k in ALLOWED_FIND_IOT_KEYS}
                if isinstance(legacy_data.get("iot"), dict)
                else None
            )
            legacy_web = (
                {k: v for k, v in legacy_data["web"].items() if k in ALLOWED_WEB_KEYS}
                if isinstance(legacy_data.get("web"), dict)
                else None
            )

            master_exists = self.master_path.exists()
            derived_exists = self.canonical_state_path.exists()

            existing_master: MasterState | None = None
            if master_exists:
                try:
                    existing_master = self._load_master_locked()
                except Exception:
                    existing_master = None

            master_matches = bool(
                existing_master
                and existing_master.account.login_id == candidate_login_id
                and existing_master.identity.userauth_token == candidate_userauth
                and existing_master.identity.auth_server_url == candidate_auth_server
                and existing_master.installation.physical_address == candidate_device_id
            )

            existing_derived: dict[str, Any] | None = None
            derived_valid = False
            if derived_exists:
                try:
                    existing_derived = read_json(self.canonical_state_path, required=False)
                    validate_derived_state(existing_derived)
                    derived_valid = True
                except Exception:
                    existing_derived = None
                    derived_valid = False

            existing_find = existing_derived.get("find") if existing_derived else None
            existing_iot = existing_derived.get("iot") if existing_derived else None
            existing_web = existing_derived.get("web") if existing_derived else None

            derived_payload_matches = bool(
                derived_valid
                and (existing_find == legacy_find if legacy_find else existing_find is None)
                and (existing_iot == legacy_iot if legacy_iot else existing_iot is None)
                and (existing_web == legacy_web if legacy_web else existing_web is None)
            )

            if master_exists and not master_matches and not force:
                raise AuthError("Target master state already exists with conflicting data. Use --force to overwrite.")

            if derived_exists and not derived_payload_matches and not force:
                raise AuthError("Target derived state already exists with conflicting data. Use --force to overwrite.")

            need_write_master = False
            need_write_derived = False

            if master_exists and master_matches and not force:
                final_generation = existing_master.generation
                if not derived_exists:
                    need_write_derived = True
                else:
                    derived_gen = existing_derived.get("master_generation") if existing_derived else None
                    if derived_valid and derived_gen == existing_master.generation:
                        # True idempotent no-op: both targets match and have coherent generation
                        return {
                            "migrated": False,
                            "source_kind": "legacy_samsung_find",
                            "target_kind": "master_state_v1",
                            "schema_version": MASTER_SCHEMA_VERSION,
                        }
                    else:
                        # Repair derived generation to match existing master generation
                        need_write_derived = True
            elif derived_exists and derived_payload_matches and derived_valid and not master_exists and not force:
                derived_gen = str(existing_derived.get("master_generation", "")).strip() if existing_derived else ""
                if derived_gen:
                    final_generation = derived_gen
                    need_write_master = True
                    need_write_derived = False
                else:
                    final_generation = str(uuid.uuid4())
                    need_write_master = True
                    need_write_derived = True
            else:
                final_generation = str(uuid.uuid4())
                need_write_master = True
                need_write_derived = True

            now = time.time()
            if need_write_master:
                candidate_master = MasterState(
                    schema=MASTER_SCHEMA_ID,
                    schema_version=MASTER_SCHEMA_VERSION,
                    generation=final_generation,
                    created_at=candidate_created_at,
                    updated_at=now,
                    account=MasterAccount(login_id=candidate_login_id, user_id=candidate_user_id),
                    installation=MasterInstallation(physical_address=candidate_device_id),
                    identity=MasterIdentity(auth_server_url=candidate_auth_server, userauth_token=candidate_userauth),
                )

            if need_write_derived:
                candidate_derived = project_legacy_derived(legacy_data, master_generation=final_generation)

            # Capture in-memory snapshots for complete rollback
            old_master_content: str | None = None
            old_master_mode: int | None = None
            if master_exists:
                with contextlib.suppress(Exception):
                    old_master_content = secure_read_raw_text(self.master_path, consume=False)
                    old_master_mode = stat.S_IMODE(self.master_path.stat().st_mode)

            old_derived_content: str | None = None
            old_derived_mode: int | None = None
            if derived_exists:
                with contextlib.suppress(Exception):
                    old_derived_content = secure_read_raw_text(self.canonical_state_path, consume=False)
                    old_derived_mode = stat.S_IMODE(self.canonical_state_path.stat().st_mode)

            def _rollback_targets() -> None:
                if need_write_master:
                    if old_master_content is not None:
                        with contextlib.suppress(Exception):
                            atomic_write_text(self.master_path, old_master_content, mode=old_master_mode or 0o600)
                    else:
                        self.master_path.unlink(missing_ok=True)

                if need_write_derived:
                    if old_derived_content is not None:
                        with contextlib.suppress(Exception):
                            atomic_write_text(
                                self.canonical_state_path,
                                old_derived_content,
                                mode=old_derived_mode or 0o600,
                            )
                    else:
                        self.canonical_state_path.unlink(missing_ok=True)

            try:
                if need_write_master:
                    atomic_write_json(self.master_path, candidate_master.to_dict())

                if need_write_derived:
                    self._atomic_write_derived(self.canonical_state_path, candidate_derived)

                post_legacy_content = secure_read_raw_text(self.legacy_path, consume=False)
                if post_legacy_content != legacy_content:
                    _rollback_targets()
                    raise SecurityError("Legacy source state was unexpectedly modified during migration")

            except BaseException:
                _rollback_targets()
                raise

            return {
                "migrated": True,
                "source_kind": "legacy_samsung_find",
                "target_kind": "master_state_v1",
                "schema_version": MASTER_SCHEMA_VERSION,
            }

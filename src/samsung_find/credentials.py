"""Shared Samsung Account Master Credentials Contract (v1)."""

from __future__ import annotations

import os
import sys
import time
import urllib.parse
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import AuthError, SecurityError, StorageError
from .storage import atomic_write_json, locked, read_json

MASTER_SCHEMA_ID = "io.github.charlesbel.samsung-account.master"
MASTER_SCHEMA_VERSION = 1

FORBIDDEN_DERIVED_KEYS = frozenset(
    {
        "userauth_token",
        "login_id",
        "user_id",
        "physical_address",
        "device_id",
        "auth_server_url",
        "account",
        "identity",
        "installation",
    }
)

ALLOWED_DERIVED_KEYS = frozenset(
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


def validate_derived_state(data: dict[str, Any]) -> dict[str, Any]:
    """Validate that derived state contains no master identity fields."""
    if not isinstance(data, dict):
        raise SecurityError("Derived state must be a JSON dictionary")
    for key in data:
        if key in FORBIDDEN_DERIVED_KEYS:
            raise SecurityError(f"Forbidden master key in derived state: {key!r}")
    return data


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

        schema = data.get("schema")
        if schema != MASTER_SCHEMA_ID:
            raise AuthError(f"Unsupported master schema: {schema!r}")

        version = data.get("schema_version")
        if version != MASTER_SCHEMA_VERSION:
            raise AuthError(f"Unsupported master schema version: {version!r}")

        generation = str(data.get("generation", ""))
        if not generation:
            raise AuthError("Master state missing generation identifier")

        created_at = float(data.get("created_at", time.time()))
        updated_at = float(data.get("updated_at", time.time()))

        account_raw = data.get("account") or {}
        if not isinstance(account_raw, dict) or not account_raw.get("login_id"):
            raise AuthError("Master state missing account.login_id")
        account = MasterAccount(
            login_id=str(account_raw["login_id"]),
            user_id=str(account_raw["user_id"]) if account_raw.get("user_id") else None,
        )

        installation_raw = data.get("installation") or {}
        if not isinstance(installation_raw, dict) or not installation_raw.get("physical_address"):
            raise AuthError("Master state missing installation.physical_address")
        installation = MasterInstallation(
            physical_address=str(installation_raw["physical_address"]),
        )

        identity_raw = data.get("identity") or {}
        if not isinstance(identity_raw, dict) or not identity_raw.get("userauth_token"):
            raise AuthError("Master state missing identity.userauth_token")

        auth_server = validate_auth_server_url(str(identity_raw.get("auth_server_url", "")))

        identity = MasterIdentity(
            auth_server_url=auth_server,
            userauth_token=str(identity_raw["userauth_token"]),
        )

        return cls(
            schema=schema,
            schema_version=version,
            generation=generation,
            created_at=created_at,
            updated_at=updated_at,
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
        return Path(explicit_path).expanduser().resolve()

    env_path = os.environ.get("SAMSUNG_ACCOUNT_MASTER_STATE")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return (base / "samsung-account" / "master.json").resolve()
    elif sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "samsung-account" / "master.json").resolve()
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return (base / "samsung-account" / "master.json").resolve()


def resolve_find_state_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve canonical Find derived state location using standard OS conventions."""
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    env_path = os.environ.get("SAMSUNG_FIND_STATE")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if sys.platform == "win32":
        app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Local"
        return (base / "samsung-find" / "state.json").resolve()
    elif sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "samsung-find" / "state.json").resolve()
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME")
        base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        return (base / "samsung-find" / "state.json").resolve()


def resolve_legacy_find_state_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve the legacy Find state file path (${XDG_CONFIG_HOME:-~/.config}/samsung-find/state.json)."""
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    env_path = os.environ.get("SAMSUNG_FIND_LEGACY_STATE")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return (base / "samsung-find" / "state.json").resolve()
    elif sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "samsung-find" / "state.json").resolve()
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
        return (base / "samsung-find" / "state.json").resolve()


def resolve_pending_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve the pending authentication file path."""
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    env_path = os.environ.get("SAMSUNG_FIND_PENDING")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if sys.platform == "win32":
        app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Local"
        return (base / "samsung-find" / "pending.json").resolve()
    elif sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "samsung-find" / "pending.json").resolve()
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME")
        base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        return (base / "samsung-find" / "pending.json").resolve()


def resolve_redirect_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve the OAuth redirect file path."""
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    env_path = os.environ.get("SAMSUNG_FIND_REDIRECT_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if sys.platform == "win32":
        app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Local"
        return (base / "samsung-find" / "redirect.uri").resolve()
    elif sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "samsung-find" / "redirect.uri").resolve()
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME")
        base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        return (base / "samsung-find" / "redirect.uri").resolve()


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
            self.canonical_state_path = (self.master_path.parent / "state.json").resolve()
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
        return MasterState(
            schema=MASTER_SCHEMA_ID,
            schema_version=MASTER_SCHEMA_VERSION,
            generation=str(uuid.uuid4()),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("created_at", time.time())),
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
                "Using legacy authentication state from samsung-find. "
                "Run 'samsung-find auth migrate-master' to migrate.",
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
        paths = sorted([self.master_path, self.canonical_state_path, self.legacy_path], key=lambda p: str(p.resolve()))

        with locked(paths[0]), locked(paths[1]), locked(paths[2]):
            if not self.legacy_path.exists():
                raise AuthError(f"Legacy state file does not exist: {self.legacy_path.name}")

            legacy_content = self.legacy_path.read_text(encoding="utf-8")
            try:
                legacy_data = read_json(self.legacy_path)
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

            auth_server = validate_auth_server_url(auth_server_raw)
            user_id = str(legacy_data.get("user_id")) if legacy_data.get("user_id") else None

            gen = str(uuid.uuid4())
            now = time.time()
            candidate_master = MasterState(
                schema=MASTER_SCHEMA_ID,
                schema_version=MASTER_SCHEMA_VERSION,
                generation=gen,
                created_at=float(legacy_data.get("created_at", now)),
                updated_at=now,
                account=MasterAccount(login_id=login_id.strip(), user_id=user_id),
                installation=MasterInstallation(physical_address=device_id.strip()),
                identity=MasterIdentity(auth_server_url=auth_server, userauth_token=userauth.strip()),
            )

            clean_derived: dict[str, Any] = {
                "schema": 1,
                "master_generation": gen,
                "created_at": float(legacy_data.get("created_at", now)),
                "updated_at": now,
            }
            if isinstance(legacy_data.get("find"), dict):
                clean_derived["find"] = {
                    k: v
                    for k, v in legacy_data["find"].items()
                    if k in {"access_token", "refresh_token", "expires_at", "token_type", "scope"}
                }
            if isinstance(legacy_data.get("iot"), dict):
                clean_derived["iot"] = {
                    k: v
                    for k, v in legacy_data["iot"].items()
                    if k in {"access_token", "refresh_token", "expires_at", "token_type", "scope"}
                }
            if isinstance(legacy_data.get("web"), dict):
                clean_derived["web"] = {
                    k: v for k, v in legacy_data["web"].items() if k in {"jsessionid", "updated_at"}
                }

            master_exists = self.master_path.exists()
            derived_exists = self.canonical_state_path.exists()

            if master_exists and not force:
                try:
                    existing_master = self._load_master_locked()
                    if (
                        existing_master
                        and existing_master.account.login_id == candidate_master.account.login_id
                        and existing_master.identity.userauth_token == candidate_master.identity.userauth_token
                    ):
                        return {
                            "migrated": False,
                            "source_kind": "legacy_samsung_find",
                            "target_kind": "master_state_v1",
                            "schema_version": MASTER_SCHEMA_VERSION,
                        }
                except Exception:
                    pass
                raise AuthError(
                    "Target master or derived state already exists with conflicting data. Use --force to overwrite."
                )

            if derived_exists and not force and not master_exists:
                raise AuthError(
                    "Target master or derived state already exists with conflicting data. Use --force to overwrite."
                )

            # Two-phase atomic write with rollback on second-write failure
            atomic_write_json(self.master_path, candidate_master.to_dict())
            try:
                self._atomic_write_derived(self.canonical_state_path, clean_derived)
            except BaseException:
                if not master_exists:
                    self.master_path.unlink(missing_ok=True)
                raise

            # Verify legacy state was byte-for-byte untouched
            assert self.legacy_path.read_text(encoding="utf-8") == legacy_content

            return {
                "migrated": True,
                "source_kind": "legacy_samsung_find",
                "target_kind": "master_state_v1",
                "schema_version": MASTER_SCHEMA_VERSION,
            }
